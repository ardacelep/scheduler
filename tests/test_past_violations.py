"""Geçmişe dönük (kapsam dışı) ihlal gösterim ayarı: partition_violations."""
from rotasyon.rules import ERROR, WARNING, Violation, blocking_errors
from ui.common import partition_violations


def _v(rule_no, sev=ERROR, month="", student_id="", unit_id=""):
    return Violation(
        rule_no=rule_no, severity=sev, message="x",
        month=month, student_id=student_id, unit_id=unit_id,
    )


def test_partition_by_month_and_student():
    v_cur_month = _v(12, month="EKİM", unit_id="u1")
    v_cur_student = _v(1, month="KASIM", student_id="s1")  # başka ay ama öğrenci kapsamda
    v_past = _v(12, month="EYLÜL", unit_id="u1")
    v_struct = _v(0)  # aysız/öğrencisiz → yapısal, hep güncel
    v_warn_past = _v(21, sev=WARNING, month="EYLÜL")
    current, past = partition_violations(
        [v_cur_month, v_cur_student, v_past, v_struct, v_warn_past],
        {"EKİM"}, {"s1"},
    )
    assert current == [v_cur_month, v_cur_student, v_struct]
    assert past == [v_past, v_warn_past]


def test_partition_empty_scope_everything_month_specific_is_past():
    """Kural Kontrolü senaryosu: kapsam boş → aya/öğrenciye bağlı her ihlal geçmiş,
    yalnız yapısal (aysız) güncel kalır."""
    v_month = _v(12, month="EYLÜL")
    v_struct = _v(0)
    current, past = partition_violations([v_month, v_struct], set(), set())
    assert current == [v_struct]
    assert past == [v_month]


def test_partition_current_errors_match_blocking_errors():
    """partition 'current' hata kümesi, blocking_errors ile BİREBİR aynı kapsam
    mantığını kullanır (gösterim ile kayıt kapısı tutarlı kalsın)."""
    vs = [
        _v(12, month="EKİM", unit_id="u1"),
        _v(1, month="KASIM", student_id="s1"),
        _v(12, month="EYLÜL", unit_id="u1"),
        _v(0),
        _v(21, sev=WARNING, month="EYLÜL"),
    ]
    months, students = {"EKİM"}, {"s1"}
    current, _past = partition_violations(vs, months, students)
    current_errors = [v for v in current if v.severity == ERROR]
    assert current_errors == blocking_errors(vs, months, students)


def test_partition_none_scope_is_empty_scope():
    v = _v(12, month="EYLÜL")
    current, past = partition_violations([v])  # scope yok
    assert current == [] and past == [v]
