"""Gerçek dünyadan örnek belgelerle (example/) içe aktarım testleri."""
from collections import Counter

import pytest

from rotasyon.excel_io import (
    detect_workbook_kind,
    read_rotation_workbook,
    read_student_list_workbook,
)
from rotasyon.importer import build_dataset, build_roster_dataset
from rotasyon.models import PROGRAM_EBELIK, PROGRAM_HEMSIRELIK, PROGRAM_SAGLIK_BAKIM

from conftest import GRUP_MID_XLSX, GRUP_XLSX, ROSTER_XLSX


# ---------- tür algılama ----------

@pytest.mark.skipif(not ROSTER_XLSX.exists(), reason="örnek dosya yok")
def test_detect_student_list():
    assert detect_workbook_kind(ROSTER_XLSX) == "student_list"


@pytest.mark.skipif(not GRUP_XLSX.exists(), reason="örnek dosya yok")
def test_detect_rotation():
    assert detect_workbook_kind(GRUP_XLSX) == "rotation"


# ---------- SML öğrenci listesi ----------

@pytest.fixture(scope="module")
def roster_ds():
    roster, warns = read_student_list_workbook(ROSTER_XLSX)
    assert not warns
    return build_roster_dataset(roster)


@pytest.fixture(scope="module")
def rotation_result():
    return read_rotation_workbook(GRUP_XLSX)


@pytest.fixture(scope="module")
def rotation_ds(rotation_result):
    return build_dataset(rotation_result)


@pytest.mark.skipif(not ROSTER_XLSX.exists(), reason="örnek dosya yok")
class TestRoster:
    @pytest.fixture
    def ds(self, roster_ds):
        return roster_ds

    def test_counts(self, ds):
        assert len(ds.students) == 74
        assert {c.name for c in ds.classes} == {"11/A", "11/B", "11/C", "11/D"}

    def test_programs_mapped(self, ds):
        programs = Counter(s.program for s in ds.students)
        assert programs[PROGRAM_HEMSIRELIK] == 28
        assert programs[PROGRAM_SAGLIK_BAKIM] == 34
        assert programs[PROGRAM_EBELIK] == 12

    def test_groups_alternate_by_class(self, ds):
        by_class = {}
        for s in ds.students:
            by_class.setdefault(s.class_name, set()).add(s.group)
        # her sınıf tek grupta; A-C → 1, B-D → 2
        assert by_class["11/A"] == {1}
        assert by_class["11/B"] == {2}
        assert by_class["11/C"] == {1}
        assert by_class["11/D"] == {2}

    def test_gender_left_empty_with_warning(self, ds):
        assert all(not s.gender for s in ds.students)
        assert any("Cinsiyet" in w for w in ds.warnings)

    def test_student_no_captured(self, ds):
        sude = next(s for s in ds.students if s.full_name == "VOLKAN ÖRNEK")
        assert sude.student_no == "5"


# ---------- gerçek yıllık rotasyon dosyası (PSÇ/ÇPC formatı) ----------

@pytest.mark.skipif(not GRUP_XLSX.exists(), reason="örnek dosya yok")
class TestRealRotation:
    @pytest.fixture
    def result(self, rotation_result):
        return rotation_result

    @pytest.fixture
    def ds(self, rotation_ds):
        return rotation_ds

    def test_two_groups_detected(self, ds):
        groups = Counter(s.group for s in ds.students)
        assert groups[1] == 69
        assert groups[2] == 66

    def test_day_labels_from_headers(self, result):
        assert "PAZARTESİ" in result.day_labels[1]
        assert "PERŞEMBE" in result.day_labels[2]

    def test_class_from_text_column(self, ds):
        names = {c.name for c in ds.classes}
        assert {"12/A", "12/B", "12/C", "12/D", "12/E", "12/F"} <= names
        yaren = next(s for s in ds.students if s.full_name == "YAREN ÖRNEK")
        assert yaren.class_name == "12/A"
        assert yaren.student_no == "1"  # föy no

    def test_gender_word_suffixes_parsed(self, ds):
        """'EFOR kız', 'ÜROLOJİ POL.erkek' gibi ekler kısıt olur."""
        by = {
            (u.group, u.name): u.gender_restriction
            for u in ds.units
            if u.active
        }
        assert by[(1, "EFOR")] == "K"
        assert by[(1, "ÜROLOJİ POL")] == "E"
        assert by[(1, "YENİ DOĞAN")] == "K"

    def test_quota_from_in_sheet_column(self, ds):
        by = {
            (u.group, u.name, u.gender_restriction): u.quota
            for u in ds.units
            if u.active
        }
        # birim adları içe aktarımda normalize edilir ("FTR. ÜNİT." → "FTR.ÜNİT")
        assert by[(1, "1.KAT CERR", "")] == 3
        assert by[(1, "DİŞ", "")] == 4
        assert by[(2, "FTR.ÜNİT", "")] == 4

    def test_gender_inferred_for_most_students(self, ds):
        inferred = sum(1 for s in ds.students if s.gender)
        assert inferred >= 100  # 135 öğrencinin büyük kısmı


