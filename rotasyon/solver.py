"""CP-SAT tabanlı aylık rotasyon çözücüsü.

Tek bir grubun tek bir ayını çözer; önceki ayların atamaları sabit girdidir
(geçmiş). Sert kısıtlar `Add*` ile, yumuşak kısıtlar (madde 4, 18, 19 ve
madde 6/7'yi erkene çekme) ceza/bonus değişkenleriyle objective'e eklenir.

Çözüm bulunamazsa (infeasible) kısıt aileleri assumption literal'larıyla
işaretlenip çekirdek (unsat core) çıkarılır ve hangi kural gruplarının
çeliştiği Türkçe raporlanır — sessiz hata yok.
"""
from __future__ import annotations

import itertools
from collections import defaultdict
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from .models import (
    Assignment,
    CustomRule,
    Requirement,
    Student,
    Unit,
    BRANCH_DOGUM_SALONU,
    BRANCH_LABELS,
    SEVERITY_REQUIRED,
    INTENSITY_HAFIF,
    INTENSITY_YOGUN,
    PROGRAM_EBELIK,
    RULE_AYRI_TUT,
    RULE_BIRIM_YASAK,
    RULE_BIRLIKTE_TUT,
    RULE_SABIT_ATAMA,
    DEFAULT_SETTINGS,
    pin_map,
    rule_active_in_month,
)
from .normalize import normalize_key


def _banned_keys(rule, catalog_by_id) -> set[str]:
    """Birim yasağı kuralının kapsadığı normalize ad anahtarları.

    Yasak birim adına göre işler (madde 1 gibi): "AMELİYATHANE k" ve
    "AMELİYATHANE e" aynı bölüm sayılır, ikisi de yasaklanır.
    """
    u = catalog_by_id.get(rule.unit_id)
    return {normalize_key(u.name)} if u is not None else set()


@dataclass
class SolveResult:
    status: str  # "OPTIMAL" | "FEASIBLE" | "INFEASIBLE" | "UNKNOWN"
    assignments: dict[str, str] = field(default_factory=dict)  # student_id -> unit_id
    infeasible_reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # kullanıcıya bilgi notları
    objective: float | None = None  # amaç fonksiyonu (düşük = iyi); kıyas için

    @property
    def ok(self) -> bool:
        return self.status in ("OPTIMAL", "FEASIBLE")


@dataclass
class SeasonSolveResult:
    """Bütün sezonu tek modelde çözen `solve_season` sonucu."""

    status: str  # "OPTIMAL" | "FEASIBLE" | "INFEASIBLE" | "UNKNOWN"
    # (öğrenci_id, ay) -> birim_id
    assignments: dict[tuple[str, str], str] = field(default_factory=dict)
    infeasible_reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    objective: float | None = None

    @property
    def ok(self) -> bool:
        return self.status in ("OPTIMAL", "FEASIBLE")


# Assumption literal grupları için Türkçe açıklamalar
_REASON_LABELS = {
    "quota": "Birim kontenjanları: toplam kontenjan öğrenci sayısını karşılamıyor "
             "olabilir (kontenjanları artırın veya birim ekleyin).",
    "no_repeat": "Madde 1 (aynı birime ikinci kez gitmeme): bazı öğrencilerin "
                 "gidebileceği yeni birim kalmamış olabilir.",
    "gender": "Madde 2/3 (cinsiyet kısıtlı birimler): kısıtlı birimler için uygun "
              "cinsiyette yeterli öğrenci bulunamıyor olabilir.",
    "banned": "Madde 8 (yasaklı birimler): yasak listeleri atama seçeneklerini "
              "aşırı daraltıyor olabilir.",
    "dis": "Madde 9 (Diş Polikliniği muafiyeti): Diş kontenjanı, muaf olmayan "
           "öğrencilerle doldurulamıyor olabilir.",
    "must_fill": "Madde 17 (FTR çiftinde her ay bir kız bir erkek): uygun "
                 "kız/erkek öğrenci kalmamış olabilir.",
    "deadline_core": "Sezon zorunlulukları (her öğrenci sezon boyunca cerrahi/"
                     "dahili/yoğun bakım/palyatif görmeli): kalan aylarda bu "
                     "birimlerde yeterli kontenjan yok.",
    "deadline_dogum": "Madde 7 (ebelik öğrencileri doğum salonu görme): doğum "
                      "salonu kontenjanı ebelik öğrencilerine yetmiyor.",
    "intensity": "Peş peşe yoğun/hafif yasağı: önceki (veya sonraki) ayın "
                 "yoğunluğu bu ayda aynı türden birimleri kapatıyor, uygun "
                 "birim kalmıyor olabilir.",
    "locked": "Elle sabitlenen atamalar diğer kurallarla çelişiyor.",
    "custom": "Özel kurallar: ayrı/birlikte tutma veya sabit atamalar diğer "
              "kurallarla çelişiyor olabilir (Özel Kurallar ekranı).",
}


class _Weights:
    """Ağırlık okuma: eksik anahtar ÇÖKERTMEZ, ölçülmüş varsayılana düşer.

    Dört anahtar `weights["x"]` diye okunuyordu; bir sezon dosyasında o
    anahtar yoksa çözücü KeyError ile ölüyordu. Uygulama yolunda
    Store.load_settings DEFAULT_SETTINGS ile birleştirdiği için görünmüyordu
    — yani tek güvence oradaki birleştirmeydi. Ayarlar ekranındaki ağırlık
    kutuları kaldırıldığına göre bu dosyaları artık kullanıcı düzeltemez;
    motorun kendi kendine ayakta kalması gerekir.
    """

    __slots__ = ("_w",)

    def __init__(self, w: dict | None):
        self._w = w or {}

    def __getitem__(self, key: str) -> int:
        return self.get(key)

    def get(self, key: str, default=None) -> int:
        deger = self._w.get(key)
        if deger is None:
            deger = (
                default if default is not None
                else DEFAULT_SETTINGS["solver"]["weights"].get(key, 0)
            )
        return int(deger)


def visited_unit_keys(
    student_id: str, history: list[Assignment], units_by_id: dict[str, Unit]
) -> set[str]:
    """Öğrencinin geçmişte gittiği birimlerin normalize ad anahtarları.

    Madde 1 birim kimliğine değil ada göre işler: "EKG k" ile "EKG" aynı
    bölümdür; K/E varyantları (FTR.ÜNİT) da aynı bölüm sayılır.
    """
    keys = set()
    for a in history:
        if a.student_id == student_id and a.unit_id in units_by_id:
            keys.add(normalize_key(units_by_id[a.unit_id].name))
    return keys


def _remaining_months(month: str, months: list[str]) -> int:
    """Seçili aydan SONRA kalan ay sayısı."""
    if month not in months:
        return 0
    return len(months) - months.index(month) - 1


def _is_eligible(
    s: Student,
    u: Unit,
    visited_keys: set[str],
    blocked_intensities: set[str] = frozenset(),
) -> bool:
    if u.gender_restriction and s.gender and s.gender != u.gender_restriction:
        return False
    if normalize_key(u.name) in visited_keys:
        return False
    if u.id in s.banned_unit_ids:
        return False
    if s.dis_exempt and "DİŞ" in normalize_key(u.name):
        return False
    if u.intensity and u.intensity in blocked_intensities:
        return False
    return True


