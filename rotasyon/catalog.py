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

from .models import Unit

_CATALOG_PATH = Path(__file__).parent / "data" / "default_units.json"


def catalog_available() -> bool:
    return _CATALOG_PATH.exists()


def load_default_units() -> list[Unit]:
    """Katalogdaki birimleri TAZE id'lerle döndürür (dosyada id tutulmaz)."""
    with open(_CATALOG_PATH, encoding="utf-8") as f:
        return [Unit.from_dict(d) for d in json.load(f)]


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
