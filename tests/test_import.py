"""Referans ARDA_ROTASYON.xlsx üzerinden içe aktarım testleri."""
import pytest

from rotasyon.excel_io import read_rotation_workbook
from rotasyon.importer import build_dataset
from rotasyon.models import FEMALE

from conftest import REFERENCE_XLSX

pytestmark = pytest.mark.skipif(
    not REFERENCE_XLSX.exists(), reason="referans xlsx yok"
)


@pytest.fixture(scope="module")
def dataset():
    return build_dataset(read_rotation_workbook(REFERENCE_XLSX))


def test_student_counts(dataset):
    g1 = [s for s in dataset.students if s.group == 1]
    g2 = [s for s in dataset.students if s.group == 2]
    assert len(g1) == 31
    assert len(g2) == 39


def test_all_assignments_parsed(dataset):
    # 70 öğrenci x 10 ay — örnek dosyada tablo eksiksiz
    assert len(dataset.assignments) == 700


def test_rule14_class_colors_extracted(dataset):
    """Madde 13/14: sınıflar renkleriyle çıkarılır (tema rengi dahil)."""
    colors = {c.name: c.color_hex for c in dataset.classes}
    assert len(colors) == 4
    assert colors["C"] == "#009900"
    assert colors["A"] == "#FFFF00"
    assert colors["D"] == "#FF00FF"
    # tema+tint rengi hex'e çözülmüş olmalı
    assert colors["B"].startswith("#") and len(colors["B"]) == 7


def test_rule2_gender_restrictions_from_red_k_e(dataset):
    by = {
        (u.group, u.name, u.gender_restriction): u
        for u in dataset.units
        if u.active
    }
    assert (1, "ALÇI ODASI", "E") in by
    assert (1, "KÜÇÜK CERR ODASI", "K") in by
    assert by[(1, "DİŞ", "")].quota == 4


def test_rule17_ftr_pair_must_fill(dataset):
    ftr = [u for u in dataset.units if u.active and "FTR" in u.name]
    assert len(ftr) == 4  # iki grup x (k + e)
    assert all(u.must_fill for u in ftr)
    assert {u.gender_restriction for u in ftr} == {"K", "E"}


def test_rule9_dis_exemption_from_side_note(dataset):
    exempt = {s.full_name for s in dataset.students if s.dis_exempt}
    assert "AYŞE ÖRNEK" in exempt
    assert "BÜŞRA ÖRNEK" in exempt
    # "diş-geç" notu hem bayrak hem not olarak korunur
    sude = next(s for s in dataset.students if s.full_name == "EZGİ DENEME")
    assert sude.dis_exempt and "geç" in sude.note


def test_gender_inferred_from_gendered_cells(dataset):
    irmak = next(s for s in dataset.students if s.full_name == "AYŞE ÖRNEK")
    assert irmak.gender == FEMALE  # EYLÜL: "2.KAT DOĞUM k"


def test_unresolved_cells_are_reported_not_dropped(dataset):
    assert len(dataset.unresolved) > 0
    # eşleşmeyen hücreler pasif birim olarak eklenir, atama kaybolmaz
    raw_values = {raw for _, _, raw, _ in dataset.unresolved}
    assert "ENDOSKOPİ-ECZANE SARF--ybc" in raw_values


def test_rule11_day_notes_preserved(dataset):
    """Madde 11: parantezli gün notları atamada saklanır."""
    notes = [a.day_note for a in dataset.assignments if a.day_note]
    assert any("üro" in n for n in notes)
