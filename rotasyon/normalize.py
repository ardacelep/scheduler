"""Birim adı normalizasyonu ve hücre değeri ayrıştırma.

Referans Excel'de aynı birim farklı yazımlarla geçiyor ("4.KAT DAH",
"4.KAT DAH.", "4.KAT DAHİLİYE"; "ECZ. SARF", "ECZ . SARF") ve hücrelerde
ek bilgiler gömülü: cinsiyet eki (" k"/" e"), parantez içi gün notu,
"--" ile eklenmiş serbest not, "X-Y" birleşik atamalar. Bu modül tek bir
hücre değerini yapısal parçalara ayırır; kanonik ada eşleme, kullanıcı
tarafından genişletilebilen alias tablosu üzerinden yapılır.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_TR_UPPER = str.maketrans("iı", "İI")


def tr_upper(s: str) -> str:
    return s.translate(_TR_UPPER).upper()


def normalize_key(s: str) -> str:
    """Karşılaştırma anahtarı: Türkçe büyük harf, tek boşluk, uç noktasız."""
    s = tr_upper(s.strip())
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*\.\s*", ".", s)  # "ECZ . SARF" -> "ECZ.SARF"
    s = s.rstrip(".")
    return s


def normalize_unit_name(name: str) -> str:
    """Birim adının GÖSTERİM biçimini temizler (büyük harfe çevirmeden).

    normalize_key ile aynı temizliği yapar ama özgün harf büyüklüğünü korur:
    çoklu boşluk tek boşluğa iner, nokta çevresindeki boşluklar silinir
    ("FTR. ÜNİT." -> "FTR.ÜNİT"), baştaki/sondaki boşluk ve noktalar atılır.
    İç noktalar korunur ("1.KAT" aynı kalır). Kimlik/eşleşme normalize_key
    ile yapıldığından bu temizlik atama çözümlemesini etkilemez.
    """
    s = str(name).strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*\.\s*", ".", s)
    return s.strip(" .")


@dataclass
class ParsedCell:
    """Bir rotasyon hücresinin ayrıştırılmış hali."""

    raw: str
    base_name: str = ""  # cinsiyet eki ve notlardan arındırılmış birim adı
    gender_suffix: str = ""  # "K", "E" veya ""
    day_note: str = ""  # parantez içi gün notu (madde 11)
    extra_note: str = ""  # "--" sonrası serbest not
    key: str = field(default="", repr=False)  # normalize edilmiş eşleme anahtarı

    def __post_init__(self):
        if not self.key and self.base_name:
            self.key = normalize_key(self.base_name)


_PAREN_RE = re.compile(r"\(([^)]*)\)\s*$")
# Cinsiyet eki: " k"/".e" tek harfleri (yalnız küçük harf — "YB/E" gibi adlarla
# karışmasın) veya "kız"/"erkek" kelimeleri (büyük/küçük fark etmez; gerçek
# belgelerde "EFOR kız", "ÜROLOJİ POL.erkek" gibi geçiyor).
_GENDER_TOKEN_RE = re.compile(r"[\s.]([A-Za-zçğıöşüÇĞIİÖŞÜ]+)\s*$")
_GENDER_WORDS_K = {"kız", "kiz"}
_GENDER_WORDS_E = {"erkek"}


def _gender_from_token(token: str) -> str:
    """Ek adayı tokenden cinsiyet çıkarır; ek değilse ''."""
    low = tr_upper(token).lower()  # Türkçe I/İ tutarlılığı için çift çevrim
    if low in _GENDER_WORDS_K or (token == "k"):
        return "K"
    if low in _GENDER_WORDS_E or (token == "e"):
        return "E"
    return ""


def parse_cell(value: str) -> ParsedCell:
    raw = str(value).strip()
    text = raw

    # "--" ve sonrası: serbest not / ikincil görev ("YB/C--- endoskopi")
    extra_note = ""
    m = re.search(r"\s*-{2,}\s*", text)
    if m:
        extra_note = text[m.end():].strip()
        text = text[: m.start()].strip()

    # Sondaki parantez grupları: "(Kız)"/"(Erkek)" → cinsiyet, diğerleri
    # gün notu ("EVRAK KAYIT(Çrş günleri üro.pol)", "FTR.ÜNİT (Erkek)").
    # Hem bizim okunur dışa aktarımımız hem gün notlu gerçek belgeler desteklenir.
    day_note = ""
    gender_suffix = ""
    while True:
        m = _PAREN_RE.search(text)
        if not m:
            break
        content = m.group(1).strip()
        g = _gender_from_token(content)
        if g and not gender_suffix:
            gender_suffix = g
        elif not day_note:
            day_note = content
        else:
            break  # sınıflandırılamayan üçüncü parantez: adın parçası say
        text = text[: m.start()].strip()

    # Eski biçim cinsiyet eki: "EKG k", "ALÇI ODASI e", "EFOR kız",
    # "ÜROLOJİ POL.erkek" (parantezsiz — gerçek hastane belgeleri)
    if not gender_suffix:
        m = _GENDER_TOKEN_RE.search(text)
        if m:
            gender_suffix = _gender_from_token(m.group(1))
            if gender_suffix:
                text = text[: m.start()].strip()

    return ParsedCell(
        raw=raw,
        base_name=text,
        gender_suffix=gender_suffix,
        day_note=day_note,
        extra_note=extra_note,
    )


class AliasTable:
    """Varyant yazım -> kanonik birim adı eşlemesi.

    Kanonik adlar birim listesinden gelir; alias'lar hem seed'de hem
    kullanıcı onayıyla (içe aktarım ekranı) birikir.
    """

    def __init__(self, aliases: dict[str, str] | None = None):
        # anahtarlar normalize edilmiş halde saklanır
        self._map: dict[str, str] = {}
        for variant, canonical in (aliases or {}).items():
            self.add(variant, canonical)

    def add(self, variant: str, canonical: str) -> None:
        self._map[normalize_key(variant)] = canonical

    def resolve(self, name_or_cell: str) -> str | None:
        """Kanonik adı döndürür; eşleşme yoksa None (kullanıcıya sorulur)."""
        return self._map.get(normalize_key(name_or_cell))

    def to_dict(self) -> dict[str, str]:
        return dict(self._map)

    @classmethod
    def from_dict(cls, d: dict[str, str]) -> "AliasTable":
        return cls(d)
