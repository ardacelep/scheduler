"""Grup-bazı birim dağılımı (queries.group_unit_distribution).

Kullanıcının el tablosunun karşılığı: her grubun birimleri + kontenjan
sayısı + toplamın öğrenci sayısına oturup oturmadığı.
"""
from rotasyon.models import Student, Unit
from rotasyon.queries import group_unit_distribution


def U(uid, group=1, quota=1, active=True, gender=""):
    return Unit(id=uid, name=uid.upper(), group=group, quota=quota,
                active=active, gender_restriction=gender)


def S(i, group=1, active=True):
    return Student(id=f"s{i}", full_name=f"Öğrenci {i}", gender="K",
                   group=group, active=active)


def test_only_units_of_that_group():
    units = [U("a", group=1), U("b", group=2), U("c", group=1)]
    d = group_unit_distribution(units, [], 1)
    assert sorted(r.unit_id for r in d.rows) == ["a", "c"]


def test_quota_total_counts_only_active():
    units = [U("a", quota=3), U("b", quota=2, active=False), U("c", quota=1)]
    d = group_unit_distribution(units, [], 1)
    # iptal birim satır olarak gelir ama toplama katılmaz
    assert len(d.rows) == 3
    assert d.active_quota_total == 4  # 3 + 1 (b hariç)
    inactive = [r for r in d.rows if not r.active]
    assert len(inactive) == 1 and inactive[0].unit_id == "b"


def test_balance_zero_when_capacity_matches_students():
    units = [U("a", quota=3), U("b", quota=2)]  # toplam 5
    students = [S(i) for i in range(5)]
    d = group_unit_distribution(units, students, 1)
    assert d.student_count == 5
    assert d.balance == 0


def test_balance_positive_is_pool_slack():
    units = [U("a", quota=5)]
    students = [S(i) for i in range(3)]
    assert group_unit_distribution(units, students, 1).balance == 2


def test_balance_negative_means_no_room():
    units = [U("a", quota=2)]
    students = [S(i) for i in range(5)]
    assert group_unit_distribution(units, students, 1).balance == -3


def test_inactive_students_not_counted():
    units = [U("a", quota=3)]
    students = [S(0), S(1), S(2, active=False)]
    assert group_unit_distribution(units, students, 1).student_count == 2


def test_other_group_students_not_counted():
    units = [U("a", quota=3, group=1)]
    students = [S(0, group=1), S(1, group=2)]
    assert group_unit_distribution(units, students, 1).student_count == 1


def test_group0_unit_appears_in_both_groups():
    units = [U("shared", group=0, quota=2)]
    assert group_unit_distribution(units, [], 1).rows[0].unit_id == "shared"
    assert group_unit_distribution(units, [], 2).rows[0].unit_id == "shared"


def test_name_uses_gender_suffix():
    units = [U("ftr", group=1, gender="E")]
    row = group_unit_distribution(units, [], 1).rows[0]
    assert "(Erkek)" in row.name


def test_rows_sorted_by_name():
    units = [U("zeta"), U("alfa"), U("beta")]
    names = [r.name for r in group_unit_distribution(units, [], 1).rows]
    assert names == sorted(names)
