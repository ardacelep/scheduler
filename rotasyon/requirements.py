"""Gereksinim derleme katmanı (v2 kural modeli).

Bir `Requirement` kullanıcının cümlesidir: *"KİME — HANGİ BİRİMLERDEN — KAÇ
KEZ"*. Çözücü ve denetleyicinin ihtiyacı olan ise somut bir şeydir: **bu
öğrenci için hangi birim id'leri bu gereksinimi karşılar**. Bu modül o
çeviriyi yapar; Streamlit'e ve OR-Tools'a bağımlı değildir, saf mantıktır.

Çeviri iki adımdır:

1. `applies_to` — gereksinim bu öğrenciyi kapsıyor mu? (kapsam/scope)
2. `compile_for_student` — kapsıyorsa, öğrencinin KENDİ grubunda bu
   gereksinimi karşılayan aktif birimlerin id'leri.

Grup ayrımı burada kendiliğinden çözülür: birimler katalogda gruba özel
tutulduğu için (aynı ad grup-1 ve grup-2 satırı olarak iki kez) ada göre
eşleşen birimlerden yalnız öğrencinin grubuna ait olanlar döner. Kullanıcı
"YB/B" der; 1. gruptaki öğrenci için grup-1 satırı, 2. gruptaki için grup-2
satırı seçilir.
"""
from __future__ import annotations

from .models import (
    BRANCH_DOGUM_SALONU,
    BRANCH_LABELS,
    DEFAULT_SETTINGS,
    PROGRAM_EBELIK,
    PROGRAM_LABELS,
    Requirement,
    SCOPE_ALL,
    SCOPE_CLASS,
    SCOPE_GROUP,
    SCOPE_PROGRAM,
    SCOPE_STUDENTS,
    SEVERITY_REQUIRED,
)
from .normalize import normalize_key


def active_requirements(store) -> list[Requirement] | None:
    """Bu sezonda GEÇERLİ gereksinim listesi — yoksa None (eski branş yolu).

    Geçiş kuralı tek yerde: sezonda tanımlı ve aktif bir gereksinim varsa
    motor onu kullanır; yoksa `settings.season_requirements` branş yolu
    çalışmaya devam eder. Böylece eski sezonlar hiç bozulmaz, yeni sezonlar
    yeni yolu kullanır.

    None ile boş liste FARKLIDIR: None "gereksinim tanımlanmamış, eski yola
    düş" demek; boş liste "hepsi silinmiş/pasif" demek olurdu ve o da eski
    yola düşmeli — bu yüzden ikisi de None'a indirgenir.
    """
    reqs = [r for r in store.load_requirements() if r.active]
    return reqs or None


def requirements_in_effect(store) -> bool:
    """Ekranlarda "hangi yol geçerli" bilgisini göstermek için."""
    return active_requirements(store) is not None


def applies_to(req: Requirement, student) -> bool:
    """Gereksinim bu öğrenciyi kapsıyor mu?

    Pasif gereksinim ve pasif öğrenci hiçbir zaman kapsanmaz: pasif öğrencinin
    (sezon ortasında ayrılan) sezon sonu zorunluluğu aranmaz, geçmişi korunur.
    """
    if not req.active:
        return False
    if not getattr(student, "active", True):
        return False
    if student.id in req.excluded_ids:
        return False
    if req.scope == SCOPE_ALL:
        return True
    if req.scope == SCOPE_GROUP:
        return str(student.group) == str(req.scope_value)
    if req.scope == SCOPE_CLASS:
        return normalize_key(student.class_name) == normalize_key(req.scope_value)
    if req.scope == SCOPE_PROGRAM:
        return student.program == req.scope_value
    if req.scope == SCOPE_STUDENTS:
        return student.id in req.student_ids
    return False


def compile_for_student(req: Requirement, student, units) -> list[str]:
    """Bu gereksinimi bu öğrenci için karşılayan aktif birimlerin id'leri.

    Boş liste dönmesi "karşılanamaz" demektir — çağıran taraf bunu ya hata
    olarak raporlar (çözücü) ya da sessizce atlar (denetleyici; hastanede o
    birim hiç yoksa kullanıcıyı boş yere uyarmamak için).
    """
    keys = {normalize_key(k) for k in req.unit_keys}
    if not keys:
        return []
    return [
        u.id
        for u in units
        if u.active
        and u.group in (0, student.group)
        and normalize_key(u.name) in keys
    ]


def met_count(req: Requirement, seen_unit_keys) -> int:
    """Bu gereksinimden kaç ziyaret ZATEN karşılanmış (geçmiş atamalardan).

    `seen_unit_keys`: öğrencinin şimdiye kadar gittiği birimlerin normalize
    adları. Madde 1 (aynı birime iki kez gidilmez) gereği her ad en fazla bir
    kez sayılır, dolayısıyla kesişimin boyutu karşılanan ziyaret sayısıdır.
    """
    keys = {normalize_key(k) for k in req.unit_keys}
    if not keys:
        return 0
    return len(keys & {normalize_key(k) for k in seen_unit_keys})


