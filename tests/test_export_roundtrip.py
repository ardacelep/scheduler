"""Excel dışa aktarım → içe aktarım round-trip'i (gerçek belge gerektirmez).

Okunur yeni biçim ("FTR.ÜNİT (Erkek)") dışa aktarılıp sorunsuz geri
okunabilmeli: rotasyon olarak algılanmalı, atamalar/cinsiyet kısıtları/gün
notları/sınıflar korunmalı.
"""
from io import BytesIO

from rotasyon.excel_io import (
    detect_workbook_kind,
    export_yearly_workbook,
    read_rotation_workbook,
)
from rotasyon.importer import build_dataset
from rotasyon.models import DEFAULT_MONTHS, FEMALE, MALE

from conftest import make_assignment


def by_name(units, name, gender=""):
    return next(
        u for u in units if u.name == name and u.gender_restriction == gender
    )


def _roundtrip(small_world):
    students, units, classes = small_world
    ftr_k = by_name(units, "FTR.ÜNİT", "K")
    ftr_e = by_name(units, "FTR.ÜNİT", "E")
    cerr = by_name(units, "1.KAT CERR.")
    dis = by_name(units, "DİŞ")
    kiz, erkek = students[0], students[4]
    assignments = [
        make_assignment(kiz, ftr_k, "EYLÜL"),
        make_assignment(erkek, ftr_e, "EYLÜL"),
        make_assignment(students[1], cerr, "EYLÜL", day_note="Çrş günleri üro.pol"),
        make_assignment(students[2], dis, "EYLÜL"),
    ]
    data = export_yearly_workbook(
        students, units, classes, assignments, DEFAULT_MONTHS
    )
    res = read_rotation_workbook(BytesIO(data))
    return data, res, build_dataset(res), assignments


def test_yearly_export_detected_as_rotation(small_world):
    data, _res, _ds, _a = _roundtrip(small_world)
    assert detect_workbook_kind(BytesIO(data)) == "rotation"


def test_export_uses_readable_gender_labels(small_world):
    import openpyxl

    data, _res, _ds, _a = _roundtrip(small_world)
    wb = openpyxl.load_workbook(BytesIO(data))
    text = " ".join(
        str(v)
        for ws in wb.worksheets
        for row in ws.iter_rows(values_only=True)
        for v in row
        if isinstance(v, str)
    )
    assert "(Kız)" in text and "(Erkek)" in text
    assert "FTR.ÜNİT e" not in text and "FTR.ÜNİT k" not in text


def test_roundtrip_preserves_assignments_and_gender_units(small_world):
    _data, _res, ds, src_assign = _roundtrip(small_world)
    # atama sayısı korundu
    assert len(ds.assignments) == len(src_assign)
    # cinsiyet kısıtlı FTR k/e geri okundu
    gr = sorted(
        (u.name, u.gender_restriction) for u in ds.units if u.gender_restriction
    )
    assert ("FTR.ÜNİT", "K") in gr and ("FTR.ÜNİT", "E") in gr


def test_roundtrip_preserves_day_note(small_world):
    _data, _res, ds, _src = _roundtrip(small_world)
    notes = [a.day_note for a in ds.assignments if a.day_note]
    assert "Çrş günleri üro.pol" in notes


def test_roundtrip_infers_gender_from_restricted_units(small_world):
    """Cinsiyet kısıtlı birime atanan öğrencinin cinsiyeti geri okunur."""
    _data, _res, ds, _src = _roundtrip(small_world)
    by_name_map = {s.full_name: s for s in ds.students}
    students, _u, _c = small_world
    # FTR k'ye atanan kız, FTR e'ye atanan erkek olarak çıkarılır
    assert by_name_map[students[0].full_name].gender == FEMALE
    assert by_name_map[students[4].full_name].gender == MALE
