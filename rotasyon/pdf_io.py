"""e-okul 'Sınıf Listesi' PDF öğrenci listesi okuyucu.

e-okul çıktısı şube başına bir sayfadır; tablo sütunları:
``S.No | Öğrenci No | Adı | Soyadı | Dalı``. pypdf metin çıkarımı sütun
sırasını (x konumuna göre) karıştırdığı için satırlar ÇAPA ile ayrıştırılır:
baştaki tam sayı = Öğrenci No, sondaki bilinen Dalı metni ve ondan hemen
önceki tam sayı = S.No; ikisinin arasında kalan metin tam addır (Adı + Soyadı).
Bu yaklaşım sütun sırası bozulsa da sağlam çalışır.

Sayfa altındaki "Kız/Erkek/Toplam Öğrenci Sayısı" satırı, cinsiyet tahminini
DOĞRULAMAK için şube başına (kız, erkek) sayısı olarak döndürülür (öğrenci
bazında cinsiyet e-okul listesinde bulunmaz).

Ayrıştırma mantığı saf metin üzerinde (`_parse_page_text`) çalışır; pypdf
yalnız metin çıkarımı için kullanılır, böylece test gerçek PDF gerektirmez.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .excel_io import RosterStudent

# Bilinen program adları (Dalı sütunu) — satır sonu çapası.
_DALILER = ("Hemşire Yardımcılığı", "Sağlık Bakım Teknisyenliği", "Ebe Yardımcılığı")
_ROW_RE = re.compile(
    r"^\s*(\d+)\s+(.+?)\s+(\d+)\s+(" + "|".join(map(re.escape, _DALILER)) + r")\s*$"
)
_SUBE_RE = re.compile(r"/\s*([A-ZÇĞİÖŞÜ])\s*Şubesi", re.IGNORECASE)
_COUNT_RE = re.compile(
    r"Kız Öğrenci Sayısı.*?Toplam Öğrenci Sayısı\s*:\s*(\d+)\s+(\d+)\s+(\d+)"
)


@dataclass
class PdfRosterResult:
    students: list[RosterStudent]
    warnings: list[str]
    # şube harfi -> (kız, erkek) sayısı (cinsiyet tahmini doğrulaması için)
    gender_counts: dict[str, tuple[int, int]]


def _parse_page_text(text: str, seq_start: int) -> tuple[list[RosterStudent], str, tuple[int, int] | None, list[str]]:
    """Tek sayfanın çıkarılmış metnini ayrıştırır.

    Dönüş: (öğrenciler, şube_harfi, (kız,erkek)|None, uyarılar). ``seq_start``
    genel sıra numarası için başlangıç ofsetidir.
    """
    warnings: list[str] = []
    sube_m = _SUBE_RE.search(text)
    sube = sube_m.group(1).upper() if sube_m else ""

    students: list[RosterStudent] = []
    seq = seq_start
    for line in text.splitlines():
        m = _ROW_RE.match(line)
        if not m:
            continue
        ogr_no, name, _sno, dali = m.groups()
        seq += 1
        students.append(
            RosterStudent(
                name=re.sub(r"\s+", " ", name).strip(),
                class_text=sube,
                field_text=dali,  # tam metin; program_from_field çözer
                student_no=ogr_no.strip(),
                row=seq,
            )
        )

    counts: tuple[int, int] | None = None
    cm = _COUNT_RE.search(text)
    if cm and sube:
        # pypdf sayıları etiketlerin ters sırasında yayar: (Toplam, Erkek, Kız)
        total, erkek, kiz = (int(x) for x in cm.groups())
        if total == erkek + kiz:
            counts = (kiz, erkek)
        else:
            warnings.append(
                f"{sube} şubesi: PDF cinsiyet sayıları tutarsız "
                f"(Kız {kiz} + Erkek {erkek} ≠ Toplam {total}); doğrulama atlandı."
            )
    return students, sube, counts, warnings


def read_student_list_pdf(path: str | Path) -> PdfRosterResult:
    """e-okul 'Sınıf Listesi' PDF'ini okur.

    ``path`` bir dosya yolu ya da dosya benzeri nesne (BytesIO) olabilir.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "PDF okumak için 'pypdf' paketi gerekli (pip install pypdf)."
        ) from exc

    reader = PdfReader(path)
    students: list[RosterStudent] = []
    warnings: list[str] = []
    gender_counts: dict[str, tuple[int, int]] = {}
    for page in reader.pages:
        text = page.extract_text() or ""
        page_students, sube, counts, warns = _parse_page_text(text, len(students))
        students.extend(page_students)
        warnings.extend(warns)
        if counts is not None and sube:
            gender_counts[sube] = counts

    if not students:
        warnings.append(
            "PDF'te öğrenci satırı bulunamadı (e-okul 'Sınıf Listesi' "
            "biçimi bekleniyor: S.No | Öğrenci No | Adı | Soyadı | Dalı)."
        )
    return PdfRosterResult(students, warnings, gender_counts)
