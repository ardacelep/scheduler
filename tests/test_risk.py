"""İleriye dönük risk denetimi (rotasyon/risk.py).

Buradaki her senaryo "fark edildiğinde telafisi yok" sınıfından: kullanıcı
bunları sezon sonunda değil, olmadan önce görmeli.
"""
import pytest

from rotasyon.capacity import ERROR, WARNING
from rotasyon.models import (
    Assignment,
    BRANCH_CERRAHI,
    BRANCH_DAHILI,
    CustomRule,
    RULE_AYRI_TUT,
    RULE_BIRLIKTE_TUT,
    RULE_SABIT_ATAMA,
    Student,
    Unit,
)
from rotasyon.risk import (
    CAT_CUSTOM,
    CAT_QUOTA,
    CAT_RUNWAY,
    fixed_assignment_conflicts,
    forward_risks,
    risk_counts,
)

MONTHS = ["EYLÜL", "EKİM", "KASIM", "ARALIK"]


def S(i, **kw):
    base = dict(
        id=f"s{i}", full_name=f"Öğrenci {i}", gender="K", group=1
    )
    base.update(kw)
    return Student(**base)


def U(uid, **kw):
    base = dict(id=uid, name=uid.upper(), quota=5, group=1)
    base.update(kw)
    return Unit(**base)


def cats(risks):
    return {r.category for r in risks}


def msg(risks):
    return " || ".join(r.message for r in risks)


# ---------------------------------------------------------------- R1
def test_r1_total_quota_below_student_count():
    students = [S(i) for i in range(6)]
    units = [U("a", quota=2), U("b", quota=2)]  # 4 < 6
    r = forward_risks(students, units, MONTHS, [])
    kota = [x for x in r if x.category == CAT_QUOTA and x.level == ERROR]
    assert kota, msg(r)
    assert "4" in msg(kota) and "6 aktif öğrenci" in msg(kota)


def test_r1_silent_when_quota_is_enough():
    students = [S(i) for i in range(4)]
    units = [U("a", quota=5), U("b", quota=5), U("c", quota=5), U("d", quota=5)]
    r = forward_risks(students, units, MONTHS, [])
    assert not [x for x in r if x.category == CAT_QUOTA and x.level == ERROR]


def test_r1_ignores_inactive_students():
    """Ayrılan öğrenci yeni aylara atanmaz; kontenjan payına sayılmamalı."""
    active_only = [S(i) for i in range(3)]
    units = [U(f"u{i}", quota=2) for i in range(4)]  # 8 kontenjan, pay var
    assert not [
        x for x in forward_risks(active_only, units, MONTHS, [])
        if x.category == CAT_QUOTA and x.level == ERROR
    ]
    # 6 pasif öğrenci eklemek kontenjan hatası doğurmamalı
    with_inactive = active_only + [S(9 + i, active=False) for i in range(6)]
    assert not [
        x for x in forward_risks(with_inactive, units, MONTHS, [])
        if x.category == CAT_QUOTA and x.level == ERROR
    ]


# ---------------------------------------------------------------- R2
def test_r2_runway_shorter_than_remaining_months():
    """4 ay var ama öğrencinin gidebileceği yalnız 2 farklı birim."""
    students = [S(0)]
    units = [U("a", quota=3), U("b", quota=3)]
    r = forward_risks(students, units, MONTHS, [])
    runway = [x for x in r if x.category == CAT_RUNWAY]
    assert runway and runway[0].level == ERROR


def test_r2_no_unit_left_at_all():
    """Tek birim var ve öğrenci oraya zaten gitmiş → hiç seçenek yok."""
    students = [S(0)]
    units = [U("a", quota=3)]
    assignments = [Assignment(student_id="s0", month="EYLÜL", unit_id="a")]
    r = forward_risks(students, units, MONTHS, assignments)
    runway = [x for x in r if x.category == CAT_RUNWAY]
    assert runway and "hiçbir birim kalmadı" in msg(runway)


