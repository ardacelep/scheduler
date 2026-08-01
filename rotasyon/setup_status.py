"""Sezon kurulum durumu — sihirbazın "nerede kaldım?" mantığı.

Kullanıcı bir sezonu kurarken beş şeyi sırayla yapar: öğrencileri getir,
sınıfları gruplara dağıt, birim kapasitesini ayarla, gereksinimleri tanımla,
rotasyonu üret. Bu adımlar uygulamada ayrı ekranlara dağılmış durumda ve
kullanıcı hangisini yaptığını/atladığını takip etmek zorunda kalıyordu.

Bu modül her adımın durumunu VERİDEN türetir — kullanıcının işaretlemesine
gerek yok, "tamamlandı" demek gerçekten tamamlanmış demektir. Streamlit'e
bağımlı değildir, saf mantıktır.
"""
from __future__ import annotations

from dataclasses import dataclass

from .fill_policy import group_capacity_plan
from .models import SEVERITY_REQUIRED

# Adım durumları
STATE_DONE = "tamam"  # yapılmış, sorun yok
STATE_WARN = "dikkat"  # yapılmış ama düzeltilmesi gereken bir şey var
STATE_TODO = "eksik"  # henüz yapılmamış
STATE_BLOCKED = "bekliyor"  # önceki adım bitmeden anlamı yok

STATE_ICONS = {
    STATE_DONE: "✅",
    STATE_WARN: "⚠️",
    STATE_TODO: "⭕",
    STATE_BLOCKED: "🔒",
}


@dataclass
class SetupStep:
    key: str
    title: str
    state: str
    detail: str  # tek cümlelik durum açıklaması
    page: str  # gidilecek ekranın url_path'i
    action: str  # bağlantı etiketi

    @property
    def icon(self) -> str:
        return STATE_ICONS.get(self.state, "•")

    @property
    def done(self) -> bool:
        return self.state == STATE_DONE


def _students_step(students) -> SetupStep:
    active = [s for s in students if getattr(s, "active", True)]
    if not active:
        return SetupStep(
            "ogrenciler", "Öğrencileri getir", STATE_TODO,
            "Henüz öğrenci yok. Sezon başındaki listeyi Excel'den aktarın ya "
            "da elle girin.",
            "excel", "Excel'den içe aktar",
        )
    eksik = [s.full_name for s in active if not s.gender]
    if eksik:
        ornek = ", ".join(eksik[:3]) + ("…" if len(eksik) > 3 else "")
        return SetupStep(
            "ogrenciler", "Öğrencileri getir", STATE_WARN,
            f"{len(active)} öğrenci var ama {len(eksik)} tanesinin cinsiyeti "
            f"eksik ({ornek}). Cinsiyet kısıtlı birimler için gerekli.",
            "veri-yonetimi", "Veri Yönetimi'nde tamamla",
        )
    return SetupStep(
        "ogrenciler", "Öğrencileri getir", STATE_DONE,
        f"{len(active)} öğrenci hazır.", "veri-yonetimi", "Listeyi gör",
    )


def _groups_step(students, classes) -> SetupStep:
    active = [s for s in students if getattr(s, "active", True)]
    if not active:
        return SetupStep(
            "gruplar", "Sınıfları gruplara dağıt", STATE_BLOCKED,
            "Önce öğrenciler gelmeli.", "veri-yonetimi", "Veri Yönetimi",
        )
    sizes: dict[int, int] = {}
    for s in active:
        sizes[s.group] = sizes.get(s.group, 0) + 1
    # NOT: metinler "Grup 1" diye yazılır, "1. grup" diye DEĞİL — Markdown
    # satır başındaki "1." ifadesini sıralı liste madde işareti sanıp numarayı
    # yutuyor ve girinti ekliyor.
    if len(sizes) < 2:
        tek = next(iter(sizes))
        return SetupStep(
            "gruplar", "Sınıfları gruplara dağıt", STATE_WARN,
            f"Bütün öğrenciler grup {tek}'de. Sınıfları iki gruba dağıtmanız "
            "gerekiyor.",
            "veri-yonetimi", "Sınıf → grup eşleştirmesi",
        )
    ozet = " · ".join(f"Grup {g}: {n} öğrenci" for g, n in sorted(sizes.items()))
    return SetupStep(
        "gruplar", "Sınıfları gruplara dağıt", STATE_DONE, ozet,
        "veri-yonetimi", "Eşleştirmeyi değiştir",
    )


