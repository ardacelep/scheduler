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
CORE_BRANCHES = (BRANCH_DAHILI, BRANCH_CERRAHI, BRANCH_YOGUN_BAKIM, BRANCH_PALYATIF)

# Öğrenci bölüm türü (madde 7, 18)
PROGRAM_HEMSIRELIK = "hemsirelik"
PROGRAM_EBELIK = "ebelik"
PROGRAM_DIGER = "diger"
PROGRAMS = (PROGRAM_HEMSIRELIK, PROGRAM_EBELIK, PROGRAM_DIGER)
PROGRAM_LABELS = {
    PROGRAM_HEMSIRELIK: "Hemşirelik",
    PROGRAM_EBELIK: "Ebelik",
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
    "solver": {
        "time_limit_seconds": 30,
        # Yumuşak kısıt ağırlıkları — değişebilir detaylar, sabit kodlanmadı
        "weights": {
            "pool_balance": 5,        # madde 4: havuz birimlerine eşit dağılım
            "repeat_pair": 3,         # madde 19: tekrar eden ikili cezası
            "ebelik_priority": 20,    # madde 18
            "core_branch_early": 2,   # madde 6/7'yi erken aylarda karşılama bonusu
            "single_slot_fill": 50,   # madde 4: tekli birimler boş kalmasın
        },
    },
}
