"""Excel dışa aktarım testleri (madde 14: renkli yıllık, madde 15: renksiz tek ay)."""
from io import BytesIO

import openpyxl
import pytest

from rotasyon.excel_io import (
    export_single_month_workbook,
    export_yearly_workbook,
    read_rotation_workbook,
)
from rotasyon.importer import build_dataset
from rotasyon.models import DEFAULT_SETTINGS

from conftest import REFERENCE_XLSX

pytestmark = pytest.mark.skipif(
    not REFERENCE_XLSX.exists(), reason="referans xlsx yok"
)


@pytest.fixture(scope="module")
def seeded():
    return build_dataset(read_rotation_workbook(REFERENCE_XLSX))


@pytest.fixture(scope="module")
def yearly_wb(seeded):
    data = export_yearly_workbook(
        seeded.students,
        seeded.units,
        seeded.classes,
        seeded.assignments,
        DEFAULT_SETTINGS["months"],
    )
    return openpyxl.load_workbook(BytesIO(data))


def test_rule14_yearly_export_has_class_colors(seeded, yearly_wb):
    assert set(yearly_wb.sheetnames) == {"1. GRUP", "2. GRUP"}
    ws = yearly_wb["1. GRUP"]
    class_colors = {
        c.color_hex.lstrip("#").upper() for c in seeded.classes if c.color_hex
    }
    found = set()
    for row in ws.iter_rows(min_row=2, min_col=2, max_col=2):
        cell = row[0]
        if cell.value and cell.fill.patternType == "solid":
            found.add(cell.fill.fgColor.rgb[-6:].upper())
    assert found and found <= class_colors


def test_rule14_yearly_export_red_gendered_units(yearly_wb):
    ws = yearly_wb["1. GRUP"]
    red_k_e = []
    for row in ws.iter_rows(min_row=2, min_col=3, max_col=12):
        for cell in row:
            if isinstance(cell.value, str) and cell.value.endswith((" k", " e")):
                red_k_e.append(cell.font.color and cell.font.color.rgb == "00FF0000"
                               or cell.font.color.rgb == "FFFF0000")
    assert red_k_e and all(red_k_e)


def test_yearly_export_quota_column(yearly_wb):
    ws = yearly_wb["1. GRUP"]
    header_col = next(
        c
        for c in range(1, ws.max_column + 1)
        if ws.cell(1, c).value == "BÖLÜMLER VE SAYILARI"
    )
    values = [
        ws.cell(r, header_col).value
        for r in range(2, ws.max_row + 1)
        if ws.cell(r, header_col).value
    ]
    assert values.count("DİŞ") == 4  # kontenjan kadar tekrar


def test_rule15_single_month_export_is_colorless(seeded):
    data = export_single_month_workbook(
        seeded.students,
        seeded.units,
        seeded.assignments,
        "EYLÜL",
        DEFAULT_SETTINGS["day_labels"],
    )
    ws = openpyxl.load_workbook(BytesIO(data)).active
    assert ws.title == "EYLÜL"
    # başlıklar: iki grup bloğu yan yana, gün etiketleri var
    headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
    texts = [h for h in headers if h]
    assert len(texts) == 2
    assert "Pazartesi" in texts[0]
    # hiçbir hücrede dolgu rengi yok (madde 15)
    for row in ws.iter_rows():
        for cell in row:
            assert cell.fill.patternType is None
    # her iki grubun tüm öğrencileri listelenmiş
    names = sum(
        1
        for row in ws.iter_rows(min_row=3)
        for i, cell in enumerate(row)
        if i in (0, 3) and cell.value
    )
    assert names == 70


def test_roundtrip_reimport(seeded):
    """Dışa aktarılan yıllık dosya, içe aktarıcı tarafından geri okunabilir."""
    data = export_yearly_workbook(
        seeded.students,
        seeded.units,
        seeded.classes,
        seeded.assignments,
        DEFAULT_SETTINGS["months"],
    )
    result = read_rotation_workbook(BytesIO(data))
    ds2 = build_dataset(result)
    assert len(ds2.students) == len(seeded.students)
    assert len(ds2.assignments) == len(seeded.assignments)
    # cinsiyet kısıtları k/e ekiyle korunur
    restrictions = {
        (u.group, u.name, u.gender_restriction)
        for u in ds2.units
        if u.gender_restriction and u.active
    }
    assert (1, "ALÇI ODASI", "E") in restrictions
