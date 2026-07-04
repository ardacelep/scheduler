"""Veri modeli: öğrenci, birim, sınıf, atama.

Kullanıcıya görünen her metin Türkçe; alan/fonksiyon adları İngilizce.
Aylar ve kural ağırlıkları sabit kodlanmaz, settings üzerinden gelir.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional

# Cinsiyet
FEMALE = "K"
MALE = "E"
GENDERS = (FEMALE, MALE)
GENDER_LABELS = {FEMALE: "Kız", MALE: "Erkek"}

# Branş kategorileri (madde 6, 7). "diger" hiçbir zorunluluğu karşılamaz.
BRANCH_DAHILI = "dahili"
BRANCH_CERRAHI = "cerrahi"
BRANCH_YOGUN_BAKIM = "yogun_bakim"
BRANCH_PALYATIF = "palyatif"
BRANCH_DOGUM_SALONU = "dogum_salonu"
BRANCH_DIGER = "diger"
BRANCH_CATEGORIES = (
    BRANCH_DAHILI,
    BRANCH_CERRAHI,
    BRANCH_YOGUN_BAKIM,
    BRANCH_PALYATIF,
    BRANCH_DOGUM_SALONU,
    BRANCH_DIGER,
)
BRANCH_LABELS = {
    BRANCH_DAHILI: "Dahili",
    BRANCH_CERRAHI: "Cerrahi",
    BRANCH_YOGUN_BAKIM: "Yoğun Bakım",
    BRANCH_PALYATIF: "Palyatif",
    BRANCH_DOGUM_SALONU: "Doğum Salonu",
    BRANCH_DIGER: "Diğer",
}
# Madde 6: Haziran'a kadar her öğrenci bu kategorilerden en az birini görmüş olmalı.
# (Eski birleşik kural; yeni ayrıntılı zorunluluklar DEFAULT_SETTINGS
# "season_requirements" listesinde branş bazında tanımlanır.)
CORE_BRANCHES = (BRANCH_DAHILI, BRANCH_CERRAHI, BRANCH_YOGUN_BAKIM, BRANCH_PALYATIF)

# Birim yoğunluğu ("BÖLÜMLER VE ÖZELLİKLERİ" belgesi): bir öğrenci peş peşe
# iki ay yoğun bölüme ya da peş peşe iki ay hafif bölüme verilmez.
INTENSITY_YOGUN = "yogun"
INTENSITY_HAFIF = "hafif"
INTENSITIES = ("", INTENSITY_YOGUN, INTENSITY_HAFIF)
INTENSITY_LABELS = {"": "—", INTENSITY_YOGUN: "Yoğun", INTENSITY_HAFIF: "Hafif"}

# Öğrenci bölüm türü (madde 7, 18). SML listelerindeki ALAN/DAL karşılıkları:
# "Hemşire Yardımcılığı" → hemsirelik, "Ebe Yardımcılığı" → ebelik,
# "Sağlık Bakım Teknisyenliği" → saglik_bakim.
PROGRAM_HEMSIRELIK = "hemsirelik"
PROGRAM_EBELIK = "ebelik"
PROGRAM_SAGLIK_BAKIM = "saglik_bakim"
PROGRAM_DIGER = "diger"
PROGRAMS = (
    PROGRAM_HEMSIRELIK,
    PROGRAM_EBELIK,
    PROGRAM_SAGLIK_BAKIM,
    PROGRAM_DIGER,
)
PROGRAM_LABELS = {
    PROGRAM_HEMSIRELIK: "Hemşire Yardımcılığı",
    PROGRAM_EBELIK: "Ebe Yardımcılığı",
    PROGRAM_SAGLIK_BAKIM: "Sağlık Bakım Teknisyenliği",
    PROGRAM_DIGER: "Diğer",
}

# Ebelik öncelikli birimler (madde 18) birim üzerinde bayrakla işaretlenir:
# dogum salonu, yenidoğan, doğum servisi.


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class ClassGroup:
    """Sınıf (A/B/C/D...). Sayısı ve adları kullanıcı tanımlı (madde 13)."""

    name: str
    color_hex: str = ""  # "#RRGGBB"; yıllık görünümde öğrenci hücresi bu renge boyanır
    id: str = field(default_factory=_new_id)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ClassGroup":
        return cls(**d)


@dataclass
class Student:
    full_name: str
    gender: str  # K / E
    group: int  # 1 veya 2 (madde 5: gruplar bağımsız)
    class_name: str = ""  # ClassGroup.name referansı
    program: str = PROGRAM_HEMSIRELIK
    student_no: str = ""  # föy no / okul numarası (gerçek belgelerde var)
    banned_unit_ids: list[str] = field(default_factory=list)  # madde 8
    dis_exempt: bool = False  # madde 9: Diş Pol'e verilmez
    note: str = ""  # madde 10: özel durum, kural motorunu etkilemez
    id: str = field(default_factory=_new_id)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Student":
        return cls(**d)


@dataclass
class Unit:
    name: str
    group: int  # 1, 2 veya 0 = her iki grupta da var
    quota: int = 1  # aylık kontenjan (madde 12: düzenlenebilir)
    gender_restriction: str = ""  # "K", "E" veya "" (madde 2, 3)
    branch_category: str = BRANCH_DIGER
    single_slot: bool = False  # madde 4: önce doldurulan tekli birimler
    pool: bool = False  # madde 4: kat/YB/FTR/acil eşit dağıtım havuzu
    ebelik_priority: bool = False  # madde 18: ebelik öğrencisi öncelikli
    must_fill: bool = False  # madde 17: kontenjan tam dolmak zorunda (FTR k/e çifti)
    active: bool = True  # listeden çıkarmak yerine pasifleştirme
    intensity: str = ""  # "yogun"/"hafif"/"" — peş peşe yasağı (madde 20)
    reserve: bool = False  # gri/yedek birim: yalnız ihtiyaç olursa öğrenci verilir
    id: str = field(default_factory=_new_id)

    @property
    def display_name(self) -> str:
        """Kullanıcıya/Excel'e gösterilen ad: cinsiyet kısıtı ekiyle."""
        if self.gender_restriction == "K":
            return f"{self.name} k"
        if self.gender_restriction == "E":
            return f"{self.name} e"
        return self.name

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Unit":
        return cls(**d)


