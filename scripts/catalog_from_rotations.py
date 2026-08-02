"""Elle yapılmış rotasyon dosyalarından varsayılan birim kataloğunu üretir.

    python scripts/catalog_from_rotations.py

Kaynak: `example/{AB-CD,AC-BD,AD-BC} ROTASYON.xlsx` — eğitim hemşiresinin
2026-2027 için hazırladığı üç sınıf-eşleştirme senaryosu. Her sayfanın
öğrenci listesinin ALTINDA yetkili bir özellik bloğu var:

    | birim adı (k/e ekli) | kontenjan (yazıyla) | özellikler… |
    | 3.KAT NOR.           | 2 ÖĞRENCİ           | DAHİLİ BRANŞ |
    | ALÇI ODASI e         | 1 ERKEK ÖĞRENCİ     | HAFİF BÖLÜM |
    | ECZANE  SARF e       | BU GRUPTA ÖĞRENCİ VERME |         |

Bu script `build_catalog.py`'nin yerini alır. Eski script "BÖLÜMLER VE
ÖZELLİKLERİ.xlsx"i okuyordu; o belge KONTENJAN VERMİYOR, bu yüzden havuz
birimlerine `POOL_QUOTA_DEFAULT = 3` diye TAHMİN yazılıyordu. Gerçek
rotasyonlar kat servislerinin 1-2 kişi aldığını gösteriyor — katalog
gerçeğin iki-üç katıydı.

Belge gitignore'lu (`example/`, kişisel veri içerir); bu script yalnız
geliştirme makinesinde koşar. Ürettiği JSON kişisel veri İÇERMEZ ve depoya
girer.

## Kontenjan kararı: senaryolar arası MAKSİMUM

Sekiz birim (kat servisleri + ACİL + FTR) grup büyüklüğüne göre 1↔2
oynuyor: büyük grup (36-38 kişi) 2, küçük grup (26-30) 1 alıyor. Katalog
sezon başlangıç şablonu olduğundan **maksimum** yazılır, çünkü kontenjan bir
ÜST SINIRDIR (aşılmaz, dolmak zorunda değil):

* büyük grupta kullanıcının yaptığı dağılım birebir sığar,
* küçük grupta çözücü hepsini doldurmaz — havuz politikası kalanı zaten
  dengeli dağıtır, bir zarar yoktur.

Tersi (minimum yazmak) büyük grubu kapasitesiz bırakır ve kullanıcıyı her
sezon sekiz kontenjanı elle yükseltmeye zorlar.
"""
import json
import re
import sys
from collections import defaultdict
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
    PROGRAM_EBELIK,
    Requirement,
    SCOPE_ALL,
    SCOPE_PROGRAM,
    Unit,
)
from rotasyon.normalize import normalize_key, normalize_unit_name, parse_cell  # noqa: E402

SOURCES = [
    ROOT / "example" / f"{ad} ROTASYON.xlsx"
    for ad in ("AB-CD", "AC-BD", "AD-BC")
]
TARGET = ROOT / "rotasyon" / "data" / "default_units.json"
TARGET_REQ = ROOT / "rotasyon" / "data" / "default_requirements.json"
SHEETS = {"PSÇ": 1, "ÇPC": 2}

# Belgelerin altındaki yazılı kurallar — altı sayfanın dördü BİREBİR aynı,
# beşincisi (D sınıfı doğum) D sınıfının bulunduğu sayfada. Sırayla:
#
#   "10 AYLIK SEZON SONUNDA HER BİR ÖĞRENCİ BİRER DEFA YOĞUN BÖLÜM,
#    DAHİLİ BRANŞ VE CERRAHİ BRANŞ GÖRMÜŞ OLMALI"
#   "…BİRER DEFA YB/B, YB/C, YB/D GÖRMÜŞ OLMALI"        → üçünden BİRİ
#   "…BİRER DEFA 5.KAT PALYATİF VEYA 7.KAT PALYATİF…"    → ikisinden biri
#   "BİR ÖĞRENCİ PEŞ PEŞE YOĞUN/HAFİF BÖLÜME VERİLMEYECEK"
#   "PEMBE RENKLİ D SINIFI ÖĞRENCİLERİ BİRER DEFA DOĞ.SAL-Y.DOĞ'YI VE
#    2.KAT DOĞUM SERVİSİ'Yİ GÖRMÜŞ OLMALI"              → İKİSİ DE ("VE")
#
# Son kural gereksinim DEĞİL, birim yoğunluğuyla (intensity) uygulanır —
# peş peşe yoğun/hafif yasağı motorda madde 20.
#
# "D sınıfı" yerine **program = ebelik** yazılır: kullanıcı D sınıfının
# ebelik öğrencileri olduğunu doğruladı ve gerçek veride birebir örtüşüyor
# (26-27: sınıf D = 8 öğrenci, hepsi ebelik). Program kapsamı sınıf ADINA
# bağımlı olmadığı için sonraki sezonlarda da geçerli kalır.
VARSAYILAN_GEREKSINIMLER = [
    ("Cerrahi branş", ["1.KAT CERR", "6.KAT CERR"], 1, None),
    ("Dahili branş", ["3.KAT NOR", "4.KAT DAHİLİYE", "ZEMİN ENF+DAH"], 1, None),
    ("Yoğun bölüm", ["5.KAT PALYATİF", "6.KAT CERR", "7.KAT PALYATİF", "ACİL",
                     "YB/B", "YB/C", "YB/D"], 1, None),
    ("Yoğun bakım (YB/B-C-D'den biri)", ["YB/B", "YB/C", "YB/D"], 1, None),
    ("Palyatif (5. veya 7. kat)", ["5.KAT PALYATİF", "7.KAT PALYATİF"], 1, None),
    ("Ebelik → doğum (ikisi de)",
     ["DOĞUM SALONU-YENİ DOĞAN", "2.KAT DOĞUM"], 2, PROGRAM_EBELIK),
]

