"""Yeni öğrenci listesi biçimleri: başlıksız kodlu xlsx + e-okul PDF.

Gerçek öğrenci verisi kullanılmaz; tüm isimler uydurmadır (example/ klasörü
gitignore'dur ve testlerde ona bağımlı olunmaz).
"""
from io import BytesIO

import openpyxl

from rotasyon.excel_io import (
    detect_workbook_kind,
    read_student_list_workbook,
)
from rotasyon.importer import build_roster_dataset, program_from_field
from rotasyon.models import (
    PROGRAM_EBELIK,
    PROGRAM_HEMSIRELIK,
    PROGRAM_SAGLIK_BAKIM,
)
from rotasyon.pdf_io import _parse_page_text


# ------------------- program_from_field kısaltmaları -------------------

def test_program_from_field_codes():
    assert program_from_field("HY") == PROGRAM_HEMSIRELIK
    assert program_from_field("SBT") == PROGRAM_SAGLIK_BAKIM
    assert program_from_field("EY") == PROGRAM_EBELIK
    # tam metin de hâlâ çalışır
    assert program_from_field("Ebe Yardımcılığı") == PROGRAM_EBELIK
    assert program_from_field("Sağlık Bakım Teknisyenliği") == PROGRAM_SAGLIK_BAKIM


# ------------------- başlıksız kodlu xlsx (A-HY) -------------------

def _coded_workbook_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["2099-2100 ÖĞRENCİ LİSTESİ", None, None])
    ws.append([1, "AYSEL DENEME  YILDIZ", "A-HY"])  # çift boşluk temizlenmeli
    ws.append([2, "MEHMET CAN DENEME", "B-SBT"])
    ws.append([3, "ZELIHA DENEME", "d-ey"])  # küçük harf de tanınmalı
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_coded_roster_detected_and_parsed():
    data = _coded_workbook_bytes()
    assert detect_workbook_kind(BytesIO(data)) == "student_list"
    roster, warns = read_student_list_workbook(BytesIO(data))
    assert warns == []
    assert [r.name for r in roster] == [
        "AYSEL DENEME YILDIZ",  # çift boşluk tek boşluğa indi
        "MEHMET CAN DENEME",
        "ZELIHA DENEME",
    ]
    assert [r.class_text for r in roster] == ["A", "B", "D"]
    ds = build_roster_dataset(roster)
    progs = {s.full_name: s.program for s in ds.students}
    assert progs["AYSEL DENEME YILDIZ"] == PROGRAM_HEMSIRELIK
    assert progs["MEHMET CAN DENEME"] == PROGRAM_SAGLIK_BAKIM
    assert progs["ZELIHA DENEME"] == PROGRAM_EBELIK


def test_coded_roster_skips_non_matching_rows():
    """Kod hücresi biçime uymayan satırlar öğrenci sayılmaz."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["başlık", "filanca", "notlar"])  # kod değil → atlanır
    ws.append([1, "AYSEL DENEME", "A-HY"])
    buf = BytesIO()
    wb.save(buf)
    roster, _ = read_student_list_workbook(BytesIO(buf.getvalue()))
    assert len(roster) == 1
    assert roster[0].name == "AYSEL DENEME"


# ------------------- e-okul PDF metin ayrıştırma -------------------

_PDF_PAGE = """\
T.C.
AMP - 11. Sınıf / A Şubesi (SAĞLIK HİZMETLERİ ALANI) Sınıf Listesi
Sınıf Öğretmeni: FİLANCA HOCA
DalıSoyadıAdıÖğrenci NoS.No
 100 AYSEL DENEME YILDIZ 1 Hemşire Yardımcılığı
 200 MEHMET CAN DENEME 2 Hemşire Yardımcılığı
 300 ZELIHA DENEME 3 Hemşire Yardımcılığı
Kız Öğrenci Sayısı : Erkek Öğrenci Sayısı : Toplam Öğrenci Sayısı :  3 1 2
"""


def test_pdf_page_parse_rows_and_counts():
    students, sube, counts, warns = _parse_page_text(_PDF_PAGE, seq_start=0)
    assert warns == []
    assert sube == "A"
    assert [s.name for s in students] == [
        "AYSEL DENEME YILDIZ",
        "MEHMET CAN DENEME",
        "ZELIHA DENEME",
    ]
    assert [s.student_no for s in students] == ["100", "200", "300"]
    assert all(s.class_text == "A" for s in students)
    # sayı satırı pypdf'te (Toplam, Erkek, Kız) sırasında → (kız, erkek)
    assert counts == (2, 1)
    ds = build_roster_dataset(students)
    assert all(s.program == PROGRAM_HEMSIRELIK for s in ds.students)


def test_pdf_page_seq_offset_continues():
    """Çok sayfalı listede genel sıra numarası sürer."""
    students, _, _, _ = _parse_page_text(_PDF_PAGE, seq_start=18)
    assert [s.row for s in students] == [19, 20, 21]


def test_pdf_page_inconsistent_counts_warns():
    bad = _PDF_PAGE.replace(
        "Toplam Öğrenci Sayısı :  3 1 2",
        "Toplam Öğrenci Sayısı :  9 1 2",  # 9 ≠ 1+2
    )
    _students, _sube, counts, warns = _parse_page_text(bad, seq_start=0)
    assert counts is None
    assert warns and "tutarsız" in warns[0]