@dataclass
class _Obligation:
    """Bir öğrencinin sezon sonuna kadar karşılaması gereken tek bir borç.

    v1 (branş bazlı) ve v2 (gereksinim bazlı) zorunlulukların ORTAK şekli:
    "şu birimlerden şu kadarını gör". Çözücünün geri kalanı yalnız bu şekli
    tanır, zorunluluğun nereden geldiğini bilmez.
    """

    label: str  # kullanıcıya gösterilen ad ("Yoğun Bakım" / "Ebelik → doğum")
    unit_ids: list[str]  # bu öğrenci için borcu kapatan aktif birimler
    count: int = 1  # kaç ayrı ziyaret gerekiyor
    urgency_multiplier: int = 1  # erken-karşılama bonusunda ağırlık
    # hard=False → SERT kısıt kurulmaz, yalnız amaç fonksiyonunda ödüllendirilir
    # ("tercih" gereksinimleri): karşılanamaması sezonu çözümsüz yapmaz.
    hard: bool = True


def _obligations_from_branches(
    students, units, settings, seen_branches
) -> dict[str, list[_Obligation]]:
    """v1 yolu: settings.season_requirements branşları + madde 7 (ebelik→doğum).

    Bir branş yalnız o branştan birim tanımlıysa uygulanır (palyatifsiz bir
    hastanede palyatif zorunluluğu çözümü kilitlemesin).
    """
    branch_unit_ids: dict[str, list[str]] = defaultdict(list)
    for u in units:
        branch_unit_ids[u.branch_category].append(u.id)
    available = set(branch_unit_ids)
    req_branches = [
        r["branch"]
        for r in settings.get("season_requirements", [])
        if r.get("branch") and r["branch"] in available
    ]
    out: dict[str, list[_Obligation]] = {}
    for s in students:
        items: list[_Obligation] = []
        for b in req_branches:
            if b not in seen_branches[s.id]:
                items.append(
                    _Obligation(
                        label=BRANCH_LABELS.get(b, b),
                        unit_ids=list(branch_unit_ids.get(b, [])),
                    )
                )
        # NOT: madde 7, doğum birimi hiç tanımlı olmasa bile eklenir (v1
        # davranışı) — o durumda borç kapatılamaz ve çözücü bunu açıkça
        # çözümsüzlük olarak raporlar.
        if (
            s.program == PROGRAM_EBELIK
            and BRANCH_DOGUM_SALONU not in seen_branches[s.id]
        ):
            items.append(
                _Obligation(
                    label=BRANCH_LABELS[BRANCH_DOGUM_SALONU],
                    unit_ids=list(branch_unit_ids.get(BRANCH_DOGUM_SALONU, [])),
                    urgency_multiplier=3,  # madde 7 daha acil
                )
            )
        out[s.id] = items
    return out


def _obligations_from_requirements(
    students, units, requirements, visited
) -> dict[str, list[_Obligation]]:
    """v2 yolu: kullanıcının tanımladığı gereksinimler.

    Hiç birime derlenmeyen gereksinim atlanır — v1'in "o branştan birim yoksa
    uygulama" davranışının karşılığı; yoksa hastanede bulunmayan bir birim
    tüm sezonu çözümsüz yapardı.
    """
    from .requirements import applies_to, compile_for_student, unmet_count

    out: dict[str, list[_Obligation]] = {}
    for s in students:
        items: list[_Obligation] = []
        for req in requirements:
            if not applies_to(req, s):
                continue
            need = unmet_count(req, visited[s.id])
            if need <= 0:
                continue
            uids = compile_for_student(req, s, units)
            if not uids:
                continue
            items.append(
                _Obligation(
                    label=req.name, unit_ids=uids, count=need,
                    hard=req.severity == SEVERITY_REQUIRED,
                )
            )
        out[s.id] = items
    return out


def _obligation_debt(items: list[_Obligation]) -> int:
    """Bu borçları kapatmak için gereken AY sayısının güvenli alt sınırı.

    Borçları toplamak YANLIŞ olurdu: gereksinimler kesişebilir ve kesişince
    tek ziyaret birkaçını birlikte kapatır (bir YB/B ziyareti hem "yoğun
    bakım" hem "yoğun bölüm" borcunu düşürür). Toplama, "kalan 4 ayda 5
    zorunluluk var, yetişmez" gibi yanlış çözümsüzlük üretiyordu.
    Bkz. requirements.min_visits_needed.

    Tercih gereksinimleri sayılmaz: karşılanmamaları sezonu çözümsüz yapmaz,
    dolayısıyla "kalan ay yetişmiyor" hesabına girmemeleri gerekir.
    """
    from .requirements import min_visits_needed

    return min_visits_needed(
        [(o.unit_ids, o.count) for o in items if o.hard]
    )


def _pin_conflicts(students, units, month, pinned_now) -> list[str]:
    """Sabitlemenin KENDİSİ imkânsızsa net sebep.

    Sabitlenen hücre madde 1 ve madde 20'den muaftır ama cinsiyet,
    kontenjan, yasaklı birim ve diş muafiyeti esnemez. Bunlarla çelişen bir
    sabitlemede unsat core alakasız aileler sayıyordu ("cinsiyet", "FTR");
    kullanıcıya hangi öğrencinin hangi ayda neden olmadığı söylenir.
    """
    by_id = {u.id: u for u in units}
    st_by_id = {s.id: s for s in students}
    out: list[str] = []
    sayac: dict[str, int] = {}
    for sid, uid in pinned_now.items():
        s, u = st_by_id.get(sid), by_id.get(uid)
        if s is None:
            continue
        if u is None:
            out.append(f"{s.full_name}: {month} sabit ataması silinmiş bir birime işaret ediyor.")
            continue
        ad = f"{s.full_name} → {month} {u.display_name} (sabit atama)"
        if not u.active or u.quota <= 0:
            out.append(f"{ad}: birim pasif ya da kontenjanı 0.")
        if u.gender_restriction and s.gender and s.gender != u.gender_restriction:
            out.append(f"{ad}: birim yalnız {'kız' if u.gender_restriction == 'K' else 'erkek'} öğrenci alıyor.")
        if u.id in s.banned_unit_ids:
            out.append(f"{ad}: öğrenci için yasaklı birim.")
        if s.dis_exempt and "DİŞ" in normalize_key(u.name):
            out.append(f"{ad}: öğrenci diş muafiyetli.")
        sayac[uid] = sayac.get(uid, 0) + 1
    for uid, n in sayac.items():
        u = by_id.get(uid)
        if u is not None and u.active and n > u.quota:
            out.append(
                f"{month}: {u.display_name} birimine {n} öğrenci sabitlenmiş "
                f"ama kontenjanı {u.quota}."
            )
    return out


