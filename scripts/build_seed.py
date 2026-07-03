"""Referans Excel'den başlangıç seed verisini üretir.

Kullanım: .venv/bin/python scripts/build_seed.py [xlsx_yolu] [cikti_klasoru]
Çıktı: seed_data/ altında students/units/classes/assignments.json + rapor.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rotasyon.excel_io import read_rotation_workbook
from rotasyon.importer import build_dataset


def main() -> None:
    default = Path("example/ARDA_ROTASYON.xlsx")
    if not default.exists():
        default = Path("ARDA_ROTASYON.xlsx")
    xlsx = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("seed_data")
    out_dir.mkdir(parents=True, exist_ok=True)

    result = read_rotation_workbook(xlsx)
    ds = build_dataset(result)

    def dump(name: str, items) -> None:
        with open(out_dir / f"{name}.json", "w", encoding="utf-8") as f:
            json.dump([it.to_dict() for it in items], f, ensure_ascii=False, indent=2)

    dump("students", ds.students)
    dump("units", ds.units)
    dump("classes", ds.classes)
    dump("assignments", ds.assignments)

    report = {
        "warnings": ds.warnings,
        "unresolved_cells": [
            {"ogrenci": s, "ay": m, "ham_deger": raw, "atanan_birim": u}
            for s, m, raw, u in ds.unresolved
        ],
    }
    with open(out_dir / "import_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Öğrenci: {len(ds.students)}")
    print(f"Birim: {len(ds.units)} (aktif: {sum(1 for u in ds.units if u.active)})")
    print(f"Sınıf: {[c.name + ' ' + c.color_hex for c in ds.classes]}")
    print(f"Atama: {len(ds.assignments)}")
    print(f"Uyarı: {len(ds.warnings)}")
    for w in ds.warnings:
        print("  !", w)
    print(f"Eşleşmeyen hücre: {len(ds.unresolved)} (import_report.json)")


if __name__ == "__main__":
    main()
