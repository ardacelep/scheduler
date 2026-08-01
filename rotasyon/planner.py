"""Sezon planlayıcı — kalan ayları toplu üretir.

İki yol vardır:
- `plan_season` (arayüzün kullandığı): her grubun bütün kalan aylarını TEK
  CP-SAT modelinde birlikte çözer (bkz. solver.solve_season). Köşeye
  sıkışma imkânsızdır; süreye sığmazsa açgözlü yola geri düşer.
- `plan_remaining`: açgözlü ay-bazlı yol (geri-düşüş ve testler için). Dolu
  aylar geçmiş kabul edilir, ilk boş aydan sona kadar sırayla çözülür; bir
  ay tıkanırsa grubun kalanı farklı tohumla yeniden denenir.

İkisi de aynı biçimde döner ve hiçbir şey kaydetmez; çağıran taraf onaylar.
"""
from __future__ import annotations

from typing import Callable

from .models import Assignment, Student, Unit
from .solver import solve_month, solve_season


def remaining_months(
    months: list[str], assignments: list[Assignment], student_ids: set[str]
) -> list[str]:
    """Verilen öğrenci kümesi için henüz hiç ataması olmayan aylar (sırayla)."""
    done = {a.month for a in assignments if a.student_id in student_ids}
    return [m for m in months if m not in done]


def _plan_group(
    g_students,
    g_units,
    todo: list[str],
    history0: list[Assignment],
    settings,
    custom_rules,
    on_month,
    group: int,
    attempt: int,
    seed: int | None,
    requirements=None,
):
    """Bir grubun kalan aylarını tek geçişte çözer.

    Dönüş: (yeni atamalar, çözülen aylar, (ay, nedenler) | None)
    """
    history = list(history0)
    new: list[Assignment] = []
    solved: list[str] = []
    for m in todo:
        if on_month:
            on_month(group, m, attempt)
        r = solve_month(
            g_students,
            g_units,
            m,
            history=history,
            settings=settings,
            custom_rules=custom_rules,
            random_seed=seed,
            requirements=requirements,
        )
        if not r.ok:
            return new, solved, (m, r.infeasible_reasons)
        month_assignments = [
            Assignment(student_id=sid, month=m, unit_id=uid)
            for sid, uid in r.assignments.items()
        ]
        history += month_assignments
        new += month_assignments
        solved.append(m)
    return new, solved, None


# Ay ay çözüm "açgözlüdür": erken bir ayın (tek başına kusursuz) çözümü,
# ileriki bir ayı çözümsüz bırakabilir. Böyle bir tıkanmada grubun kalan
# ayları farklı tohumla baştan denenir; yapısal çözümsüzlükler (örn. erkek
# sayısı yetmiyor) her denemede aynı ayda durur, en iyi deneme raporlanır.
MAX_ATTEMPTS = 3


def plan_remaining(
    students: list[Student],
    units: list[Unit],
    months: list[str],
    assignments: list[Assignment],
    settings: dict | None = None,
    custom_rules=None,
    groups: list[int] | None = None,
    on_month: Callable[[int, str, int], None] | None = None,
    requirements=None,
):
    """Seçili gruplar için kalan tüm ayları sırayla çözer.

    Bir ay çözülemezse grubun kalan ayları farklı tohumla yeniden denenir
    (en çok MAX_ATTEMPTS geçiş); yine olmazsa en ileri giden denemenin
    ayları tutulur, diğer gruplara devam edilir. Hiçbir şey kaydedilmez;
    çağıran taraf döndürülen atamaları kalıcılaştırır.

    on_month(grup, ay, deneme_no) her çözüm girişiminde çağrılır.

    Dönüş: (yeni atamalar, {grup: çözülen aylar}, {grup: (ay, nedenler)})
    """
    groups = groups or sorted({s.group for s in students})
    new_assignments: list[Assignment] = []
    solved: dict[int, list[str]] = {}
    failed: dict[int, tuple[str, list[str]]] = {}
    for g in groups:
        g_students = [s for s in students if s.group == g and s.active]
        g_ids = {s.id for s in g_students}
        g_units = [u for u in units if u.group in (0, g)]
        history = [a for a in assignments if a.student_id in g_ids]
        todo = remaining_months(months, assignments, g_ids)
        best: tuple[list[Assignment], list[str], tuple | None] | None = None
        prev_failure = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            result = _plan_group(
                g_students, g_units, todo, history, settings,
                custom_rules, on_month, g, attempt,
                seed=None if attempt == 1 else attempt,
                requirements=requirements,
            )
            if best is None or len(result[1]) > len(best[1]):
                best = result
            if result[2] is None:
                break
            if result[2] == prev_failure:
                # iki deneme aynı ayda aynı nedenle durdu: tıkanma yol
                # seçiminden değil veriden (yapısal) — devam etmek boşuna
                break
            prev_failure = result[2]
        new, months_ok, failure = best
        new_assignments += new
        solved[g] = months_ok
        if failure is not None:
            failed[g] = failure
    return new_assignments, solved, failed


