"""İsimden cinsiyet tahmini testleri.

Tahmin tamamen çevrimdışıdır (paket içi sözlükler); öğrenci isimleri
hiçbir servise gönderilmez.
"""
import pytest

from rotasyon.gender_guess import (
    AUTO_FILL_CONFIDENCE,
    fill_missing_genders,
    guess_gender,
)
from rotasyon.models import Student

from conftest import GRUP_XLSX


def _g(name):
    return guess_gender(name)


def test_classic_names():
    assert _g("AYŞE YILMAZ").gender == "K"
    assert _g("MEHMET DEMİR").gender == "E"
    assert _g("HATİCE ÖZ").gender == "K"
    assert _g("MUSTAFA ÇELİK").gender == "E"


def test_modern_names_supplement():
    """gender_guesser'ın eski sözlüğünde olmayan yeni kuşak isimleri."""
    assert _g("SUDE KARACA").gender == "K"
    assert _g("ECRİN ARSLAN").gender == "K"
    assert _g("EYMEN KAYA").gender == "E"
    assert _g("MİRAÇ AKSOY").gender == "E"  # gender_guesser yanlış bilir


def test_turkish_i_handling():
    """İ/ı küçültme tuzakları: İREM, IRMAK."""
    assert _g("İREM ÖRNEK").gender == "K"
    assert _g("IRMAK DENEME").gender == "K"


def test_compound_names():
    assert _g("ÇAĞLANUR TASLAK").gender == "K"  # -nur eki
    assert _g("ZEYNEPNUR KURGU").gender == "K"
    assert _g("MAHMUTCAN MODEL").gender == "E"  # kökü erkek + -can
    assert _g("GÜLCAN TAŞ").gender == "K"  # kökü kadın + -can
    assert _g("MUHAMMEDSAİT SAHTE").gender == "E"  # muhammed- öneki
    assert _g("METEHAN ARI").gender == "E"  # -han eki


def test_compound_first_names_with_space():
    assert _g("AYŞE NUR YILMAZ").gender == "K"


def test_ambiguous_gets_no_gender_low_confidence():
    g = _g("DENİZ KARA")
    assert g.gender == ""
    assert 0 < g.confidence < AUTO_FILL_CONFIDENCE


def test_unknown_name():
    g = _g("XQZPTR VWLMN")
    assert g.gender == ""
    assert g.confidence == 0.0


def test_confidence_is_numeric_and_bounded():
    for name in ["AYŞE A", "MAHMUTCAN B", "DENİZ C", "XQZPTR D"]:
        g = _g(name)
        assert 0.0 <= g.confidence <= 1.0
        assert g.percent  # kullanıcıya gösterilecek metin üretir


def test_fill_missing_genders_respects_existing_and_threshold():
    students = [
        Student(full_name="AYŞE YILMAZ", gender="", group=1),
        Student(full_name="DENİZ KARA", gender="", group=1),  # belirsiz
        Student(full_name="MEHMET öz", gender="K", group=1),  # dolu: dokunma
    ]
    filled, remaining = fill_missing_genders(students)
    assert [s.full_name for s, _ in filled] == ["AYŞE YILMAZ"]
    assert students[0].gender == "K"
    assert students[1].gender == ""  # eşik altı: kullanıcıya bırakılır
    assert [s.full_name for s, _ in remaining] == ["DENİZ KARA"]
    assert students[2].gender == "K"  # mevcut değer korunur


@pytest.mark.skipif(not GRUP_XLSX.exists(), reason="örnek dosya yok")
def test_zero_wrong_on_real_known_genders():
    """Gerçek dosyada birim kısıtından cinsiyeti KESİN bilinen öğrencilerde
    tahmin hiç yanlış olmamalı (yanlış tahmin > tahminsizlikten kötüdür)."""
    from rotasyon.excel_io import read_rotation_workbook
    from rotasyon.importer import build_dataset

    ds = build_dataset(read_rotation_workbook(GRUP_XLSX))
    known = [s for s in ds.students if s.gender]
    assert len(known) >= 100
    wrong = [
        (s.full_name, s.gender, g.gender)
        for s in known
        if (g := guess_gender(s.full_name)).gender
        and g.confidence >= AUTO_FILL_CONFIDENCE
        and g.gender != s.gender
    ]
    assert wrong == []
    # kapsam da yüksek kalmalı: bilinenlerin ≥ %90'ı doğru tahminlenir
    correct = sum(
        1
        for s in known
        if (g := guess_gender(s.full_name)).gender == s.gender
        and g.confidence >= AUTO_FILL_CONFIDENCE
    )
    assert correct / len(known) >= 0.9
