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


def plan_remaining(
    students: list[Student],
    units: list[Unit],
    months: list[str],
    assignments: list[Assignment],
    settings: dict | None = None,
    custom_rules=None,
    groups: list[int] | None = None,
    on_month: Callable[[int, str], None] | None = None,
):
    """Seçili gruplar için kalan tüm ayları sırayla çözer.

    Bir ay çözülemezse o grup için durulur (önceki aylar geçerli kalır),
    diğer gruplara devam edilir. Hiçbir şey kaydedilmez; çağıran taraf
    döndürülen atamaları kalıcılaştırır.

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
        solved[g] = []
        for m in remaining_months(months, assignments, g_ids):
            if on_month:
                on_month(g, m)
            r = solve_month(
                g_students,
                g_units,
                m,
                history=history,
                settings=settings,
                custom_rules=custom_rules,
            )
            if not r.ok:
                failed[g] = (m, r.infeasible_reasons)
                break
            month_assignments = [
                Assignment(student_id=sid, month=m, unit_id=uid)
                for sid, uid in r.assignments.items()
            ]
            history += month_assignments
            new_assignments += month_assignments
            solved[g].append(m)
    return new_assignments, solved, failed
