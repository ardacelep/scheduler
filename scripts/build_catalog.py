"""'BÖLÜMLER VE ÖZELLİKLERİ.xlsx' → rotasyon/data/default_units.json

⚠️ **ARTIK KULLANILMIYOR — `catalog_from_rotations.py` bunun yerini aldı.**
Bu script'i çalıştırmak katalogu GERİLETİR: kaynak belge kontenjan vermediği
için havuz birimlerine aşağıdaki `POOL_QUOTA_DEFAULT = 3` tahminini yazar,
oysa elle yapılmış gerçek rotasyonlar kat servislerinin 1-2 kişi aldığını
gösteriyor. (`tests/test_catalog.py::test_catalog_quotas_match_real_documents`
bu gerilemeyi yakalar.) Dosya, eski belgenin ayrıştırma kurallarına referans
olsun diye duruyor.

Gerçek belgeden varsayılan birim kataloğunu üretir. Belge gitignore'lu
(example/) olduğundan bu script yalnız geliştirme makinesinde koşar;
üretilen JSON kişisel veri içermez ve depoya girer.

Özellik sütunu kuralları:
- "BİR KIZ, BİR ERKEK (TOPLAM 2)"  → k/e çifti: iki kayıt, must_fill (madde 17)
- "BİR ERKEK/KIZ ÖĞRENCİ"          → kontenjan 1 + cinsiyet kısıtı
- "4 ÖĞRENCİ" / "İKİ ÖĞRENCİ"      → sayısal kontenjan
- "BİR VEYA İKİ ÖĞRENCİ"           → kontenjan 2 (üst sınır)
- "YOĞUN BÖLÜM" / "HAFİF BÖLÜM"    → intensity (peş peşe yasağı)
- "CERRAHİ/DAHİLİ BRANŞ"           → branş kategorisi
- "İHTİYAÇ OLURSA" veya gri dolgu  → reserve (yalnız gerekirse kullanılır)
- kontenjan yazmayan kat servisleri → havuz birimi (eşit dağıtım)
"""
import json
import re
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rotasyon.models import (  # noqa: E402
    BRANCH_CERRAHI,
    BRANCH_DAHILI,
    BRANCH_DIGER,
    BRANCH_DOGUM_SALONU,
    BRANCH_PALYATIF,
    BRANCH_YOGUN_BAKIM,
    INTENSITY_HAFIF,
    INTENSITY_YOGUN,
)
from rotasyon.normalize import normalize_key, normalize_unit_name  # noqa: E402

SOURCE = ROOT / "example" / "BÖLÜMLER VE ÖZELLİKLERİ.xlsx"
TARGET = ROOT / "rotasyon" / "data" / "default_units.json"
# Havuz birimlerinin aylık kontenjanları (belge sayı vermez); önceki gerçek
# rotasyon dosyalarındaki tipik değerler.
POOL_QUOTA_DEFAULT = 3

# Ebelik öncelikli birimler (madde 18): doğum/yenidoğan ilişkili olanlar.
# "2.KAT ÇOCUK ve DOĞUM" belgede "2.KAT ÇOCUK" + "2.KAT DOĞUM" olarak ayrıldı;
# ebelik önceliği doğum bölümündedir.
EBELIK_PRIORITY_KEYS = {"2.KAT DOĞUM", "DOĞUM SALONU-YENİ DOĞAN", "GEBE OKULU-NST"}


def parse_row(name: str, spec: str, gray: bool) -> list[dict]:
    spec_up = spec.upper()
    name = normalize_unit_name(name)  # "FTR.ÜNİT." → "FTR.ÜNİT" (ad biçimi)
    base = {
        "name": name,
        "quota": 0,
        "gender_restriction": "",
        "branch_category": BRANCH_DIGER,
        "single_slot": False,
        "pool": False,
        "ebelik_priority": normalize_key(name) in {
            normalize_key(k) for k in EBELIK_PRIORITY_KEYS
        },
        "must_fill": False,
        "intensity": "",
        "reserve": gray or "İHTİYAÇ OLURSA" in spec_up,
    }
    # branş
    key = normalize_key(name)
    if "CERRAHİ BRANŞ" in spec_up:
        base["branch_category"] = BRANCH_CERRAHI
    elif "DAHİLİ BRANŞ" in spec_up:
        base["branch_category"] = BRANCH_DAHILI
    elif key.startswith("YB"):
        base["branch_category"] = BRANCH_YOGUN_BAKIM
    elif "PALYATİF" in key:
        base["branch_category"] = BRANCH_PALYATIF
    elif "DOĞUM SALONU" in key:
        base["branch_category"] = BRANCH_DOGUM_SALONU
    # yoğunluk
    if "YOĞUN BÖLÜM" in spec_up or key.startswith("YB"):
        base["intensity"] = INTENSITY_YOGUN
    elif "HAFİF BÖLÜM" in spec_up:
        base["intensity"] = INTENSITY_HAFIF

    # kontenjan / cinsiyet
    if "BİR KIZ, BİR ERKEK" in spec_up:  # k/e çifti (madde 17)
        out = []
        for g in ("K", "E"):
            d = dict(base)
            d.update(quota=1, gender_restriction=g, must_fill=True,
                     single_slot=True)
            out.append(d)
        return out
    m = re.search(r"(\d+)\s*ÖĞRENCİ", spec_up)
    if "BİR VEYA İKİ" in spec_up:
        base["quota"] = 2
    elif m:
        base["quota"] = int(m.group(1))
    elif "İKİ ÖĞRENCİ" in spec_up:
        base["quota"] = 2
    elif "BİR" in spec_up and "ÖĞRENCİ" in spec_up:
        base["quota"] = 1
        if "ERKEK" in spec_up:
            base["gender_restriction"] = "E"
        elif "KIZ" in spec_up:
            base["gender_restriction"] = "K"
    if base["quota"] == 0:
        if base["reserve"]:
            base["quota"] = 1  # ihtiyaç olursa: 1 kişilik yedek kapasite
        else:
            # kontenjan yazmayan kat servisi / acil / YB → havuz birimi
            base["quota"] = POOL_QUOTA_DEFAULT
            base["pool"] = True
    base["single_slot"] = base["quota"] == 1 and not base["reserve"] and not base["pool"]
    return [base]


def main() -> None:
    wb = openpyxl.load_workbook(SOURCE)
    ws = wb.worksheets[0]
    entries: list[dict] = []
    for row in ws.iter_rows(min_row=3):
        name = row[0].value
        if not name or not str(name).strip():
            continue
        spec = str(row[1].value or "")
        fill = row[0].fill
        gray = bool(fill and fill.patternType == "solid")
        entries += parse_row(str(name), spec, gray)

    # her iki grup için aynı katalog (gerçek belgelerde iki grup aynı
    # birim listesine sahip)
    out = []
    for group in (1, 2):
        for e in entries:
            d = dict(e)
            d["group"] = group
            out.append(d)
    TARGET.write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"{len(entries)} birim tanımı ({len(out)} kayıt, 2 grup) → {TARGET}")


if __name__ == "__main__":
    main()
