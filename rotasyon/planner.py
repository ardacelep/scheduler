"""Sezon planlayıcı — kalan ayları tek seferde, sırayla çözer.

Sezon başı (hiç atama yok) ve sezon ortası (bazı aylar içe aktarılmış /
elle yapılmış) durumlarını aynı şekilde ele alır: dolu aylar geçmiş kabul
edilir, ilk boş aydan sezon sonuna kadar sırayla devam edilir. Her ayın
çözümü bir sonrakinin geçmişine eklenir; böylece madde 1/6/7/19 sezon
bütününde tutarlı kalır.
"""
from __future__ import annotations

from typing import Callable

from .models import Assignment, Student, Unit
from .solver import solve_month


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
        g_students = [s for s in students if s.group == g]
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