def _prefeasibility_reasons(
    students: list[Student],
    units: list[Unit],
    visited: dict[str, set[str]],
    remaining: int,
    unmet: dict[str, list[_Obligation]],
    blocked_intensity: dict[str, set[str]],
    pinned_now: dict[str, str] | None = None,
) -> list[str]:
    """CP-SAT'tan önce ucuz, kesin çelişki kontrolleri.

    Buradan dönen her madde tek başına çözümsüzlüğü kanıtlar; kullanıcıya
    unsat core'dan çok daha somut bir açıklama verir ("DİŞ için uygun
    öğrenci kalmadı" gibi).

    `unmet`: öğrenci başına, sezon sonuna kadar kapatılması gereken borçlar
    (v1 branş zorunlulukları ya da v2 gereksinimleri — ikisi de _Obligation).
    """
    reasons: list[str] = []
    # `remaining` tek sayı ya da öğrenci başına sözlük olabilir: sabitlenen
    # gelecek aylar o öğrencinin zorunluluk kapatabileceği ayları azaltır.
    rem = (
        remaining if isinstance(remaining, dict)
        else {s.id: remaining for s in students}
    )
    total_quota = sum(u.quota for u in units)
    n = len(students)
    if total_quota < n:
        reasons.append(
            f"Toplam kontenjan ({total_quota}) öğrenci sayısının ({n}) altında; "
            "kontenjanları artırın veya birim ekleyin."
        )
    # "Tam dolmalı" birimler bir ayda BİRLİKTE kontenjanları kadar AYRI
    # öğrenci ister (bir öğrenci ayda tek birimde olur) — toplamları grubu
    # aşıyorsa çelişki kesindir. Bu kontrol olmadan unsat core alakasız bir
    # aile gösterebiliyordu ("elle sabitlenen atamalar" gibi).
    must_total = sum(u.quota for u in units if u.must_fill)
    if must_total > n:
        adlar = ", ".join(u.display_name for u in units if u.must_fill)
        reasons.append(
            f"“Tam dolmalı” birimler her ay toplam {must_total} öğrenci "
            f"istiyor ama grupta {n} öğrenci var ({adlar}). Kontenjanlarını "
            "düşürün ya da bazılarını “tam dolmalı” olmaktan çıkarın."
        )
    exact_fill = total_quota == n

    for u in units:
        need = u.quota if (exact_fill or u.must_fill) else 0
        if not need:
            continue
        eligible = sum(
            1
            for s in students
            if _is_eligible(s, u, visited[s.id], blocked_intensity[s.id])
        )
        if eligible < need:
            why = "tam dolmak zorunda (madde 17)" if u.must_fill and not exact_fill \
                else "toplam kontenjan öğrenci sayısına eşit olduğundan her birim dolmalı"
            reasons.append(
                f"{u.display_name}: uygun öğrenci sayısı ({eligible}) "
                f"kontenjanın ({need}) altında — daha önce gidenler, cinsiyet "
                f"kısıtı veya muafiyetler nedeniyle; bu birim {why}."
            )

    for s in students:
        if not any(
            _is_eligible(s, u, visited[s.id], blocked_intensity[s.id])
            for u in units
        ):
            reasons.append(
                f"{s.full_name} için atanabilecek birim kalmadı (tekrar yasağı, "
                "peş peşe yoğun/hafif yasağı ve kısıtlar tüm birimleri eliyor)."
            )

    # Sezon zorunlulukları: ayda en çok 1 borç kapatılabilir → kalan ay
    # sayısı toplam borcu taşımıyorsa çözüm yoktur.
    pinned_now = pinned_now or {}
    for s in students:
        debt = _obligation_debt(unmet[s.id])
        if s.id in pinned_now:
            # bu ay sabitlemeyle dolu: borç yalnız sonraki serbest aylarda
            if debt > rem[s.id]:
                labels = ", ".join(o.label for o in unmet[s.id])
                reasons.append(
                    f"{s.full_name}: sabit atamalar yüzünden sezonun geri "
                    f"kalanında yalnız {rem[s.id]} serbest ayı kalıyor ama "
                    f"karşılanması gereken {debt} zorunluluk var ({labels}). "
                    "Sabitleme süresini kısaltın ya da Gereksinimler "
                    "ekranında bu öğrenciyi o gereksinimden hariç tutun."
                )
            continue
        if debt > rem[s.id] + 1:
            labels = ", ".join(o.label for o in unmet[s.id])
            serbest = rem[s.id] + 1
            ek = (
                " (sonraki ayların bir kısmı sabit atamayla dolu; gerekiyorsa "
                "Gereksinimler ekranında öğrenciyi gereksinimden hariç tutun)"
                if isinstance(remaining, dict) and rem[s.id] < max(rem.values())
                else ""
            )
            reasons.append(
                f"{s.full_name}: kalan {serbest} serbest ayda karşılanması "
                f"gereken {debt} sezon zorunluluğu var ({labels}){ek} "
                "— ayda en fazla biri karşılanabilir, yetişmez."
            )

    son_ay = [
        s for s in students if rem[s.id] == 0 and s.id not in pinned_now
    ]
    if son_ay:
        # Son fırsat: borcunu kapatmak için bu ay dışında ayı kalmayanlar
        # (sezonun son ayı ya da sonraki ayları sabitlenmiş öğrenciler) o
        # borcu kapatan birimlerin kontenjanına sığmalı
        quota_by_unit = {u.id: u.quota for u in units}
        need_by_label: dict[str, int] = defaultdict(int)
        uids_by_label: dict[str, set[str]] = defaultdict(set)
        for s in son_ay:
            for o in unmet[s.id]:
                if not o.hard:
                    continue  # tercih: karşılanmazsa çözümsüzlük değil
                need_by_label[o.label] += 1
                uids_by_label[o.label].update(o.unit_ids)
        for label, count in need_by_label.items():
            quota = sum(
                quota_by_unit.get(uid, 0) for uid in uids_by_label[label]
            )
            if count > quota:
                reasons.append(
                    f"Son ayda {label} görmesi gereken "
                    f"{count} öğrenci var ama bunu karşılayan birimlerin "
                    f"toplam kontenjanı {quota}."
                )
    return reasons


