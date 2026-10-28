"""Referans Excel'den "Örnek veriyle başla" verisini üretir.

Kullanım: .venv/bin/python scripts/build_seed.py [xlsx_yolu] [cikti_klasoru]
Çıktı: seed_data/ altında students/units/classes/assignments.json.

Kaynak belge gerçek öğrenci adları içerir; depoya giren çıktıda adlar
`anonymize_names` ile uydurma adlarla değiştirilir (cinsiyete uygun, kararlı).
Eşleşmeyen hücre raporu yalnız ekrana basılır, dosyaya yazılmaz.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rotasyon.excel_io import read_rotation_workbook
from rotasyon.importer import build_dataset

FEMALE_NAMES = [
    "AYŞE", "FATMA", "ZEYNEP", "ELİF", "MERVE", "BÜŞRA", "ESRA", "DERYA",
    "SEDA", "GİZEM", "EBRU", "PINAR", "TUĞBA", "SEVGİ", "NUR", "ASLI",
    "BAHAR", "CEREN", "DİLEK", "EZGİ", "HANDE", "İPEK", "LALE", "MELİS",
]
MALE_NAMES = [
    "AHMET", "MEHMET", "MUSTAFA", "ALİ", "HASAN", "HÜSEYİN", "İBRAHİM",
    "MURAT", "EMRE", "BURAK", "KEMAL", "OSMAN", "SELİM", "TOLGA", "UMUT",
    "VOLKAN", "ERKAN", "SERKAN",
]
SURNAMES = [
    "ÖRNEK", "DENEME", "TASLAK", "KURGU", "MODEL", "SAHTE", "UYDURMA",
    "TEMSİLİ", "VARSAYIM", "PROTOTİP", "ŞABLON", "TASARI", "MÜSVEDDE",
    "KARALAMA", "EMSAL", "NUMUNE",
]


def fake_name(index: int, gender: str) -> str:
    """Kararlı, cinsiyete uygun uydurma ad: aynı sıra → aynı ad."""
    firsts = MALE_NAMES if gender == "E" else FEMALE_NAMES
    first = firsts[index % len(firsts)]
    last = SURNAMES[(index // len(firsts)) % len(SURNAMES)]
    return f"{first} {last}"


def anonymize_names(students) -> dict[str, str]:
    """Öğrenci adlarını yerinde uydurma adlarla değiştirir; {gerçek: uydurma}."""
    mapping: dict[str, str] = {}
    sayac = {"E": 0, "K": 0}
    for s in students:
        g = "E" if s.gender == "E" else "K"
        mapping[s.full_name] = fake_name(sayac[g], g)
        sayac[g] += 1
        s.full_name = mapping[s.full_name]
    return mapping


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

    mapping = anonymize_names(ds.students)
    dump("students", ds.students)
    dump("units", ds.units)
    dump("classes", ds.classes)
    dump("assignments", ds.assignments)

    print(f"Öğrenci: {len(ds.students)}")
    print(f"Birim: {len(ds.units)} (aktif: {sum(1 for u in ds.units if u.active)})")
    print(f"Sınıf: {[c.name + ' ' + c.color_hex for c in ds.classes]}")
    print(f"Atama: {len(ds.assignments)}")
    print(f"Uyarı: {len(ds.warnings)}")
    for w in ds.warnings:
        for gercek, uydurma in mapping.items():
            w = w.replace(gercek, uydurma)
        print("  !", w)
    print(f"Eşleşmeyen hücre: {len(ds.unresolved)}")


if __name__ == "__main__":
    main()