def unmet_count(req: Requirement, seen_unit_keys) -> int:
    """Bu gereksinimden kaç ziyaret daha gerekiyor.

    Kırpma YOK: kullanıcı 3 birim isteyip listede 2 birim varsa bu bir veri
    hatasıdır ve çözücünün "karşılanamıyor" diye açıkça söylemesi gerekir.
    Sessizce 2'ye düşürmek hatayı gizlerdi. (Listede HİÇ birim yoksa
    gereksinim baştan uygulanmaz — v1'in "o branştan birim yoksa atla"
    davranışıyla aynı; bkz. compile_for_student.)
    """
    return max(0, req.min_count - met_count(req, seen_unit_keys))


def min_visits_needed(items) -> int:
    """Bu borçları kapatmak için gereken ay sayısının GÜVENLİ alt sınırı.

    `items`: (birim_kümesi, kaç_ziyaret) çiftleri.

    Gereksinimler KESİŞEBİLİR ve kesişince tek ziyaret birkaçını birlikte
    kapatır: "yoğun bakım" (YB/B-C-D) kümesi "yoğun bölüm" kümesinin ALT
    KÜMESİ olduğu için bir YB/B ziyareti ikisini de karşılar. Borçları
    toplamak (1+1+1+1+1=5) bu yüzden gereken ay sayısını ŞİŞİRİR ve
    "kalan 4 ayda 5 zorunluluk var, yetişmez" gibi YANLIŞ çözümsüzlük
    üretirdi.

    Kesin minimum bir küme-kapsama problemi (NP-zor). Burada gereken şey
    kesinlik değil **sağlamlık**: alt sınır asla gerçek minimumdan BÜYÜK
    olmamalı, yoksa yanlış hata basarız. Birbiriyle hiç kesişmeyen borçlar
    ayrı ayrı ay ister; dolayısıyla ikili ayrık bir alt küme seçip
    sayılarını toplamak geçerli bir alt sınırdır. Açgözlü seçim (en büyük
    sayıdan başlayarak, ayrık olanı al) bunu O(n²) ile verir; en iyi alt
    sınırı bulmayabilir ama ASLA aşmaz.
    """
    kalanlar = sorted(items, key=lambda it: -it[1])
    secilen_birimler: set = set()
    alt_sinir = 0
    for birimler, sayi in kalanlar:
        kume = set(birimler)
        if not kume or sayi <= 0:
            continue
        if kume & secilen_birimler:
            continue  # başka bir borçla kesişiyor: aynı ziyaret ikisini sayabilir
        secilen_birimler |= kume
        alt_sinir += sayi
    return alt_sinir


def describe(req: Requirement, class_names=None) -> str:
    """Gereksinimin tek cümlelik okunur özeti (ekranda ve ihlal mesajında)."""
    who = {
        SCOPE_ALL: "Tüm öğrenciler",
        SCOPE_GROUP: f"{req.scope_value}. grup",
        SCOPE_CLASS: f"{req.scope_value} sınıfı",
        SCOPE_PROGRAM: PROGRAM_LABELS.get(req.scope_value, req.scope_value),
        SCOPE_STUDENTS: f"Seçili {len(req.student_ids)} öğrenci",
    }.get(req.scope, req.scope)
    if req.excluded_ids and req.scope != SCOPE_STUDENTS:
        who += f" ({len(req.excluded_ids)} öğrenci hariç)"
    units_text = ", ".join(req.unit_keys) if req.unit_keys else "(birim seçilmemiş)"
    kind = "zorunlu" if req.severity == SEVERITY_REQUIRED else "tercih"
    return f"{who} — {units_text} birimlerinden en az {req.min_count} — {kind}"


def from_legacy_settings(settings, units, students=None) -> list[Requirement]:
    """v1 ayarlarını (branş bazlı) gereksinim listesine çevirir.

    İki kaynak vardır ve ikisi de görünür birer satıra dönüşür:

    * `settings.season_requirements` — her zorunlu branş, o branştaki birim
      adlarından en az 1 ziyaret isteyen bir gereksinim olur.
    * Koda gömülü madde 7 (ebelik → doğum salonu) — artık normal, düzenlenebilir
      bir satır: kapsam "program = ebelik".

    v1'deki "yalnız o branştan birim tanımlıysa uygula" davranışı korunur:
    hiç birimi olmayan branş için gereksinim üretilmez (palyatifsiz bir
    hastanede palyatif zorunluluğu çözümü kilitlemesin).
    """
    settings = settings or DEFAULT_SETTINGS
    by_branch: dict[str, list[str]] = {}
    for u in units:
        if u.active:
            by_branch.setdefault(u.branch_category, [])
            key = normalize_key(u.name)
            if key not in by_branch[u.branch_category]:
                by_branch[u.branch_category].append(key)

    out: list[Requirement] = []
    for entry in settings.get("season_requirements", []):
        branch = entry.get("branch")
        keys = by_branch.get(branch)
        if not branch or not keys:
            continue
        out.append(
            Requirement(
                name=BRANCH_LABELS.get(branch, branch),
                scope=SCOPE_ALL,
                unit_keys=sorted(keys),
                min_count=1,
                note=f"v1 sezon zorunluluğundan aktarıldı (branş: {branch}).",
            )
        )

    dogum_keys = by_branch.get(BRANCH_DOGUM_SALONU)
    if dogum_keys:
        out.append(
            Requirement(
                name="Ebelik → doğum salonu",
                scope=SCOPE_PROGRAM,
                scope_value=PROGRAM_EBELIK,
                unit_keys=sorted(dogum_keys),
                min_count=1,
                note="v1'de koda gömülü olan madde 7; artık düzenlenebilir.",
            )
        )
    return out