def solve_month(
    students: list[Student],
    units: list[Unit],
    month: str,
    history: list[Assignment],
    settings: dict | None = None,
    locked: dict[str, str] | None = None,
    random_seed: int | None = None,
    custom_rules: list[CustomRule] | None = None,
    requirements: list[Requirement] | None = None,
    escalate: bool = True,
    _diagnostic: bool = False,
) -> SolveResult:
    """`students` (tek grup) için `month` ayının atamasını çözer.

    `requirements` (v2): verilirse sezon zorunlulukları bu gereksinim
    listesinden okunur. Verilmezse v1 yolu işler — settings.season_requirements
    branşları + koda gömülü madde 7 (ebelik → doğum salonu).

    `escalate`: süre yetmezse limiti büyütüp yeniden dene (varsayılan). Sebep
    TEŞHİSİ bunu kapatır: teşhis ayları tek tek çözerek döngü kurar, her zor
    ayda kademeleri beklemek analizi dakikalarca uzatır ve zaten aranan şey
    çözüm değil hangi kuralın tıkadığıdır.

    `units` grubun TÜM birimlerini içermeli (pasifler dahil): atama yalnız
    aktif ve kontenjanlı birimlere yapılır, ama geçmiş yorumu (madde 1 tekrar
    yasağı, madde 6/7 kategori geçmişi) tam katalog üzerinden çalışır —
    pasifleştirilmiş bir birimin geçmişi kaybolmaz.

    locked: {student_id: unit_id} — yarı otomatik modda elle sabitlenen hücreler.
    """
    settings = settings or DEFAULT_SETTINGS
    months: list[str] = settings["months"]
    weights = _Weights(settings["solver"]["weights"])
    locked = dict(locked or {})
    custom_rules = [r for r in (custom_rules or []) if r.active]

    # Sabit atama kuralları bu ayın kilitli hücreleri gibi işlenir;
    # elle kilitlenen hücre (locked parametresi) öncelik taşır.
    # "Sabitlenen kazanır": sabitlenen hücre madde 1 ve madde 20'den muaftır
    # (bkz. models.pin_map). Muafiyet yalnız bu aya ve o birime aittir.
    group_ids = {s.id for s in students}
    pins = {
        k: v for k, v in pin_map(custom_rules, months).items()
        if k[0] in group_ids
    }
    pinned_now = {sid: uid for (sid, m), uid in pins.items() if m == month}
    for sid, uid in pinned_now.items():
        locked.setdefault(sid, uid)

    catalog_by_id = {u.id: u for u in units}  # geçmiş yorumu için tam katalog
    all_units = units
    units = [u for u in units if u.active and u.quota > 0]
    units_by_id = {u.id: u for u in units}
    remaining = _remaining_months(month, months)

    model = cp_model.CpModel()

    # İki fazlı çözüm: normalde kısıtlar doğrudan (hızlı) kurulur. Model
    # infeasible çıkarsa `_diagnostic=True` ile yeniden çağrılır; o zaman her
    # sert kısıt ailesi bir assumption literal'ına bağlanır ve unsat core'dan
    # hangi kural gruplarının çeliştiği okunur. (Assumption'lı model presolve'u
    # zayıflattığı için mutlu yol ayrı tutulur.)
    if _diagnostic:
        assumptions: dict[str, cp_model.IntVar] = {
            name: model.NewBoolVar(f"assume_{name}") for name in _REASON_LABELS
        }
    else:
        always = model.NewBoolVar("always")
        model.Add(always == 1)
        assumptions = {name: always for name in _REASON_LABELS}

    # ---- değişkenler: uygunluk ön filtresiyle x[s,u] ----
    x: dict[tuple[str, str], cp_model.IntVar] = {}
    visited: dict[str, set[str]] = {
        s.id: visited_unit_keys(s.id, history, catalog_by_id) for s in students
    }
    # Sabitlenen birimler (geçmiş ya da gelecek her ayda) görülmüş sayılır:
    # sabitlenmemiş bir ayda o birime tekrar verilmez, o birimin kapattığı
    # zorunluluk da "karşılanmış" sayılır (sabitleme onu zaten karşılayacak).
    for (sid, m), uid in pins.items():
        if uid in catalog_by_id:
            visited[sid].add(normalize_key(catalog_by_id[uid].name))
    # Uygunluk için ayrı görünüm: bu ay sabitlenen öğrenci, sabitlendiği
    # birim için madde 1'den muaf.
    eligible_visited: dict[str, set[str]] = {
        sid: set(keys) for sid, keys in visited.items()
    }
    for sid, uid in pinned_now.items():
        if sid in eligible_visited and uid in catalog_by_id:
            eligible_visited[sid].discard(normalize_key(catalog_by_id[uid].name))
    # Öğrenci başına zorunluluk kapatabileceği kalan ay: sabitlenen gelecek
    # aylar sayılmaz (o aylar zaten dolu).
    later = set(months[months.index(month) + 1:]) if month in months else set()
    remaining_by_student = {
        s.id: remaining - sum(1 for (sid, m) in pins if sid == s.id and m in later)
        for s in students
    }
    # Aynı ayda başka gruba/aya ait çakışan atama olmadığı varsayılır (UI temizler).

    # ---- sezon zorunlulukları: her öğrencinin sezon sonuna kadar kapatması
    # gereken borçlar. `requirements` verilirse v2 gereksinim modeli, aksi
    # halde v1 branş yolu (settings.season_requirements + madde 7 ebelik→doğum).
    # İkisi de aynı `_Obligation` şekline derlenir; aşağısı farkı görmez.
    if requirements is not None:
        unmet = _obligations_from_requirements(
            students, units, requirements, visited
        )
    else:
        seen_branches: dict[str, set[str]] = {}
        for s in students:
            seen_branches[s.id] = {
                catalog_by_id[a.unit_id].branch_category
                for a in history
                if a.student_id == s.id and a.unit_id in catalog_by_id
            } | {
                catalog_by_id[uid].branch_category
                for (sid, m), uid in pins.items()
                if sid == s.id and uid in catalog_by_id
            }
        unmet = _obligations_from_branches(
            students, units, settings, seen_branches
        )

    # ---- peş peşe yoğun/hafif yasağı: komşu ayların yoğunluğu bu ayda
    # aynı türden birimleri kapatır (araya ay eklenirken iki yön de denetlenir)
    blocked_intensity: dict[str, set[str]] = {s.id: set() for s in students}
    if month in months:
        idx = months.index(month)
        neighbors = {
            months[i] for i in (idx - 1, idx + 1) if 0 <= i < len(months)
        }
        for a in history:
            if (
                a.month in neighbors
                and a.student_id in blocked_intensity
                and a.unit_id in catalog_by_id
            ):
                inten = catalog_by_id[a.unit_id].intensity
                if inten:
                    blocked_intensity[a.student_id].add(inten)
        # henüz üretilmemiş ama SABİTLENMİŞ komşu ay da sayılır: Kasım'da
        # DİŞ'e (hafif) sabitlenen öğrenciye Ekim'de hafif bölüm verilmez
        for (sid, m), uid in pins.items():
            if (
                m in neighbors
                and sid in blocked_intensity
                and uid in catalog_by_id
                and catalog_by_id[uid].intensity
            ):
                blocked_intensity[sid].add(catalog_by_id[uid].intensity)
    for sid in pinned_now:
        if sid in blocked_intensity:
            blocked_intensity[sid].clear()  # sabitlenen hücre madde 20'den muaf

    # CP-SAT'tan önce ucuz kesin kontroller: çelişki buradan yakalanırsa
    # somut Türkçe açıklamayla hemen dönülür (solver'ın kanıt araması gereksiz).
    if not _diagnostic:
        pre = _pin_conflicts(students, all_units, month, pinned_now)
        pre += _prefeasibility_reasons(
            students, units, eligible_visited, remaining_by_student, unmet,
            blocked_intensity, pinned_now,
        )
        if pre:
            return SolveResult(status="INFEASIBLE", infeasible_reasons=pre)

    for s in students:
        for u in units:
            x[(s.id, u.id)] = model.NewBoolVar(f"x_{s.id}_{u.id}")

    # Uygunluk kısıtları (assumption'lı — ihlal ailesi teşhis edilebilsin diye
    # değişken budama yerine koşullu kısıt olarak yazılır)
    for s in students:
        for u in units:
            var = x[(s.id, u.id)]
            if u.gender_restriction and s.gender and s.gender != u.gender_restriction:
                model.Add(var == 0).OnlyEnforceIf(assumptions["gender"])
            if normalize_key(u.name) in eligible_visited[s.id]:
                model.Add(var == 0).OnlyEnforceIf(assumptions["no_repeat"])
            if u.id in s.banned_unit_ids:
                model.Add(var == 0).OnlyEnforceIf(assumptions["banned"])
            if s.dis_exempt and "DİŞ" in normalize_key(u.name):
                model.Add(var == 0).OnlyEnforceIf(assumptions["dis"])
            if u.intensity and u.intensity in blocked_intensity[s.id]:
                # peş peşe yoğun ya da peş peşe hafif bölüm yasak
                model.Add(var == 0).OnlyEnforceIf(assumptions["intensity"])

    # Her öğrenciye tam bir birim (grubun tanımı — assumption'sız, gevşetilemez)
    for s in students:
        model.AddExactlyOne(x[(s.id, u.id)] for u in units)

    # Kontenjan
    occupancy: dict[str, cp_model.LinearExpr] = {}
    for u in units:
        occ = sum(x[(s.id, u.id)] for s in students)
        occupancy[u.id] = occ
        model.Add(occ <= u.quota).OnlyEnforceIf(assumptions["quota"])
        if u.must_fill:  # madde 17
            model.Add(occ == u.quota).OnlyEnforceIf(assumptions["must_fill"])

    # Elle sabitlenen hücreler
    for sid, uid in locked.items():
        if (sid, uid) in x:
            model.Add(x[(sid, uid)] == 1).OnlyEnforceIf(assumptions["locked"])

    # Özel kurallar: ayrı tut / birlikte tut / birim yasağı — yalnız kuralın
    # zaman penceresi bu ayı kapsıyorsa (sabit atama yukarıda locked'a girdi).
    student_id_set = {s.id for s in students}
    for rule in custom_rules:
        if not rule_active_in_month(rule, month, months):
            continue
        if rule.type == RULE_BIRIM_YASAK:
            banned_keys = _banned_keys(rule, catalog_by_id)
            for sid in rule.student_ids:
                if sid not in student_id_set:
                    continue
                for u in units:
                    if normalize_key(u.name) in banned_keys and (sid, u.id) in x:
                        model.Add(x[(sid, u.id)] == 0).OnlyEnforceIf(
                            assumptions["custom"]
                        )
            continue
        ids = [sid for sid in rule.student_ids if sid in student_id_set]
        if len(ids) < 2:
            continue
        if rule.type == RULE_AYRI_TUT:
            for u in units:
                model.Add(
                    sum(x[(sid, u.id)] for sid in ids) <= 1
                ).OnlyEnforceIf(assumptions["custom"])
        elif rule.type == RULE_BIRLIKTE_TUT:
            first = ids[0]
            for other in ids[1:]:
                for u in units:
                    model.Add(
                        x[(first, u.id)] == x[(other, u.id)]
                    ).OnlyEnforceIf(assumptions["custom"])

    # ---- Sezon zorunlulukları (madde 6/7 + branş bazlı liste) ----
    # Öğrencinin karşılanmamış zorunluluk sayısı kalan ay sayısını aşarsa
    # bu ayda mutlaka bir zorunlu branşa gitmeli (sert kısıt); daha erkense
    # objective bonusuyla yönlendirilir.
    for s in students:
        if s.id in pinned_now:
            continue  # bu ayı sabitleme belirliyor
        need_now = _obligation_debt(unmet[s.id]) - remaining_by_student[s.id]
        if need_now >= 1:
            zorunlu = [o for o in unmet[s.id] if o.hard]
            uids = {uid for o in zorunlu for uid in o.unit_ids}
            only_dogum = (
                len(zorunlu) == 1 and zorunlu[0].urgency_multiplier > 1
            )
            label = "deadline_dogum" if only_dogum else "deadline_core"
            model.Add(
                sum(x[(s.id, uid)] for uid in uids if (s.id, uid) in x) >= 1
            ).OnlyEnforceIf(assumptions[label])

    # ---- Objective (Minimize) ----
    penalties: list[cp_model.LinearExpr] = []

    # Madde 4: havuz birimlerine eşit dağılım (doluluk yayılımını küçült)
    pool_units = [u for u in units if u.pool]
    if len(pool_units) >= 2:
        max_occ = model.NewIntVar(0, len(students), "pool_max")
        min_occ = model.NewIntVar(0, len(students), "pool_min")
        for u in pool_units:
            model.Add(occupancy[u.id] <= max_occ)
            model.Add(occupancy[u.id] >= min_occ)
        penalties.append(weights["pool_balance"] * (max_occ - min_occ))

    # Eşit dağıtım tam bölünmeyince oluşan FAZLALIK öğrenciler yoğun havuz
    # birimlerine düşsün: yoğun havuz doluluğu ÖDÜLLENDİRİLİR (negatif ceza).
    # Ağırlık pool_balance'tan küçük olduğundan dengeyi bozmaz — bir öğrenciyi
    # dengeyi 1 bozacak şekilde yoğuna almak pool_balance kadar (5) ceza yer,
    # ödül ise yalnız intensive_surplus (2); dolayısıyla yalnız EŞİT çözümler
    # arasında yoğunu seçtirir.
    w_surplus = weights.get("intensive_surplus", 2)
    if w_surplus:
        for u in pool_units:
            if u.intensity == INTENSITY_YOGUN:
                for s in students:
                    penalties.append(-w_surplus * x[(s.id, u.id)])

    # Madde 4: tekli birimler boş kalmasın (önce onlar doldurulur)
    for u in units:
        if u.single_slot:
            empty = model.NewBoolVar(f"empty_{u.id}")
            model.Add(occupancy[u.id] == 0).OnlyEnforceIf(empty)
            model.Add(occupancy[u.id] >= 1).OnlyEnforceIf(empty.Not())
            penalties.append(weights["single_slot_fill"] * empty)

    # Madde 19: geçmişte birlikte olmuş ikililer yine aynı birime düşmesin
    together_count: dict[tuple[str, str], int] = defaultdict(int)
    by_month_unit: dict[tuple[str, str], list[str]] = defaultdict(list)
    for a in history:
        by_month_unit[(a.month, a.unit_id)].append(a.student_id)
    for ids in by_month_unit.values():
        for s1, s2 in itertools.combinations(sorted(ids), 2):
            together_count[(s1, s2)] += 1
    student_ids = {s.id for s in students}
    for (s1, s2), count in together_count.items():
        if s1 not in student_ids or s2 not in student_ids:
            continue
        for u in units:
            both = model.NewBoolVar(f"pair_{s1}_{s2}_{u.id}")
            model.Add(x[(s1, u.id)] + x[(s2, u.id)] - 1 <= both)
            penalties.append(weights["repeat_pair"] * count * both)

    # Madde 18: ebelik öncelikli birimlere önce ebelik öğrencileri
    ebelik_students = {s.id for s in students if s.program == PROGRAM_EBELIK}
    if ebelik_students:
        for u in units:
            if not u.ebelik_priority:
                continue
            for s in students:
                if s.id not in ebelik_students:
                    # ebelik olmayan öğrenci öncelikli birimi işgal ederse ceza
                    penalties.append(
                        weights["ebelik_priority"] * x[(s.id, u.id)]
                    )

    # Sezon zorunluluklarını erken aylarda karşılama bonusu (negatif ceza).
    # Aciliyet kalan ay azaldıkça artar; doğum salonu (madde 7) daha ağır.
    urgency = max(1, len(months) - remaining)
    for s in students:
        for o in unmet[s.id]:
            for uid in o.unit_ids:
                if (s.id, uid) not in x:
                    continue
                penalties.append(
                    -weights["core_branch_early"] * urgency
                    * o.urgency_multiplier * x[(s.id, uid)]
                )

    # Gri/yedek birimler: yalnız gerektiğinde kullanılsın (her yerleştirme cezalı)
    for u in units:
        if u.reserve:
            for s in students:
                penalties.append(weights.get("reserve_use", 15) * x[(s.id, u.id)])

    # Havuz birimlerinde kız/erkek dengesi ("kız ve erkek sayısı dengeli olacak")
    genders_present = {s.gender for s in students if s.gender}
    if len(genders_present) == 2:
        w_gender = weights.get("gender_balance", 2)
        for u in pool_units:
            if u.gender_restriction:
                continue
            diff = model.NewIntVar(-len(students), len(students), f"gd_{u.id}")
            model.Add(
                diff
                == sum(x[(s.id, u.id)] for s in students if s.gender == "K")
                - sum(x[(s.id, u.id)] for s in students if s.gender == "E")
            )
            gap = model.NewIntVar(0, len(students), f"ga_{u.id}")
            model.AddAbsEquality(gap, diff)
            penalties.append(w_gender * gap)

    # Teşhis turunda amaç fonksiyonu kapatılır: yalnız fizibilite aranır,
    # unsat core çıkarımı hızlanır.
    model.Minimize(0 if _diagnostic else (sum(penalties) if penalties else 0))

    # ---- çözüm ----
    if _diagnostic:
        model.AddAssumptions(list(set(assumptions.values())))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(
        settings["solver"].get(
            "time_limit_seconds",
            DEFAULT_SETTINGS["solver"]["time_limit_seconds"],
        )
    )
    # Tek worker: paralel modda OR-Tools'un absl senkronizasyonu, pandas'ın
    # yüklediği pyarrow'daki aynı absl sembolleriyle çakışıp deadlock
    # yapabiliyor (macOS'ta gözlendi). Modeller küçük, tek worker yeterli;
    # gerekirse sezon settings.json'ından artırılabilir.
    solver.parameters.num_workers = int(settings["solver"].get("num_workers", 1))
    if random_seed is not None:
        # "Yeniden oluştur": eş-maliyetli çözümler arasında farklı sonuç üretir.
        # Küçük tohumlar (1, 2...) CP-SAT'ın varsayılan aramasına çok yakın
        # sonuç verebiliyor (ölçüldü: seed=1, tohumsuz çözümle birebir aynı
        # çıktı); Knuth karması ile tohum uzayına saçılır.
        solver.parameters.random_seed = (
            random_seed * 2654435761 + 101
        ) % (2**31)
        solver.parameters.randomize_search = True
    status = solver.Solve(model)
    if status == cp_model.UNKNOWN and not _diagnostic and escalate:
        # Eski/yavaş makine sigortası: süre içinde hiç çözüm bulunamadıysa
        # limiti kademeli büyütüp yeniden dene (kullanıcıya "süreyi artırın"
        # dememek için — uygulama sabırlı davranmayı kendi bilir).
        taban_ay = float(
            settings["solver"].get(
                "time_limit_seconds",
                DEFAULT_SETTINGS["solver"]["time_limit_seconds"],
            )
        )
        for kat in (4, 8):
            solver.parameters.max_time_in_seconds = taban_ay * kat
            status = solver.Solve(model)
            if status != cp_model.UNKNOWN:
                break

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        result = SolveResult(
            status="OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE",
            objective=solver.ObjectiveValue(),
        )
        for s in students:
            for u in units:
                if solver.Value(x[(s.id, u.id)]):
                    result.assignments[s.id] = u.id
        return result

    if status == cp_model.INFEASIBLE:
        if not _diagnostic:
            # teşhis turu: hangi kural aileleri çelişiyor?
            return solve_month(
                students,
                all_units,
                month,
                history,
                settings=settings,
                locked=locked,
                custom_rules=custom_rules,
                _diagnostic=True,
            )
        core = solver.SufficientAssumptionsForInfeasibility()
        index_to_name = {
            assumptions[name].Index(): name for name in assumptions
        }
        reasons = [
            _REASON_LABELS[index_to_name[i]]
            for i in core
            if i in index_to_name
        ]
        if not reasons:
            reasons = [
                "Kurallar birlikte sağlanamıyor; kontenjanları ve kısıtları "
                "gözden geçirin."
            ]
        return SolveResult(status="INFEASIBLE", infeasible_reasons=reasons)

    if status == cp_model.UNKNOWN and _diagnostic:
        return SolveResult(
            status="INFEASIBLE",
            infeasible_reasons=[
                "Kurallar birlikte sağlanamıyor; kontenjanları, cinsiyet "
                "kısıtlarını ve tekrar yasağını gözden geçirin."
            ],
        )

    return SolveResult(
        status="UNKNOWN",
        infeasible_reasons=[
            "Bu ay bilgisayarın rahat çözebileceğinden daha zor: uygulama "
            "giderek daha uzun süre denedi ama kesin sonuca ulaşamadı. Bu, "
            "çözümü OLMADIĞI anlamına gelmez — kurallar bu ay için çok sıkı. "
            "Kontenjanlara bir-iki kişilik pay bırakmayı ya da bir "
            "gereksinimi 'tercih'e çevirmeyi deneyin."
        ],
    )


