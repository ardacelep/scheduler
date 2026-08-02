"""Varsayılan birim kataloğu.

Gerçek bir hastane rotasyon belgesinden türetilmiş birim tanımları
(ad, grup, kontenjan, cinsiyet kısıtı, branş kategorisi, bayraklar).
Kişisel veri içermez. Yeni sezon açılırken kopyalanacak bir önceki
sezon yoksa başlangıç noktası olarak sunulur; kullanıcı sonra Veri
Yönetimi'nden serbestçe düzenler.
"""
from __future__ import annotations

import json
from pathlib import Path

from .models import Requirement, Unit

_CATALOG_PATH = Path(__file__).parent / "data" / "default_units.json"
_REQ_PATH = Path(__file__).parent / "data" / "default_requirements.json"


def catalog_available() -> bool:
    return _CATALOG_PATH.exists()


def load_default_units() -> list[Unit]:
    """Katalogdaki birimleri TAZE id'lerle döndürür (dosyada id tutulmaz)."""
    with open(_CATALOG_PATH, encoding="utf-8") as f:
        return [Unit.from_dict(d) for d in json.load(f)]


def load_default_requirements() -> list[Requirement]:
    """Katalogla birlikte gelen varsayılan sezon gereksinimleri.

    Elle hazırlanmış rotasyon belgelerinin altındaki yazılı kurallardan
    türetilir (bkz. scripts/catalog_from_rotations.py). Birimleri varsayılan
    katalogdan seçen yeni sezon bu gereksinimleri de hazır alır — kullanıcı
    her sezon aynı beş-altı kuralı elle kurmak zorunda kalmaz.

    Katalogdaki birim ADLARINA dayanır; kullanıcı birim adını değiştirirse
    ilgili gereksinim o birime artık uymaz (Gereksinimler ekranı bunu
    "0 uygun birim" diye gösterir).
    """
    if not _REQ_PATH.exists():
        return []
    with open(_REQ_PATH, encoding="utf-8") as f:
        return [Requirement.from_dict(d) for d in json.load(f)]


def catalog_attributes() -> dict[str, dict]:
    """normalize_key(ad) → katalog nitelikleri (intensity, reserve, branş...).

    İçe aktarılan rotasyon dosyaları yoğunluk/yedek bilgisi taşımaz; birimler
    isim eşleşmesiyle katalogdan zenginleştirilir.
    """
    from .normalize import normalize_key

    if not catalog_available():
        return {}
    attrs: dict[str, dict] = {}
    for u in load_default_units():
        attrs.setdefault(
            normalize_key(u.name),
            {
                "intensity": u.intensity,
                "reserve": u.reserve,
                "branch_category": u.branch_category,
                "ebelik_priority": u.ebelik_priority,
            },
        )
    return attrs