def test_r2_counts_units_by_name_not_id():
    """Madde 1 ad bazındadır: 'FTR k' ve 'FTR e' tek seçenek sayılır."""
    students = [S(0, gender="K")]
    units = [
        U("f1", name="FTR", quota=1, gender_restriction="K"),
        U("f2", name="FTR", quota=1, gender_restriction="E"),
        U("b", quota=3),
    ]
    # ad bazında 2 seçenek (FTR + B), 4 ay → yetmez
    r = forward_risks(students, units, MONTHS, units and [])
    assert [x for x in r if x.category == CAT_RUNWAY]


def test_r2_silent_when_enough_units():
    students = [S(0)]
    units = [U(f"u{i}", quota=3) for i in range(5)]
    r = forward_risks(students, units, MONTHS, [])
    assert not [x for x in r if x.category == CAT_RUNWAY]


# ---------------------------------------------------------------- R3
def test_r3_fixed_assignment_repeats_visited_unit():
    """MART'a sabit atama, ama öğrenci o birime EYLÜL'de gitmiş."""
    students = [S(0)]
    units = [U("a", quota=3), U("b", quota=3), U("c", quota=3), U("d", quota=3)]
    assignments = [Assignment(student_id="s0", month="EYLÜL", unit_id="a")]
    rules = [
        CustomRule(type=RULE_SABIT_ATAMA, student_ids=["s0"],
                   unit_id="a", month="ARALIK")
    ]
    r = forward_risks(students, units, MONTHS, assignments, rules)
    ozel = [x for x in r if x.category == CAT_CUSTOM]
    assert ozel and "ikinci kez" in msg(ozel)


def test_r3_fixed_assignment_to_inactive_unit():
    students = [S(0)]
    units = [U("a", quota=3, active=False)] + [U(f"u{i}", quota=3) for i in range(4)]
    rules = [
        CustomRule(type=RULE_SABIT_ATAMA, student_ids=["s0"],
                   unit_id="a", month="EKİM")
    ]
    r = forward_risks(students, units, MONTHS, [], rules)
    assert "pasif" in msg([x for x in r if x.category == CAT_CUSTOM])


def test_r3_fixed_assignment_gender_conflict():
    students = [S(0, gender="K")]
    units = [U("a", quota=3, gender_restriction="E")] + [
        U(f"u{i}", quota=3) for i in range(4)
    ]
    rules = [
        CustomRule(type=RULE_SABIT_ATAMA, student_ids=["s0"],
                   unit_id="a", month="EKİM")
    ]
    r = forward_risks(students, units, MONTHS, [], rules)
    assert "atanamaz" in msg([x for x in r if x.category == CAT_CUSTOM])


def test_r3_fixed_assignment_over_quota():
    students = [S(i) for i in range(3)]
    units = [U("a", quota=1)] + [U(f"u{i}", quota=5) for i in range(4)]
    rules = [
        CustomRule(type=RULE_SABIT_ATAMA, student_ids=["s0", "s1"],
                   unit_id="a", month="EKİM")
    ]
    r = forward_risks(students, units, MONTHS, [], rules)
    assert "kontenjanı 1" in msg([x for x in r if x.category == CAT_CUSTOM])


def test_r3_silent_for_already_generated_month():
    """O ay zaten üretilmişse rules.py denetler; risk paneli tekrar etmez."""
    students = [S(0)]
    units = [U(f"u{i}", quota=3) for i in range(5)]
    assignments = [Assignment(student_id="s0", month="EYLÜL", unit_id="u0")]
    rules = [
        CustomRule(type=RULE_SABIT_ATAMA, student_ids=["s0"],
                   unit_id="u1", month="EYLÜL")
    ]
    r = forward_risks(students, units, MONTHS, assignments, rules)
    assert not [x for x in r if x.category == CAT_CUSTOM]


