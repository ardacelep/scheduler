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
    Student,
    Unit,
    BRANCH_DOGUM_SALONU,
    BRANCH_LABELS,
    PROGRAM_EBELIK,
    RULE_AYRI_TUT,
    RULE_BIRLIKTE_TUT,
    RULE_SABIT_ATAMA,
    DEFAULT_SETTINGS,
)
from .normalize import normalize_key


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
    "dis": "Madde 9 (Diş Pol muafiyeti): Diş kontenjanı, muaf olmayan "
           "öğrencilerle doldurulamıyor olabilir.",
    "must_fill": "Madde 17 (FTR'ye 1 kız 1 erkek): FTR çifti için uygun kız/erkek "
                 "öğrenci kalmamış olabilir.",
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


def _prefeasibility_reasons(
    students: list[Student],
    units: list[Unit],
    visited: dict[str, set[str]],
    remaining: int,
    unmet: dict[str, list[str]],
    blocked_intensity: dict[str, set[str]],
) -> list[str]:
    """CP-SAT'tan önce ucuz, kesin çelişki kontrolleri.

    Buradan dönen her madde tek başına çözümsüzlüğü kanıtlar; kullanıcıya
    unsat core'dan çok daha somut bir açıklama verir ("DİŞ için uygun
    öğrenci kalmadı" gibi).

    `unmet`: öğrenci başına, sezon sonuna kadar hâlâ görülmesi gereken
    branşlar (settings.season_requirements + madde 7 doğum salonu).
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

    # Sezon zorunlulukları: ayda en çok 1 branş karşılanabilir → kalan ay
    # sayısı, karşılanmamış zorunluluk sayısını taşımıyorsa çözüm yoktur.
    for s in students:
        if len(unmet[s.id]) > remaining + 1:
            labels = ", ".join(BRANCH_LABELS.get(b, b) for b in unmet[s.id])
            reasons.append(
                f"{s.full_name}: kalan {remaining + 1} ayda karşılanması "
                f"gereken {len(unmet[s.id])} sezon zorunluluğu var ({labels}) "
                "— ayda en fazla biri karşılanabilir, yetişmez."
            )

    if remaining == 0:
        # Son ay: her branş için, o branşı görmek zorunda olanlar kontenjana sığmalı
        need_by_branch: dict[str, int] = defaultdict(int)
        for s in students:
            for b in unmet[s.id]:
                need_by_branch[b] += 1
        for b, count in need_by_branch.items():
            quota = sum(u.quota for u in units if u.branch_category == b)
            if count > quota:
                reasons.append(
                    f"Son ayda {BRANCH_LABELS.get(b, b)} görmesi gereken "
                    f"{count} öğrenci var ama bu branştaki birimlerin toplam "
                    f"kontenjanı {quota}."
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
    _diagnostic: bool = False,
) -> SolveResult:
    """`students` (tek grup) için `month` ayının atamasını çözer.

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

    # ---- sezon zorunlulukları: her öğrenci sezon boyunca hangi branşları
    # görmüş olmalı? (settings.season_requirements; yalnız bu grupta o
    # branştan aktif birim varsa uygulanır — palyatifsiz bir hastanede
    # palyatif zorunluluğu çözümü kilitlemesin.) Madde 7 (ebelik → doğum
    # salonu) her zaman ayrıca eklenir.
    seen_branches: dict[str, set[str]] = {}
    for s in students:
        seen_branches[s.id] = {
            catalog_by_id[a.unit_id].branch_category
            for a in history
            if a.student_id == s.id and a.unit_id in catalog_by_id
        }
    available_branches = {u.branch_category for u in units}
    req_branches = [
        r["branch"]
        for r in settings.get("season_requirements", [])
        if r.get("branch") and r["branch"] in available_branches
    ]
    unmet: dict[str, list[str]] = {}
    for s in students:
        needs = [b for b in req_branches if b not in seen_branches[s.id]]
        if (
            s.program == PROGRAM_EBELIK
            and BRANCH_DOGUM_SALONU not in seen_branches[s.id]
        ):
            needs.append(BRANCH_DOGUM_SALONU)
        unmet[s.id] = needs

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

    # Özel kurallar: ayrı tut / birlikte tut (sabit atama yukarıda locked'a girdi)
    student_id_set = {s.id for s in students}
    for rule in custom_rules:
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
    branch_unit_ids: dict[str, list[str]] = defaultdict(list)
    for u in units:
        branch_unit_ids[u.branch_category].append(u.id)

    for s in students:
        need_now = len(unmet[s.id]) - remaining
        if need_now >= 1:
            uids = [
                uid for b in unmet[s.id] for uid in branch_unit_ids.get(b, [])
            ]
            label = (
                "deadline_dogum"
                if unmet[s.id] == [BRANCH_DOGUM_SALONU]
                else "deadline_core"
            )
            model.Add(
                sum(x[(s.id, uid)] for uid in uids) >= 1
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
        for b in unmet[s.id]:
            mult = 3 if b == BRANCH_DOGUM_SALONU else 1
            for uid in branch_unit_ids.get(b, []):
                penalties.append(
                    -weights["core_branch_early"] * urgency * mult
                    * x[(s.id, uid)]
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