@dataclass
class Assignment:
    student_id: str
    month: str  # settings.months içindeki ad (örn. "EYLÜL")
    unit_id: str
    day_note: str = ""  # madde 11: "Çrş günleri üro.pol" gibi serbest metin
    locked: bool = False  # yarı otomatik modda elle sabitlenen hücre
    id: str = field(default_factory=_new_id)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Assignment":
        return cls(**d)


# ---- Kullanıcı tanımlı (özel) kurallar ----
# Yerleşik 19 kuralın dışında, arayüzden eklenebilen parametrik kurallar.
RULE_AYRI_TUT = "ayri_tut"  # seçilen öğrenciler aynı ay aynı birimde olamaz
RULE_BIRLIKTE_TUT = "birlikte_tut"  # seçilen öğrenciler her ay aynı birimde olur
RULE_SABIT_ATAMA = "sabit_atama"  # öğrenci X, ay Y'de birim Z'ye atanır
CUSTOM_RULE_TYPES = (RULE_AYRI_TUT, RULE_BIRLIKTE_TUT, RULE_SABIT_ATAMA)
CUSTOM_RULE_LABELS = {
    RULE_AYRI_TUT: "Ayrı tut — seçilen öğrenciler aynı birime düşmesin",
    RULE_BIRLIKTE_TUT: "Birlikte tut — seçilen öğrenciler hep aynı birimde olsun",
    RULE_SABIT_ATAMA: "Sabit atama — öğrenci belirli ayda belirli birime gitsin",
}


