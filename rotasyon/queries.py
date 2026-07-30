"""Salt-okunur yardımcı sorgular (UI ekranları bunları kullanır)."""
from __future__ import annotations

from dataclasses import dataclass

from .models import Assignment, Student, Unit


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


# ---------------------------------------------------------------------------
# Grup-bazı birim dağılımı (Grup Dağılımı ekranı)
# ---------------------------------------------------------------------------
@dataclass
class GroupUnitRow:
    """Bir grubun bir biriminin dağılım satırı."""

    unit_id: str
    name: str  # unit.name_with_gender
    quota: int
    active: bool  # False = bu grupta iptal (gri gösterilir)


@dataclass
class GroupDistribution:
    """Bir grubun birim dağılımının özeti.

    Kullanıcının el tablosunun karşılığı: hangi birime kaç kişi (kontenjan)
    ve toplam, grubun öğrenci sayısına oturuyor mu.
    """

    group: int
    student_count: int  # yalnız aktif öğrenci
    rows: list[GroupUnitRow]  # o grubun birimleri, ada göre sıralı
    active_quota_total: int  # yalnız AKTİF birimlerin kontenjan toplamı

    @property
    def balance(self) -> int:
        """Aktif kontenjan − öğrenci sayısı. 0 = tam oturur, >0 havuz payı,
        <0 bazı öğrenciye yer yok."""
        return self.active_quota_total - self.student_count


def group_unit_distribution(
    units: list[Unit], students: list[Student], group: int
) -> GroupDistribution:
    """Bir grup için birim dağılımı. Yalnız o gruba ait birimler (group ∈
    {0, g}) ve yalnız aktif öğrenciler hesaba katılır.

    İptal (pasif) birimler satır olarak DÖNER (kullanıcı 'atlamayayım diye'
    görünür istiyor) ama kontenjan toplamına katılmaz.
    """
    g_units = [u for u in units if u.group in (0, group)]
    g_units.sort(key=lambda u: u.name)
    rows = [
        GroupUnitRow(
            unit_id=u.id,
            name=u.name_with_gender,
            quota=u.quota,
            active=u.active,
        )
        for u in g_units
    ]
    active_total = sum(u.quota for u in g_units if u.active)
    n_active_students = sum(
        1 for s in students
        if s.group == group and getattr(s, "active", True)
    )
    return GroupDistribution(
        group=group,
        student_count=n_active_students,
        rows=rows,
        active_quota_total=active_total,
    )