def _capacity_step(students, units) -> SetupStep:
    if not units:
        return SetupStep(
            "kapasite", "Birim kapasitesini ayarla", STATE_TODO,
            "Henüz birim yok. Varsayılan katalogdan başlayabilirsiniz.",
            "veri-yonetimi", "Birim ekle",
        )
    active_students = [s for s in students if getattr(s, "active", True)]
    if not active_students:
        return SetupStep(
            "kapasite", "Birim kapasitesini ayarla", STATE_BLOCKED,
            "Kapasite matematiği öğrenci sayısına göre hesaplanır; önce "
            "öğrenciler gelmeli.",
            "kapasite-plani", "Kapasite Planı",
        )
    uyarilar = []
    for g in sorted({s.group for s in active_students}):
        uyarilar += group_capacity_plan(units, active_students, g).warnings
    if uyarilar:
        return SetupStep(
            "kapasite", "Birim kapasitesini ayarla", STATE_WARN,
            f"{len(uyarilar)} sorun var: {uyarilar[0]}",
            "kapasite-plani", "Kapasite Planı'nda düzelt",
        )
    n_aktif = sum(1 for u in units if u.active)
    return SetupStep(
        "kapasite", "Birim kapasitesini ayarla", STATE_DONE,
        f"{n_aktif} aktif birim; kontenjanlar öğrenci sayısına oturuyor.",
        "kapasite-plani", "Planı gözden geçir",
    )


def _requirements_step(requirements, units) -> SetupStep:
    if not units:
        return SetupStep(
            "gereksinimler", "Gereksinimleri tanımla", STATE_BLOCKED,
            "Önce birimler tanımlanmalı.", "gereksinimler", "Gereksinimler",
        )
    aktif = [r for r in requirements if r.active]
    if not aktif:
        return SetupStep(
            "gereksinimler", "Gereksinimleri tanımla", STATE_TODO,
            "Henüz gereksinim yok. Kimin hangi birimleri görmesi gerektiğini "
            "belirleyin (mevcut ayarlarınızdan otomatik liste de üretilebilir).",
            "gereksinimler", "Gereksinimleri kur",
        )
    zorunlu = sum(1 for r in aktif if r.severity == SEVERITY_REQUIRED)
    tercih = len(aktif) - zorunlu
    ozet = f"{zorunlu} zorunlu" + (f", {tercih} tercih" if tercih else "")
    return SetupStep(
        "gereksinimler", "Gereksinimleri tanımla", STATE_DONE,
        f"{ozet} gereksinim tanımlı.", "gereksinimler", "Gereksinimleri düzenle",
    )


def _generate_step(students, assignments, months) -> SetupStep:
    active = [s for s in students if getattr(s, "active", True)]
    if not active or not months:
        return SetupStep(
            "uret", "Rotasyonu üret", STATE_BLOCKED,
            "Önceki adımlar tamamlanmalı.", "yillik-tablo", "Yıllık Tablo",
        )
    ids = {s.id for s in active}
    dolu = {a.month for a in assignments if a.student_id in ids}
    kalan = [m for m in months if m not in dolu]
    if not dolu:
        return SetupStep(
            "uret", "Rotasyonu üret", STATE_TODO,
            f"Sezonun {len(months)} ayı da boş. Yıllık Tablo'dan tek seferde "
            "üretebilirsiniz.",
            "yillik-tablo", "Yıllık Tablo'da üret",
        )
    if kalan:
        return SetupStep(
            "uret", "Rotasyonu üret", STATE_WARN,
            f"{len(dolu)}/{len(months)} ay üretilmiş; sıradaki: {kalan[0]}.",
            "yillik-tablo", "Devam et",
        )
    return SetupStep(
        "uret", "Rotasyonu üret", STATE_DONE,
        f"Sezonun {len(months)} ayı da üretilmiş.",
        "yillik-tablo", "Tabloyu aç",
    )


def setup_steps(
    students, units, classes, requirements, assignments, settings
) -> list[SetupStep]:
    """Kurulumun beş adımı, sırayla. Durumlar tamamen veriden türetilir."""
    months = (settings or {}).get("months", [])
    return [
        _students_step(students),
        _groups_step(students, classes),
        _capacity_step(students, units),
        _requirements_step(requirements, units),
        _generate_step(students, assignments, months),
    ]


def progress(steps) -> tuple[int, int]:
    """(tamamlanan, toplam) — ilerleme çubuğu için."""
    return sum(1 for s in steps if s.done), len(steps)


def first_actionable(steps):
    """Kullanıcının şu an ilgilenmesi gereken ilk adım (yoksa None)."""
    for s in steps:
        if s.state in (STATE_TODO, STATE_WARN):
            return s
    return None
