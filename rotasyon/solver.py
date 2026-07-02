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
    Student,
    Unit,
    CORE_BRANCHES,
    BRANCH_DOGUM_SALONU,
    PROGRAM_EBELIK,
    DEFAULT_SETTINGS,
)
from .normalize import normalize_key


@dataclass
class SolveResult:
    status: str  # "OPTIMAL" | "FEASIBLE" | "INFEASIBLE" | "UNKNOWN"
    assignments: dict[str, str] = field(default_factory=dict)  # student_id -> unit_id
    infeasible_reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # kullanıcıya bilgi notları

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
    "deadline_core": "Madde 6 (Haziran'a kadar dahili/cerrahi/YB/palyatif görme): "
                     "son aylarda bu birimlerde yeterli kontenjan yok.",
    "deadline_dogum": "Madde 7 (ebelik öğrencileri doğum salonu görme): doğum "
                      "salonu kontenjanı ebelik öğrencilerine yetmiyor.",
    "locked": "Elle sabitlenen atamalar diğer kurallarla çelişiyor.",
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


def solve_month(
    students: list[Student],
    units: list[Unit],
    month: str,
    history: list[Assignment],
    settings: dict | None = None,
    locked: dict[str, str] | None = None,
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
    locked = locked or {}

    catalog_by_id = {u.id: u for u in units}  # geçmiş yorumu için tam katalog
    units = [u for u in units if u.active and u.quota > 0]
    units_by_id = {u.id: u for u in units}
    remaining = _remaining_months(month, months)

    model = cp_model.CpModel()

    # Assumption literal'ları: infeasible analizinde hangi kural ailesinin
    # çekirdekte olduğunu görmek için her sert kısıt ailesi bir literal'a bağlanır.
    assumptions: dict[str, cp_model.IntVar] = {
        name: model.NewBoolVar(f"assume_{name}") for name in _REASON_LABELS
    }

    # ---- değişkenler: uygunluk ön filtresiyle x[s,u] ----
    x: dict[tuple[str, str], cp_model.IntVar] = {}
    visited: dict[str, set[str]] = {
        s.id: visited_unit_keys(s.id, history, catalog_by_id) for s in students
    }
    # Aynı ayda başka gruba/aya ait çakışan atama olmadığı varsayılır (UI temizler).

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

    # ---- Madde 6/7: Haziran'a kadar zorunluluklar ----
    # Kalan ay sayısı 0 ise (son ay) sert kısıt; öncesinde objective bonusu.
    core_unit_ids = [u.id for u in units if u.branch_category in CORE_BRANCHES]
    dogum_unit_ids = [u.id for u in units if u.branch_category == BRANCH_DOGUM_SALONU]

    def _has_core_history(s: Student) -> bool:
        cats = {
            catalog_by_id[a.unit_id].branch_category
            for a in history
            if a.student_id == s.id and a.unit_id in catalog_by_id
        }
        return bool(cats & set(CORE_BRANCHES))

    def _has_dogum_history(s: Student) -> bool:
        return any(
            a.student_id == s.id
            and a.unit_id in catalog_by_id
            and catalog_by_id[a.unit_id].branch_category == BRANCH_DOGUM_SALONU
            for a in history
        )

    core_needed = [s for s in students if not _has_core_history(s)]
    dogum_needed = [
        s
        for s in students
        if s.program == PROGRAM_EBELIK and not _has_dogum_history(s)
    ]
    if remaining == 0:
        for s in core_needed:
            model.Add(
                sum(x[(s.id, uid)] for uid in core_unit_ids) >= 1
            ).OnlyEnforceIf(assumptions["deadline_core"])
        for s in dogum_needed:
            model.Add(
                sum(x[(s.id, uid)] for uid in dogum_unit_ids) >= 1
            ).OnlyEnforceIf(assumptions["deadline_dogum"])

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

    # Madde 6/7'yi erken aylarda karşılama bonusu (negatif ceza).
    # Aciliyet kalan ay azaldıkça artar.
    urgency = max(1, len(months) - remaining)
    for s in core_needed:
        for uid in core_unit_ids:
            penalties.append(
                -weights["core_branch_early"] * urgency * x[(s.id, uid)]
            )
    for s in dogum_needed:
        for uid in dogum_unit_ids:
            penalties.append(
                -weights["core_branch_early"] * urgency * 3 * x[(s.id, uid)]
            )

    model.Minimize(sum(penalties) if penalties else 0)

    # ---- çözüm ----
    model.AddAssumptions(list(assumptions.values()))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(
        settings["solver"].get("time_limit_seconds", 30)
    )
    solver.parameters.num_workers = 8
    status = solver.Solve(model)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        result = SolveResult(
            status="OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE"
        )
        for s in students:
            for u in units:
                if solver.Value(x[(s.id, u.id)]):
                    result.assignments[s.id] = u.id
        return result

    if status == cp_model.INFEASIBLE:
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

    return SolveResult(
        status="UNKNOWN",
        infeasible_reasons=[
            "Süre sınırı içinde çözüm bulunamadı; süreyi artırmayı deneyin."
        ],
    )
