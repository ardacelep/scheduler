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
    "custom": "Özel kurallar (Veri Yönetimi → Kurallar): ayrı/birlikte tutma "
              "veya sabit atamalar diğer kurallarla çelişiyor olabilir.",
}


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
    """Kalan toplam ZORUNLU ziyaret borcu (ayda en fazla 1 kapatılabilir).

    Tercih gereksinimleri sayılmaz: karşılanmamaları sezonu çözümsüz yapmaz,
    dolayısıyla "kalan ay yetişmiyor" hesabına girmemeleri gerekir.
    """
    return sum(o.count for o in items if o.hard)


def _prefeasibility_reasons(
    students: list[Student],
    units: list[Unit],
    visited: dict[str, set[str]],
    remaining: int,
    unmet: dict[str, list[_Obligation]],
    blocked_intensity: dict[str, set[str]],
) -> list[str]:
    """CP-SAT'tan önce ucuz, kesin çelişki kontrolleri.

    Buradan dönen her madde tek başına çözümsüzlüğü kanıtlar; kullanıcıya
    unsat core'dan çok daha somut bir açıklama verir ("DİŞ için uygun
    öğrenci kalmadı" gibi).

    `unmet`: öğrenci başına, sezon sonuna kadar kapatılması gereken borçlar
    (v1 branş zorunlulukları ya da v2 gereksinimleri — ikisi de _Obligation).
    """
    reasons: list[str] = []
    total_quota = sum(u.quota for u in units)
    n = len(students)
    if total_quota < n:
        reasons.append(
            f"Toplam kontenjan ({total_quota}) öğrenci sayısının ({n}) altında; "
            "kontenjanları artırın veya birim ekleyin."
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
    for s in students:
        debt = _obligation_debt(unmet[s.id])
        if debt > remaining + 1:
            labels = ", ".join(o.label for o in unmet[s.id])
            reasons.append(
                f"{s.full_name}: kalan {remaining + 1} ayda karşılanması "
                f"gereken {debt} sezon zorunluluğu var ({labels}) "
                "— ayda en fazla biri karşılanabilir, yetişmez."
            )

    if remaining == 0:
        # Son ay: aynı borcu taşıyanlar o borcu kapatan birimlerin
        # kontenjanına sığmalı
        quota_by_unit = {u.id: u.quota for u in units}
        need_by_label: dict[str, int] = defaultdict(int)
        uids_by_label: dict[str, set[str]] = defaultdict(set)
        for s in students:
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
    _diagnostic: bool = False,
) -> SolveResult:
    """`students` (tek grup) için `month` ayının atamasını çözer.

    `requirements` (v2): verilirse sezon zorunlulukları bu gereksinim
    listesinden okunur. Verilmezse v1 yolu işler — settings.season_requirements
    branşları + koda gömülü madde 7 (ebelik → doğum salonu).

    `units` grubun TÜM birimlerini içermeli (pasifler dahil): atama yalnız
    aktif ve kontenjanlı birimlere yapılır, ama geçmiş yorumu (madde 1 tekrar
    yasağı, madde 6/7 kategori geçmişi) tam katalog üzerinden çalışır —
    pasifleştirilmiş bir birimin geçmişi kaybolmaz.

    locked: {student_id: unit_id} — yarı otomatik modda elle sabitlenen hücreler.
    """
    settings = settings or DEFAULT_SETTINGS
    months: list[str] = settings["months"]
    weights: dict = settings["solver"]["weights"]
    locked = dict(locked or {})
    custom_rules = [r for r in (custom_rules or []) if r.active]

    # Sabit atama kuralları bu ayın kilitli hücreleri gibi işlenir;
    # elle kilitlenen hücre (locked parametresi) öncelik taşır.
    for rule in custom_rules:
        if rule.type == RULE_SABIT_ATAMA and rule.month == month:
            for sid in rule.student_ids:
                locked.setdefault(sid, rule.unit_id)

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

    # CP-SAT'tan önce ucuz kesin kontroller: çelişki buradan yakalanırsa
    # somut Türkçe açıklamayla hemen dönülür (solver'ın kanıt araması gereksiz).
    if not _diagnostic:
        pre = _prefeasibility_reasons(
            students, units, visited, remaining, unmet, blocked_intensity
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
            if normalize_key(u.name) in visited[s.id]:
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
        need_now = _obligation_debt(unmet[s.id]) - remaining
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
        settings["solver"].get("time_limit_seconds", 5)
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
    if status == cp_model.UNKNOWN and not _diagnostic:
        # Eski/yavaş makine sigortası: süre içinde hiç çözüm bulunamadıysa
        # limiti 4 katına çıkarıp bir kez daha dene.
        solver.parameters.max_time_in_seconds *= 4
        status = solver.Solve(model)

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
            "Süre sınırı içinde çözüm bulunamadı; süreyi artırmayı deneyin."
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
) -> SeasonSolveResult:
    """`solve_months`'un TAMAMINI tek CP-SAT modelinde birlikte çözer.

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
    weights: dict = settings["solver"]["weights"]
    custom_rules = [r for r in (custom_rules or []) if r.active]
    solve_set = set(solve_months)

    catalog_by_id = {u.id: u for u in units}
    active_units = [u for u in units if u.active and u.quota > 0]

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
                if key_of[u.id] in visited[s.id]:
                    continue  # madde 1: sezon öncesinde görülmüş
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
            if k in visited[s.id]:
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
            for t in (INTENSITY_YOGUN, INTENSITY_HAFIF):
                if a_m in solve_set and b_m in solve_set:
                    av = vars_for(s.id, a_m, lambda u: u.intensity == t)
                    bv = vars_for(s.id, b_m, lambda u: u.intensity == t)
                    if av and bv:
                        model.AddAtMostOne(av + bv)
                elif a_m in solve_set and b_m not in solve_set:
                    hu = hist_by_student_month.get((s.id, b_m))
                    if hu is not None and hu.intensity == t:
                        for v in vars_for(s.id, a_m, lambda u: u.intensity == t):
                            model.Add(v == 0)
                elif b_m in solve_set and a_m not in solve_set:
                    hu = hist_by_student_month.get((s.id, a_m))
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
    for rule in custom_rules:
        if rule.type == RULE_SABIT_ATAMA:
            if rule.month in solve_set:
                for sid in rule.student_ids:
                    if (sid, rule.unit_id, rule.month) in x:
                        model.Add(x[(sid, rule.unit_id, rule.month)] == 1)
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
    solver.parameters.max_time_in_seconds = float(
        settings["solver"].get("season_time_limit_seconds", 60)
    )
    solver.parameters.num_workers = int(settings["solver"].get("num_workers", 1))
    if random_seed is not None:
        solver.parameters.random_seed = (
            random_seed * 2654435761 + 101
        ) % (2**31)
        solver.parameters.randomize_search = True
    status = solver.Solve(model)

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
            "Süre sınırı içinde bütün sezon için çözüm bulunamadı."
        ],
    )