# ---------- kullanım senaryosu 2: yarım sezonu içe aktarıp devam etme ----------

@pytest.mark.skipif(not GRUP_MID_XLSX.exists(), reason="örnek dosya yok")
def test_mid_season_import_and_continue(settings):
    """Belirli bir aya kadar elle yapılmış rotasyon içe aktarılır,
    program kalınan yerden (geçmişi bilerek) devam eder."""
    from rotasyon.models import Assignment
    from rotasyon.normalize import normalize_key
    from rotasyon.rules import ERROR, check_all
    from rotasyon.solver import solve_month

    ds = build_dataset(read_rotation_workbook(GRUP_MID_XLSX))
    assert {a.month for a in ds.assignments} == {"EYLÜL"}  # yarım sezon

    # kullanıcı düzeltmesi: eksik cinsiyetler doldurulur
    for i, s in enumerate(ds.students):
        if not s.gender:
            s.gender = "K" if i % 2 == 0 else "E"

    settings["solver"]["time_limit_seconds"] = 15
    g1 = [s for s in ds.students if s.group == 1]
    units1 = [u for u in ds.units if u.group in (0, 1)]
    ids1 = {s.id for s in g1}
    history = [a for a in ds.assignments if a.student_id in ids1]

    r = solve_month(g1, units1, "EKİM", history=history, settings=settings)
    assert r.ok, r.infeasible_reasons

    # madde 1: kimse EYLÜL'de gittiği birime geri dönmez
    units_by_id = {u.id: u for u in ds.units}
    eylul = {
        a.student_id: normalize_key(units_by_id[a.unit_id].name)
        for a in history
    }
    for s in g1:
        if s.id in eylul:
            assert (
                normalize_key(units_by_id[r.assignments[s.id]].name)
                != eylul[s.id]
            )

    # tüm tablo (içe aktarılan EYLÜL + üretilen EKİM) denetimden geçer
    new = [
        Assignment(student_id=sid, month="EKİM", unit_id=uid)
        for sid, uid in r.assignments.items()
    ]
    errors = [
        v
        for v in check_all(g1, units1, history + new, settings["months"])
        if v.severity == ERROR
    ]
    assert errors == [], [e.message for e in errors]


# ---------- uçtan uca: yeni sezon akışı ----------

@pytest.mark.skipif(
    not (GRUP_XLSX.exists() and ROSTER_XLSX.exists()), reason="örnek dosya yok"
)
def test_full_season_flow(tmp_path, rotation_ds, roster_ds, settings):
    """Gerçek kullanım hikayesi: önceki sezonu içe aktar → yeni sezonu
    öğrenci listesiyle aç (birimleri kopyala) → cinsiyetleri tamamla →
    ilk ayı çöz → kural denetiminden geçir."""
    from rotasyon.models import Assignment
    from rotasyon.rules import ERROR, check_all
    from rotasyon.solver import solve_month
    from rotasyon.store import SeasonManager

    m = SeasonManager(tmp_path)

    # 1) önceki sezon: gerçek GRUP dosyasından
    prev = m.create("2024-2025")
    prev.save_students(rotation_ds.students)
    prev.save_units(rotation_ds.units)
    prev.save_classes(rotation_ds.classes)
    prev.save_assignments(rotation_ds.assignments)

    # 2) yeni sezon: birimler kopyalanır, öğrenciler SML listesinden
    new = m.create("2025-2026", copy_units_from="2024-2025")
    assert m.active_season() == "2025-2026"
    new.save_students(roster_ds.students)
    assert len(new.load_units()) == len(rotation_ds.units)
    assert new.load_assignments() == []  # atama geçmişi taşınmaz

    # 3) kullanıcı düzeltmesi simülasyonu: cinsiyetleri doldur
    students = new.load_students()
    for i, s in enumerate(students):
        s.gender = "K" if i % 2 == 0 else "E"
    new.save_students(students)

    # 4) 1. grubun ilk ayını çöz ve denetle
    group1 = [s for s in students if s.group == 1]
    units = [u for u in new.load_units() if u.group in (0, 1)]
    settings["solver"]["time_limit_seconds"] = 10
    r = solve_month(group1, units, "EYLÜL", history=[], settings=settings)
    assert r.ok, r.infeasible_reasons
    assignments = [
        Assignment(student_id=sid, month="EYLÜL", unit_id=uid)
        for sid, uid in r.assignments.items()
    ]
    errors = [
        v
        for v in check_all(group1, units, assignments, settings["months"])
        if v.severity == ERROR
    ]
    assert errors == [], [e.message for e in errors]
    # önceki sezon verisi bozulmadı
    assert len(m.store("2024-2025").load_assignments()) == len(
        rotation_ds.assignments
    )
