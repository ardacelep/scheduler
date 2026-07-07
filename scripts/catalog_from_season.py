"""Bir sezonun birimlerinden varsayılan birim kataloğunu üretir.

Kullanım:  python scripts/catalog_from_season.py "26-27"

İş akışı: Veri Yönetimi'nden birimleri düzenle → bu script'le katalogu o
sezona eşitle. Adlar normalize edilir ("FTR. ÜNİT." → "FTR.ÜNİT"), id'ler
atılır (katalog id tutmaz; kopyalanırken taze id verilir). Kişisel veri
içermez (yalnız birim tanımları), depoya girebilir.

Ek olarak sezonun kendi birim adlarını da normalize edip geri yazar (istenirse
--no-write-back ile kapatılır) ki sezon ile katalog birebir aynı kalsın.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rotasyon.normalize import normalize_unit_name  # noqa: E402
from rotasyon.store import SeasonManager  # noqa: E402

TARGET = ROOT / "rotasyon" / "data" / "default_units.json"
# Katalog alan sırası (mevcut dosyayla tutarlı; id yok)
_FIELDS = [
    "name", "quota", "gender_restriction", "branch_category", "single_slot",
    "pool", "ebelik_priority", "must_fill", "intensity", "reserve", "group",
]


def main() -> None:
    season = sys.argv[1] if len(sys.argv) > 1 else None
    write_back = "--no-write-back" not in sys.argv
    manager = SeasonManager()
    if season is None:
        season = manager.active_season()
    store = manager.store(season)
    units = store.load_units()

    changed = 0
    for u in units:
        clean = normalize_unit_name(u.name)
        if clean != u.name:
            changed += 1
            u.name = clean

    if write_back and changed:
        store.save_units(units)
        print(f"Sezon '{season}': {changed} birim adı normalize edilip geri yazıldı.")

    out = [{f: getattr(u, f) for f in _FIELDS} for u in units]
    TARGET.write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"{len(out)} birim → {TARGET}  (kaynak sezon: {season})")


if __name__ == "__main__":
    main()