# Belgede kısaltılmış yazımlar → katalogdaki kanonik ad.
KANONIK = {
    "2.KAT DOĞUM SERVİSİ": "2.KAT DOĞUM",
    "4.KAT DAH": "4.KAT DAHİLİYE",
    "DOĞ.SAL-Y.DOĞ": "DOĞUM SALONU-YENİ DOĞAN",
    "FTR ÜNİT": "FTR.ÜNİT",
    "KÜÇÜK CERR ODASI": "KÜÇÜK CERRAHİ ODASI",
}

# Belge yalnız CERRAHİ/DAHİLİ BRANŞ yazıyor. Branş artık bir KURAL değil,
# gereksinim kurarken birimleri hızlı seçmeye yarayan bir etiket (bkz.
# rotasyon/requirements.py); bu yüzden ada göre anlaşılan diğer kategoriler
# de korunur — liste daha kullanışlı olur, davranışı etkilemez.
BRANS_ADA_GORE = {
    "5.KAT PALYATİF": BRANCH_PALYATIF,
    "7.KAT PALYATİF": BRANCH_PALYATIF,
    "YB/B": BRANCH_YOGUN_BAKIM,
    "YB/C": BRANCH_YOGUN_BAKIM,
    "YB/D": BRANCH_YOGUN_BAKIM,
    "DOĞUM SALONU-YENİ DOĞAN": BRANCH_DOGUM_SALONU,
    "2.KAT DOĞUM": BRANCH_DOGUM_SALONU,
}

# Ebelik öncelikli birimler (madde 18): doğum/yenidoğan ilişkili olanlar.
EBELIK_ONCELIKLI = {"DOĞUM SALONU-YENİ DOĞAN", "2.KAT DOĞUM"}

# Belge doldurma POLİTİKASI yazmıyor. Kontenjan davranışından çıkarılır:
# grup büyüklüğüne göre oynayan birimler fazlalığı emen HAVUZ'dur; sabit
# kontenjanlı uzmanlık birimleri "mümkünse dolsun".
HAVUZ_ADAY = {
    "1.KAT CERR", "3.KAT NOR", "4.KAT DAHİLİYE", "5.KAT PALYATİF",
    "6.KAT CERR", "7.KAT PALYATİF", "ACİL", "FTR.ÜNİT",
    "DİŞ", "LABORATUVAR", "2.KAT ÇOCUK",
}


# Bu üç senaryoda hiç kullanılmayan ama hastanede var olan birimler
# ("BÖLÜMLER VE ÖZELLİKLERİ.xlsx" belgesinden geliyorlar). PASİF eklenirler:
# üç senaryo dosyasına bakıp gerçek birimleri katalogdan tamamen silmek aşırı
# uyarlama olurdu; pasif kayıt çözücüyü etkilemez, kullanıcı gerekirse
# Kapasite Planı'ndan tek tıkla açar.
BELGEDE_YOK = [
    ("YB/A", 1, BRANCH_YOGUN_BAKIM, INTENSITY_YOGUN),
    ("ÜROLOJİ POLK", 1, BRANCH_DIGER, ""),
]


def kontenjan(metin: str) -> int:
    """"2 ÖĞRENCİ" → 2 · "BU GRUPTA ÖĞRENCİ VERME" → 0 (o grupta pasif)."""
    t = str(metin).upper()
    if "VERME" in t:
        return 0
    m = re.search(r"(\d+)", t)
    return int(m.group(1)) if m else 1