def test_fixed_assignment_conflicts_is_reusable_standalone():
    """Kurallar sekmesi bu fonksiyonu kural EKLENİRKEN çağırır."""
    s = S(0)
    u = U("a", quota=3)
    rule = CustomRule(type=RULE_SABIT_ATAMA, student_ids=["s0"],
                      unit_id="a", month="ARALIK")
    assignments = [Assignment(student_id="s0", month="EYLÜL", unit_id="a")]
    sorunlar = fixed_assignment_conflicts(
        rule, {"s0": s}, {"a": u}, assignments
    )
    assert sorunlar and "ikinci kez" in sorunlar[0]
    # temiz durumda boş döner
    assert fixed_assignment_conflicts(rule, {"s0": s}, {"a": u}, []) == []


# ---------------------------------------------------------------- R4
def test_r4_together_rule_has_no_unit_big_enough():
    students = [S(0), S(1), S(2)]
    units = [U(f"u{i}", quota=2) for i in range(5)]  # hiçbiri 3 kişilik değil
    rules = [
        CustomRule(type=RULE_BIRLIKTE_TUT, student_ids=["s0", "s1", "s2"])
    ]
    r = forward_risks(students, units, MONTHS, [], rules)
    ozel = [x for x in r if x.category == CAT_CUSTOM]
    assert ozel and "aynı anda" in msg(ozel)


def test_r4_silent_when_a_unit_fits():
    students = [S(0), S(1), S(2)]
    units = [U(f"u{i}", quota=4) for i in range(5)]
    rules = [
        CustomRule(type=RULE_BIRLIKTE_TUT, student_ids=["s0", "s1", "s2"])
    ]
    r = forward_risks(students, units, MONTHS, [], rules)
    assert not [x for x in r if x.category == CAT_CUSTOM]


def test_r4_respects_gender_restrictions():
    """Kontenjan yetiyor ama birim yalnız kızlara açık, grupta erkek var."""
    students = [S(0, gender="K"), S(1, gender="E")]
    units = [U("a", quota=5, gender_restriction="K")] + [
        U(f"u{i}", quota=1) for i in range(4)
    ]
    rules = [CustomRule(type=RULE_BIRLIKTE_TUT, student_ids=["s0", "s1"])]
    r = forward_risks(students, units, MONTHS, [], rules)
    assert [x for x in r if x.category == CAT_CUSTOM]


# ---------------------------------------------------------------- R5
def test_r5_contradicting_rules():
    students = [S(0), S(1)]
    units = [U(f"u{i}", quota=5) for i in range(5)]
    rules = [
        CustomRule(type=RULE_AYRI_TUT, student_ids=["s0", "s1"]),
        CustomRule(type=RULE_BIRLIKTE_TUT, student_ids=["s0", "s1"]),
    ]
    r = forward_risks(students, units, MONTHS, [], rules)
    ozel = [x for x in r if x.category == CAT_CUSTOM]
    assert ozel and "aynı anda sağlanamaz" in msg(ozel)


def test_r5_silent_when_windows_do_not_overlap():
    """Pencereler ayrıksa çelişki yok — biri erken, biri geç aylarda."""
    students = [S(0), S(1)]
    units = [U(f"u{i}", quota=5) for i in range(5)]
    rules = [
        CustomRule(type=RULE_AYRI_TUT, student_ids=["s0", "s1"],
                   start_month="EYLÜL", end_month="EKİM"),
        CustomRule(type=RULE_BIRLIKTE_TUT, student_ids=["s0", "s1"],
                   start_month="KASIM", end_month="ARALIK"),
    ]
    r = forward_risks(students, units, MONTHS, [], rules)
    assert not [
        x for x in r if x.category == CAT_CUSTOM and "sağlanamaz" in x.message
    ]


def test_r5_inactive_rules_ignored():
    students = [S(0), S(1)]
    units = [U(f"u{i}", quota=5) for i in range(5)]
    rules = [
        CustomRule(type=RULE_AYRI_TUT, student_ids=["s0", "s1"]),
        CustomRule(type=RULE_BIRLIKTE_TUT, student_ids=["s0", "s1"],
                   active=False),
    ]
    r = forward_risks(students, units, MONTHS, [], rules)
    assert not [x for x in r if "sağlanamaz" in x.message]