def plan_season(
    students: list[Student],
    units: list[Unit],
    months: list[str],
    assignments: list[Assignment],
    settings: dict | None = None,
    custom_rules=None,
    groups: list[int] | None = None,
    on_group=None,
    on_month=None,
    requirements=None,
):
    """Kalan ayları toplu planlar — açgözlü birincil, ortak model emniyet ağı.

    Ölçüm (74 öğrencilik gerçek sezon): açgözlü+yeniden-deneme yolu ayları
    hızlı çözüyor ve yumuşak hedeflerde (madde 19/21) daha iyi sonuç
    veriyor; ortak model (solve_season) ise 15 bin değişkende ikili-tekrar
    cezasını süre içinde optimize edemiyor ama FİZİBİLİTEYİ garanti ediyor
    ve yapısal çözümsüzlüğü saniyeler içinde kanıtlıyor. Bu yüzden:

      1. Grup açgözlü yolla çözülür (hızlı + iyi kalite).
      2. Açgözlü bir ayda tıkanırsa ortak model devreye girer: geçerli bir
         sezon VARSA onu bulur (açgözlünün ıskaladığı köşe kurtulur); ortak
         model de çözümsüz derse veri yapısal olarak çözümsüzdür ve
         açgözlünün ürettiği somut Türkçe neden raporlanır.

    Böylece geçerli sezon varsa kullanıcı onu mutlaka alır, yumuşak kalite
    ise hiçbir zaman salt-açgözlüden kötü olmaz.

    on_group(grup, faz) çağrılır: faz "cozum" (açgözlü) | "ortak" (emniyet).

    Dönüş: (yeni atamalar, {g: çözülen aylar}, {g: (ay, nedenler)})
    """
    groups = groups or sorted({s.group for s in students})
    new_assignments: list[Assignment] = []
    solved: dict[int, list[str]] = {}
    failed: dict[int, tuple[str, list[str]]] = {}
    order = {m: i for i, m in enumerate(months)}
    for g in groups:
        g_students = [s for s in students if s.group == g and s.active]
        g_ids = {s.id for s in g_students}
        g_units = [u for u in units if u.group in (0, g)]
        history = [a for a in assignments if a.student_id in g_ids]
        todo = remaining_months(months, assignments, g_ids)
        if not todo:
            solved[g] = []
            continue

        # 1. Açgözlü birincil yol (yeniden-denemeli)
        if on_group:
            on_group(g, "cozum")
        new, sub_solved, sub_failed = plan_remaining(
            g_students, g_units, months, assignments,
            settings=settings, custom_rules=custom_rules, groups=[g],
            on_month=on_month, requirements=requirements,
        )
        if g not in sub_failed:
            new_assignments += new
            solved[g] = sub_solved.get(g, [])
            continue

        # 2. Açgözlü tıkandı → ortak model: gerçekten çözümsüz mü, yoksa
        #    açgözlü mü ıskaladı? Geçerli sezon varsa ortak model bulur.
        if on_group:
            on_group(g, "ortak")
        r = solve_season(
            g_students, g_units, months, todo, history=history,
            settings=settings, custom_rules=custom_rules,
            requirements=requirements,
        )
        if r.ok:
            new_assignments += [
                Assignment(student_id=sid, month=m, unit_id=uid)
                for (sid, m), uid in r.assignments.items()
            ]
            solved[g] = sorted(
                {m for (_sid, m) in r.assignments}, key=lambda m: order.get(m, 99)
            )
        else:
            # ortak model de çözemedi: yapısal — açgözlünün kısmi sonucu +
            # somut ay/neden raporu korunur
            new_assignments += new
            solved[g] = sub_solved.get(g, [])
            failed[g] = sub_failed[g]
    return new_assignments, solved, failed