def oku() -> dict:
    """(kanonik ad, grup) → {"quota": max, "gender": …, "ozellik": {…}}"""
    veri: dict[tuple[str, int], dict] = defaultdict(
        lambda: {"quota": 0, "gender": "", "ozellik": set()}
    )
    for src in SOURCES:
        if not src.exists():
            raise SystemExit(f"Kaynak bulunamadı: {src}")
        wb = openpyxl.load_workbook(src, data_only=True)
        for sheet, grup in SHEETS.items():
            ws = wb[sheet]
            for r in range(1, ws.max_row + 1):
                ad, kot = ws.cell(r, 2).value, ws.cell(r, 3).value
                if not ad or not kot:
                    continue
                ku = str(kot).upper()
                # Özellik bloğunun imzası: kontenjan hücresi "ÖĞRENCİ" ya da
                # "…VERME" içerir. Öğrenci listesindeki ay hücreleri içermez.
                if "ÖĞRENCİ" not in ku and "VERME" not in ku:
                    continue
                if "SOYAD" in str(ad).upper():
                    continue
                p = parse_cell(str(ad))
                temiz = normalize_unit_name(p.base_name)
                kanon = KANONIK.get(normalize_key(temiz), temiz)
                kayit = veri[(kanon, grup)]
                kayit["quota"] = max(kayit["quota"], kontenjan(kot))
                if p.gender_suffix:
                    kayit["gender"] = p.gender_suffix
                for c in range(4, 9):
                    v = ws.cell(r, c).value
                    if v not in (None, ""):
                        kayit["ozellik"].add(str(v).strip().upper())
    return veri


def birim_kur(ad: str, grup: int, k: dict) -> Unit:
    oz = k["ozellik"]
    if "CERRAHİ BRANŞ" in oz:
        brans = BRANCH_CERRAHI
    elif "DAHİLİ BRANŞ" in oz:
        brans = BRANCH_DAHILI
    else:
        brans = BRANS_ADA_GORE.get(ad, BRANCH_DIGER)

    if "YOĞUN BÖLÜM" in oz:
        yogunluk = INTENSITY_YOGUN
    elif "HAFİF BÖLÜM" in oz:
        yogunluk = INTENSITY_HAFIF
    else:
        yogunluk = ""

    havuz = ad in HAVUZ_ADAY
    return Unit(
        name=ad,
        group=grup,
        # kontenjan 0 = "bu grupta öğrenci verme" → pasif, ama kontenjanı
        # 1'e çekilir ki kullanıcı aktifleştirdiğinde kullanılabilir olsun
        quota=max(1, k["quota"]),
        active=k["quota"] > 0,
        gender_restriction=k["gender"],
        branch_category=brans,
        intensity=yogunluk,
        pool=havuz,
        single_slot=not havuz,
        ebelik_priority=ad in EBELIK_ONCELIKLI,
        must_fill=False,   # belge hiçbir birim için "tam dolmalı" demiyor
        reserve=False,     # "yedek" ayrımı da belgede yok
    )


def main() -> int:
    veri = oku()
    units = [birim_kur(ad, g, veri[(ad, g)]) for (ad, g) in sorted(veri)]
    for ad, kota, brans, yog in BELGEDE_YOK:
        for g in (1, 2):
            units.append(
                Unit(
                    name=ad, group=g, quota=kota, active=False,
                    branch_category=brans, intensity=yog, single_slot=True,
                )
            )
    units.sort(key=lambda u: (u.name, u.group))
    payload = []
    for u in units:
        d = u.to_dict()
        d.pop("id", None)  # id dosyada TUTULMAZ, her yüklemede taze üretilir
        payload.append(d)
    TARGET.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    # --- varsayılan gereksinimler ---
    var_adlar = {normalize_key(u.name) for u in units}
    reqs = []
    for ad, birimler, minc, program in VARSAYILAN_GEREKSINIMLER:
        eksik = [b for b in birimler if normalize_key(b) not in var_adlar]
        if eksik:
            raise SystemExit(
                f"'{ad}' gereksinimi katalogda olmayan birim istiyor: {eksik}"
            )
        reqs.append(
            Requirement(
                name=ad,
                scope=SCOPE_PROGRAM if program else SCOPE_ALL,
                scope_value=program or "",
                unit_keys=[normalize_key(b) for b in birimler],
                min_count=minc,
                note="Elle hazırlanmış rotasyon belgelerindeki yazılı kural.",
            )
        )
    req_payload = []
    for r in reqs:
        d = r.to_dict()
        d.pop("id", None)  # id dosyada tutulmaz, her yüklemede taze
        req_payload.append(d)
    TARGET_REQ.write_text(
        json.dumps(req_payload, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"{TARGET_REQ.relative_to(ROOT)}: {len(reqs)} gereksinim")
    for r in reqs:
        kim = "ebelik" if r.scope == SCOPE_PROGRAM else "tüm öğrenciler"
        print(f"  · {r.name} ({kim}, en az {r.min_count})")

    aktif = sum(1 for u in units if u.active)
    print(f"{TARGET.relative_to(ROOT)}: {len(units)} kayıt ({aktif} aktif)")
    for g in (1, 2):
        gu = [u for u in units if u.group == g and u.active]
        print(f"  grup {g}: {len(gu)} aktif birim, toplam kontenjan "
              f"{sum(u.quota for u in gu)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