# ---------------------------------------------------------------- genel
def test_clean_setup_produces_no_risks():
    students = [S(i) for i in range(4)]
    units = [U(f"u{i}", quota=4) for i in range(8)]
    assert forward_risks(students, units, MONTHS, []) == []


def test_errors_sort_before_warnings():
    students = [S(i) for i in range(6)]
    units = [U("a", quota=2), U("b", quota=2)]
    r = forward_risks(students, units, MONTHS, [])
    levels = [x.level for x in r]
    assert levels == sorted(levels, key=lambda l: l != ERROR)


def test_risk_counts_splits_errors_and_warnings():
    students = [S(i) for i in range(6)]
    units = [U("a", quota=2), U("b", quota=2)]
    hata, uyari = risk_counts(forward_risks(students, units, MONTHS, []))
    assert hata >= 1 and hata + uyari == len(
        forward_risks(students, units, MONTHS, [])
    )


def test_no_risks_when_season_is_complete():
    """Tüm aylar üretilmişse ileriye dönük risk kalmaz."""
    students = [S(0)]
    units = [U(f"u{i}", quota=3) for i in range(4)]
    assignments = [
        Assignment(student_id="s0", month=m, unit_id=f"u{i}")
        for i, m in enumerate(MONTHS)
    ]
    r = forward_risks(students, units, MONTHS, assignments)
    assert not [x for x in r if x.category in (CAT_RUNWAY, CAT_QUOTA)]


# ---------------------------------------------------------------- yardımcılar
def test_units_fitting_all_is_shared_by_ui_and_risk():
    """Kurallar sekmesi ile risk denetimi aynı fonksiyonu kullanmalı."""
    from rotasyon.risk import can_attend, units_fitting_all

    grup = [S(0, gender="K"), S(1, gender="E")]
    units = [
        U("kucuk", quota=1),                       # kontenjan yetmez
        U("kiz", quota=5, gender_restriction="K"),  # erkek giremez
        U("ok", quota=2),                           # uyar
    ]
    uygun = units_fitting_all(grup, units)
    assert [u.id for u in uygun] == ["ok"]
    assert can_attend(grup[0], units[1]) and not can_attend(grup[1], units[1])


def test_can_attend_respects_group_and_bans():
    from rotasyon.risk import can_attend

    s = S(0, group=1, banned_unit_ids=["yasak"])
    assert can_attend(s, U("ortak", group=0))
    assert not can_attend(s, U("digergrup", group=2))
    assert not can_attend(s, U("yasak"))


def test_deep_feasibility_reports_per_group_without_saving():
    """Deneme çözümü sonuç döndürür ve hiçbir şeyi değiştirmez."""
    from rotasyon.risk import deep_feasibility

    students = [S(i) for i in range(4)]
    units = [U(f"u{i}", quota=4) for i in range(6)]
    assignments = []
    res = deep_feasibility(students, units, MONTHS, assignments)
    assert len(res) == 1 and res[0].group == 1
    assert res[0].months == MONTHS
    assert res[0].ok, res[0].reasons
    assert assignments == []  # hiçbir şey yazılmadı


def test_deep_feasibility_skips_completed_group():
    from rotasyon.risk import deep_feasibility

    students = [S(0)]
    units = [U(f"u{i}", quota=3) for i in range(4)]
    assignments = [
        Assignment(student_id="s0", month=m, unit_id=f"u{i}")
        for i, m in enumerate(MONTHS)
    ]
    res = deep_feasibility(students, units, MONTHS, assignments)
    assert res[0].status == "ATLANDI"


def test_deep_feasibility_detects_infeasible_season():
    """Tek birim, 4 ay: tekrar yasağı yüzünden çözülemez."""
    from rotasyon.risk import deep_feasibility

    students = [S(0)]
    units = [U("tek", quota=1)]
    res = deep_feasibility(students, units, MONTHS, [])
    assert not res[0].ok