@dataclass
class CustomRule:
    type: str  # CUSTOM_RULE_TYPES
    student_ids: list[str] = field(default_factory=list)  # ayrı/birlikte: ≥2, sabit: 1
    unit_id: str = ""  # sabit_atama için
    month: str = ""  # sabit_atama için
    note: str = ""
    active: bool = True
    id: str = field(default_factory=_new_id)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CustomRule":
        return cls(**d)


DEFAULT_MONTHS = [
    "EYLÜL", "EKİM", "KASIM", "ARALIK", "OCAK",
    "ŞUBAT", "MART", "NİSAN", "MAYIS", "HAZİRAN",
]

DEFAULT_SETTINGS: dict = {
    "months": DEFAULT_MONTHS,
    # Tek-ay görünümünde grup başlığında gösterilen haftalık gün etiketi
    # (madde 15, ÖRN.TEK AY HALİ formatı) — JSON anahtarları str tutulur
    "day_labels": {"1": "Pazartesi-Salı-Çarşamba", "2": "Çarşamba-Perşembe-Cuma"},
    # FTR kuralı (madde 17) solver'da birim adına değil bu bayrağa göre çalışır:
    # gender_restriction'lı iki ayrı FTR birimi (k/e) tanımlanır, ikisinin de
    # dolu olması sağlanır. Bu ayar sadece uyarı eşiği vb. için yer tutucu.
    # Sezon sonuna kadar HER öğrencinin görmüş olması gereken branşlar
    # ("BÖLÜMLER VE ÖZELLİKLERİ" belgesi): bir cerrahi, bir dahili, bir
    # yoğun bakım (YB/B-C-D) ve bir palyatif. Liste serbestçe düzenlenebilir;
    # ebelik→doğum salonu zorunluluğu (madde 7) ayrıca her zaman uygulanır.
    "season_requirements": [
        {"branch": BRANCH_CERRAHI},
        {"branch": BRANCH_DAHILI},
        {"branch": BRANCH_YOGUN_BAKIM},
        {"branch": BRANCH_PALYATIF},
    ],
    "solver": {
        # Ölçüm: en iyi çözüm ilk 1-2 saniyede bulunuyor, kalan süre yalnız
        # optimallik kanıtına gidiyor (skor 60 sn'de bile değişmedi).
        # Eski/yavaş bilgisayarlarda da akıcı kalsın diye 5 sn yeterli.
        "time_limit_seconds": 5,
        # Toplu üretimde bütün sezonu tek modelde çözen ortak çözücünün süre
        # sınırı (solve_season). Model ay-bazlıdan büyük olduğu için daha
        # geniş; süre dolarsa açgözlü ay-bazlı yola geri düşülür.
        "season_time_limit_seconds": 60,
        # Paralel arama worker sayısı. 1 bırakın: bu boyuttaki modellerde tek
        # worker daha hızlı VE macOS'ta pyarrow ile absl deadlock'unu önlüyor.
        "num_workers": 1,
        # Yumuşak kısıt ağırlıkları — değişebilir detaylar, sabit kodlanmadı
        # Ölçüm (74 öğrencilik gerçek sezon, tam sezon çözümü): repeat_pair
        # 3→10 tekrar eden ikili sayısını 8'den 1'e, gender_balance 2→6
        # (repeat_pair=10 ile birlikte) K/E uyarısını 17'den 9'a düşürdü;
        # başka bir kuralda gerileme olmadı.
        "weights": {
            "pool_balance": 5,        # madde 4: havuz birimlerine eşit dağılım
            "repeat_pair": 10,        # madde 19: tekrar eden ikili cezası
            "ebelik_priority": 20,    # madde 18
            "core_branch_early": 2,   # madde 6/7'yi erken aylarda karşılama bonusu
            "single_slot_fill": 50,   # madde 4: tekli birimler boş kalmasın
            "reserve_use": 15,        # gri/yedek birim yalnız ihtiyaç olursa
            "gender_balance": 6,      # havuz birimlerinde kız/erkek dengesi
        },
    },
}
