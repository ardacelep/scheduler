"""Salt-okunur yardımcı sorgular (UI ekranları bunları kullanır)."""
from __future__ import annotations

from .models import Assignment, Unit


def student_history(
    student_id: str,
    assignments: list[Assignment],
    months: list[str],
    units_by_id: dict[str, Unit],
) -> list[tuple[str, str, str]]:
    """Madde 16: öğrencinin ay sırasına dizilmiş geçmişi.

    (ay, birim adı, gün notu) üçlüleri döner; birim silinmişse ad yerine
    "(silinmiş birim)" yazılır ki geçmiş kaybolmasın.
    """
    order = {m: i for i, m in enumerate(months)}
    items = [a for a in assignments if a.student_id == student_id]
    items.sort(key=lambda a: order.get(a.month, len(order)))
    return [
        (
            a.month,
            units_by_id[a.unit_id].name if a.unit_id in units_by_id else "(silinmiş birim)",
            a.day_note,
        )
        for a in items
    ]