def solve_season(
    students: list[Student],
    units: list[Unit],
    months: list[str],
    solve_months: list[str],
    history: list[Assignment],
    settings: dict | None = None,
    custom_rules: list[CustomRule] | None = None,
    random_seed: int | None = None,
    requirements: list[Requirement] | None = None,
    on_retry=None,
) -> SeasonSolveResult:
    """`solve_months`'un TAMAMINI tek CP-SAT modelinde birlikte çözer.

    `on_retry(kademe, toplam_kademe, yeni_limit)`: süre yetmeyip daha uzun
    denemeye geçildiğinde çağrılır (arayüz "daha uzun deneniyor" yazsın diye).

    `requirements` (v2): verilirse sezon zorunlulukları bu listeden okunur;
    verilmezse v1 branş yolu işler (bkz. solve_month).

    Ay-bazlı `solve_month` açgözlüdür: erken bir ayın (tek başına kusursuz)
    çözümü ileriki ayı çözümsüz bırakabilir. Bu fonksiyon bütün ayları aynı
    anda değişkenleştirir; böylece madde 1 (tekrar yasağı), sezon
    zorunlulukları (madde 6/7) ve madde 20 (peş peşe yoğunluk) SERT kısıt
    olarak kurulur ve veri elveriyorsa geçerli bir sezon bulunması garanti
    edilir (köşeye sıkışma imkânsız). `history`'deki dolu aylar sabit girdidir.

    Dönüş: (öğrenci_id, ay) -> birim_id eşlemesi + durum.
    """
    settings = settings or DEFAULT_SETTINGS
    weights = _Weights(settings["solver"]["weights"])
    custom_rules = [r for r in (custom_rules or []) if r.active]
    solve_set = set(solve_months)

    catalog_by_id = {u.id: u for u in units}
    active_units = [u for u in units if u.active and u.quota > 0]

    # "Sabitlenen kazanır" (bkz. models.pin_map): sabitlenen hücre madde 1 ve
    # madde 20'den muaftır. Eskiden sabitlenen hücrenin değişkeni tekrar
    # yasağı yüzünden hiç oluşturulmuyor ve sabitleme SESSİZCE atlanıyordu —
    # toplu üretim kullanıcının kararını fark ettirmeden yok sayabiliyordu.
    group_ids = {s.id for s in students}
    pins = {
        k: v for k, v in pin_map(custom_rules, months).items()
        if k[0] in group_ids
    }
    pinned_keys: dict[str, set[str]] = {s.id: set() for s in students}
    for (sid, m), uid in pins.items():
        if uid in catalog_by_id:
            pinned_keys[sid].add(normalize_key(catalog_by_id[uid].name))

    def is_pinned_cell(sid, uid, m):
        return pins.get((sid, m)) == uid

    for m in solve_months:
        pre = _pin_conflicts(
            students, units, m,
            {sid: uid for (sid, mm), uid in pins.items() if mm == m},
        )
        if pre:
            return SeasonSolveResult(status="INFEASIBLE", infeasible_reasons=pre)

    # geçmiş yorumu (tekrar yasağı + görülmüş branşlar)
    visited: dict[str, set[str]] = {
        s.id: visited_unit_keys(s.id, history, catalog_by_id) for s in students
    }
    seen_branches: dict[str, set[str]] = {}
    hist_by_student_month: dict[tuple[str, str], Unit] = {}
    for s in students:
        seen_branches[s.id] = set()
    for a in history:
        if a.unit_id in catalog_by_id:
            u = catalog_by_id[a.unit_id]
            if a.student_id in seen_branches:
                seen_branches[a.student_id].add(u.branch_category)
            hist_by_student_month[(a.student_id, a.month)] = u

    # Sezon zorunlulukları: v2 gereksinimleri verildiyse onlardan, aksi halde
    # v1 branş yolundan derlenir (ikisi de _Obligation).
    if requirements is not None:
        obligations = _obligations_from_requirements(
            students, active_units, requirements, visited
        )
    else:
        obligations = _obligations_from_branches(
            students, active_units, settings, seen_branches
        )

    model = cp_model.CpModel()

    # ---- değişkenler: x[s, u, m], statik uygunlukla budanmış ----
    x: dict[tuple[str, str, str], cp_model.IntVar] = {}
    key_of = {u.id: normalize_key(u.name) for u in active_units}
    for s in students:
        for m in solve_months:
            for u in active_units:
                if u.gender_restriction and s.gender and s.gender != u.gender_restriction:
                    continue
                sabit = is_pinned_cell(s.id, u.id, m)
                if not sabit and (
                    key_of[u.id] in visited[s.id]
                    or key_of[u.id] in pinned_keys[s.id]
                ):
                    # madde 1: sezon öncesinde görülmüş ya da başka bir ayda
                    # oraya sabitlenmiş (sabitleme o ziyaretin kendisi)
                    continue
                if u.id in s.banned_unit_ids:
                    continue
                if s.dis_exempt and "DİŞ" in key_of[u.id]:
                    continue
                x[(s.id, u.id, m)] = model.NewBoolVar(f"x_{s.id}_{u.id}_{m}")

    def vars_for(sid, m, pred):
        return [
            x[(sid, u.id, m)]
            for u in active_units
            if (sid, u.id, m) in x and pred(u)
        ]

    # her öğrenciye her ay tam bir birim
    for s in students:
        for m in solve_months:
            cell = vars_for(s.id, m, lambda u: True)
            if not cell:
                return SeasonSolveResult(
                    status="INFEASIBLE",
                    infeasible_reasons=[
                        f"{s.full_name}: {m} ayında atanabilecek hiç birim yok "
                        "(tekrar yasağı ve kısıtlar tüm birimleri eliyor)."
                    ],
                )
            model.AddExactlyOne(cell)

    # madde 1: sezon içinde de aynı bölüme iki kez gidilmez (ad bazında)
    keys = {key_of[u.id] for u in active_units}
    for s in students:
        for k in keys:
            if k in visited[s.id] or k in pinned_keys[s.id]:
                continue
            same = [
                x[(s.id, u.id, m)]
                for u in active_units
                for m in solve_months
                if key_of[u.id] == k and (s.id, u.id, m) in x
            ]
            if len(same) > 1:
                model.AddAtMostOne(same)

    # kontenjan + madde 17 (tam dolma)
    def unit_occ(uid, m):
        return sum(
            x[(s.id, uid, m)] for s in students if (s.id, uid, m) in x
        )

    occ: dict[tuple[str, str], cp_model.LinearExpr] = {}
    for u in active_units:
        for m in solve_months:
            e = unit_occ(u.id, m)
            occ[(u.id, m)] = e
            model.Add(e <= u.quota)
            if u.must_fill:
                model.Add(e == u.quota)

    # madde 20: peş peşe yoğun/hafif yasağı (komşu aylar; geçmiş sınır dahil)
    for i in range(len(months) - 1):
        a_m, b_m = months[i], months[i + 1]
        for s in students:
            a_pin, b_pin = (s.id, a_m) in pins, (s.id, b_m) in pins
            if a_pin and b_pin:
                continue  # sabitlenen kalışın içi (DİŞ'te art arda aylar)
            for t in (INTENSITY_YOGUN, INTENSITY_HAFIF):
                if a_m in solve_set and b_m in solve_set:
                    av = vars_for(s.id, a_m, lambda u: u.intensity == t)
                    bv = vars_for(s.id, b_m, lambda u: u.intensity == t)
                    if av and bv:
                        model.AddAtMostOne(av + bv)
                elif a_m in solve_set and b_m not in solve_set:
                    hu = hist_by_student_month.get((s.id, b_m))
                    if a_pin:
                        continue  # sabitlenen hücre engellenmez
                    if hu is not None and hu.intensity == t:
                        for v in vars_for(s.id, a_m, lambda u: u.intensity == t):
                            model.Add(v == 0)
                elif b_m in solve_set and a_m not in solve_set:
                    hu = hist_by_student_month.get((s.id, a_m))
                    if b_pin:
                        continue  # sabitlenen hücre engellenmez
                    if hu is not None and hu.intensity == t:
                        for v in vars_for(s.id, b_m, lambda u: u.intensity == t):
                            model.Add(v == 0)

    # sezon zorunlulukları: her karşılanmamış borç kalan aylarda kapatılmalı
    # — SERT kısıt (açgözlü lookahead değil). Borçlar v1 branşlarından ya da
    # v2 gereksinimlerinden gelir; buradan sonrası farkı görmez.
    # "Tercih" borçları sert kısıt kurmaz, aşağıda amaç fonksiyonunda
    # ödüllendirilir (soft_bonus).
    soft_bonus: list = []
    for s in students:
        for o in obligations[s.id]:
            cover = [
                x[(s.id, uid, m)]
                for uid in o.unit_ids
                for m in solve_months
                if (s.id, uid, m) in x
            ]
            if not o.hard:
                # tercih: sert kısıt yok, yalnız amaç fonksiyonunda ödül
                for v in cover:
                    soft_bonus.append(v)
                continue
            # Madde 1 gereği aynı bölüme iki kez gidilmez: borcu kapatabilecek
            # ziyaret sayısının üst sınırı, uygun AYRI BİRİM ADI sayısıdır
            # (birim×ay çifti sayısı değil).
            reachable = {
                key_of[uid]
                for uid in o.unit_ids
                for m in solve_months
                if (s.id, uid, m) in x
            }
            if len(reachable) >= o.count:
                model.Add(sum(cover) >= o.count)
            else:
                kalan = "kalan aylarda hiçbir uygun birimle karşılanamıyor"
                if o.count > 1:
                    kalan = (
                        f"kalan aylarda {o.count} kez karşılanamıyor "
                        f"(yalnız {len(reachable)} uygun birim var ve aynı "
                        "bölüme ikinci kez gidilemez)"
                    )
                return SeasonSolveResult(
                    status="INFEASIBLE",
                    infeasible_reasons=[
                        f"{s.full_name}: {o.label} zorunluluğu {kalan}."
                    ],
                )

    # özel kurallar (her ay yalnız kuralın zaman penceresi içindeyse)
    student_id_set = {s.id for s in students}
    st_by_id = {s.id: s for s in students}
    for (sid, m), uid in pins.items():
        if m not in solve_set:
            continue
        if (sid, uid, m) not in x:
            # _pin_conflicts cinsiyet/yasak/pasiflik gibi sebepleri zaten
            # yakaladı; buraya düşmek beklenmez ama sessiz kalmamalı
            u = catalog_by_id.get(uid)
            return SeasonSolveResult(
                status="INFEASIBLE",
                infeasible_reasons=[
                    f"{st_by_id[sid].full_name} → {m} "
                    f"{u.display_name if u else '?'} sabit ataması "
                    "uygulanamıyor."
                ],
            )
        model.Add(x[(sid, uid, m)] == 1)
    for rule in custom_rules:
        if rule.type == RULE_SABIT_ATAMA:
            continue
        win_months = [m for m in solve_months if rule_active_in_month(rule, m, months)]
        if not win_months:
            continue
        if rule.type == RULE_BIRIM_YASAK:
            banned_keys = _banned_keys(rule, catalog_by_id)
            for sid in rule.student_ids:
                if sid not in student_id_set:
                    continue
                for u in active_units:
                    if key_of[u.id] not in banned_keys:
                        continue
                    for m in win_months:
                        if (sid, u.id, m) in x:
                            model.Add(x[(sid, u.id, m)] == 0)
            continue
        ids = [sid for sid in rule.student_ids if sid in student_id_set]
        if len(ids) < 2:
            continue
        if rule.type == RULE_AYRI_TUT:
            for m in win_months:
                for u in active_units:
                    pair = [x[(sid, u.id, m)] for sid in ids if (sid, u.id, m) in x]
                    if len(pair) > 1:
                        model.AddAtMostOne(pair)
        elif rule.type == RULE_BIRLIKTE_TUT:
            first = ids[0]
            for other in ids[1:]:
                for m in win_months:
                    for u in active_units:
                        a = x.get((first, u.id, m))
                        b = x.get((other, u.id, m))
                        if a is not None and b is not None:
                            model.Add(a == b)
                        elif a is not None:
                            model.Add(a == 0)
                        elif b is not None:
                            model.Add(b == 0)

    # ---- Objective ----
    penalties: list[cp_model.LinearExpr] = []
    pool_units = [u for u in active_units if u.pool]
    genders_present = {s.gender for s in students if s.gender}

    # "Tercih" gereksinimleri: karşılanması ÖDÜLLENDİRİLİR (negatif ceza),
    # zorunlu değil. Ağırlık core_branch_early ile aynı aileden — zorunlu
    # kuralları ezmeyecek kadar küçük.
    for v in soft_bonus:
        penalties.append(-weights["core_branch_early"] * v)

    for m in solve_months:
        # madde 4: havuz doluluk yayılımı
        if len(pool_units) >= 2:
            mx = model.NewIntVar(0, len(students), f"pmax_{m}")
            mn = model.NewIntVar(0, len(students), f"pmin_{m}")
            for u in pool_units:
                model.Add(occ[(u.id, m)] <= mx)
                model.Add(occ[(u.id, m)] >= mn)
            penalties.append(weights["pool_balance"] * (mx - mn))
        # eşit dağıtımdaki FAZLALIK yoğun havuz birimlerine düşsün (tercih;
        # pool_balance'tan küçük ağırlık → dengeyi bozmaz)
        w_surplus = weights.get("intensive_surplus", 2)
        if w_surplus:
            for u in pool_units:
                if u.intensity == INTENSITY_YOGUN:
                    for s in students:
                        if (s.id, u.id, m) in x:
                            penalties.append(-w_surplus * x[(s.id, u.id, m)])
        # madde 4: tekli birimler boş kalmasın
        for u in active_units:
            if u.single_slot:
                empty = model.NewBoolVar(f"empty_{u.id}_{m}")
                model.Add(occ[(u.id, m)] == 0).OnlyEnforceIf(empty)
                model.Add(occ[(u.id, m)] >= 1).OnlyEnforceIf(empty.Not())
                penalties.append(weights["single_slot_fill"] * empty)
        # madde 21: havuzda kız/erkek dengesi
        if len(genders_present) == 2:
            wg = weights.get("gender_balance", 2)
            for u in pool_units:
                if u.gender_restriction:
                    continue
                diff = model.NewIntVar(-len(students), len(students), f"gd_{u.id}_{m}")
                model.Add(
                    diff
                    == sum(x[(s.id, u.id, m)] for s in students
                           if s.gender == "K" and (s.id, u.id, m) in x)
                    - sum(x[(s.id, u.id, m)] for s in students
                          if s.gender == "E" and (s.id, u.id, m) in x)
                )
                gap = model.NewIntVar(0, len(students), f"gap_{u.id}_{m}")
                model.AddAbsEquality(gap, diff)
                penalties.append(wg * gap)

    # yedek birim + ebelik önceliği (her yerleştirme başına)
    ebelik_students = {s.id for s in students if s.program == PROGRAM_EBELIK}
    for (sid, uid, m), var in x.items():
        u = catalog_by_id[uid]
        if u.reserve:
            penalties.append(weights.get("reserve_use", 15) * var)
        if u.ebelik_priority and ebelik_students and sid not in ebelik_students:
            penalties.append(weights["ebelik_priority"] * var)

    # madde 19: geçmişte birlikte olmuş ikili yine aynı birime düşmesin
    together_count: dict[tuple[str, str], int] = defaultdict(int)
    by_month_unit: dict[tuple[str, str], list[str]] = defaultdict(list)
    for a in history:
        by_month_unit[(a.month, a.unit_id)].append(a.student_id)
    for ids in by_month_unit.values():
        for s1, s2 in itertools.combinations(sorted(ids), 2):
            together_count[(s1, s2)] += 1
    for (s1, s2), count in together_count.items():
        if s1 not in student_id_set or s2 not in student_id_set:
            continue
        for u in active_units:
            for m in solve_months:
                a = x.get((s1, u.id, m))
                b = x.get((s2, u.id, m))
                if a is None or b is None:
                    continue
                both = model.NewBoolVar(f"pair_{s1}_{s2}_{u.id}_{m}")
                model.Add(a + b - 1 <= both)
                penalties.append(weights["repeat_pair"] * count * both)

    model.Minimize(sum(penalties) if penalties else 0)

    solver = cp_model.CpSolver()
    taban = float(
        settings["solver"].get(
            "season_time_limit_seconds",
            DEFAULT_SETTINGS["solver"]["season_time_limit_seconds"],
        )
    )
    solver.parameters.num_workers = int(settings["solver"].get("num_workers", 1))
    if random_seed is not None:
        solver.parameters.random_seed = (
            random_seed * 2654435761 + 101
        ) % (2**31)
        solver.parameters.randomize_search = True

    # KADEMELİ DENEME: süre içinde sonuç alınamazsa (UNKNOWN) limiti büyütüp
    # kendiliğinden yeniden dener. Amaç kullanıcıyı "çözüm süresini artırın"
    # gibi teknik bir ayara yönlendirmemek — uygulama sabırlı davranmayı kendi
    # bilir. Makine hızı bilinmediği için (eski bilgisayar) sabit bir sayı
    # yerine kademe kullanılıyor: hızlı makine ilk denemede biter, yavaş
    # makine kendiliğinden daha çok süre alır.
    #
    # INFEASIBLE'da ASLA tekrar denenmez: çözümsüzlük matematiksel bir kanıt,
    # daha uzun beklemek sonucu değiştirmez (yalnız kullanıcıyı bekletir).
    kademeler = [taban, taban * 2, taban * 4]
    status = None
    for i, limit in enumerate(kademeler):
        solver.parameters.max_time_in_seconds = limit
        status = solver.Solve(model)
        if status != cp_model.UNKNOWN:
            break
        if on_retry and i + 1 < len(kademeler):
            on_retry(i + 2, len(kademeler), kademeler[i + 1])

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        result = SeasonSolveResult(
            status="OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE",
            objective=solver.ObjectiveValue(),
        )
        for (sid, uid, m), var in x.items():
            if solver.Value(var):
                result.assignments[(sid, m)] = uid
        return result

    if status == cp_model.INFEASIBLE:
        return SeasonSolveResult(
            status="INFEASIBLE",
            infeasible_reasons=[
                "Bütün sezonu birlikte sağlayan bir çözüm yok: veri yapısal "
                "olarak çözümsüz (örn. kontenjanlar, cinsiyet kısıtları ve "
                "tekrar yasağı birlikte tutmuyor)."
            ],
        )

    return SeasonSolveResult(
        status="UNKNOWN",
        infeasible_reasons=[
            "Bu sezon bilgisayarın rahat çözebileceğinden daha zor: uygulama "
            f"giderek daha uzun süre denedi ({int(kademeler[-1])} saniyeye "
            "kadar) ama kesin sonuca ulaşamadı. Bu, çözümü OLMADIĞI anlamına "
            "gelmez. En işe yarar adım kuralları biraz gevşetmek: "
            "kontenjanlara bir-iki kişilik pay bırakmak ya da bir "
            "gereksinimi 'tercih'e çevirmek genelde yeter."
        ],
    )
