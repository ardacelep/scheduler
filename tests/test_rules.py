"""Kural ihlal denetleyicisi (rules.check_all) testleri."""
from rotasyon.models import DEFAULT_MONTHS, PROGRAM_EBELIK
from rotasyon.queries import student_history
from rotasyon.rules import ERROR, WARNING, check_all

from conftest import make_assignment


def by_name(units, name, gender=""):
    return next(
        u for u in units if u.name == name and u.gender_restriction == gender
    )


def rules_hit(violations):
    return {v.rule_no for v in violations}


def test_clean_table_has_no_violations(small_world):
    students, units, _ = small_world
    dis = by_name(units, "DİŞ")
    cerr = by_name(units, "1.KAT CERR.")
    assignments = [
        make_assignment(students[0], dis, "EYLÜL"),
        make_assignment(students[1], cerr, "EYLÜL"),
    ]
    # FTR must_fill ihlali üretmesin diye FTR'yi de dolduralım
    ftr_k = by_name(units, "FTR.ÜNİT", "K")
    ftr_e = by_name(units, "FTR.ÜNİT", "E")
    assignments += [
        make_assignment(students[2], ftr_k, "EYLÜL"),
        make_assignment(students[4], ftr_e, "EYLÜL"),
    ]
    v = check_all(students, units, assignments, DEFAULT_MONTHS)
    assert [x for x in v if x.severity == ERROR] == []


def test_rule1_detected(small_world):
    students, units, _ = small_world
    dis = by_name(units, "DİŞ")
    s = students[0]
    assignments = [
        make_assignment(s, dis, "EYLÜL"),
        make_assignment(s, dis, "EKİM"),
    ]
    v = check_all(students, units, assignments, DEFAULT_MONTHS)
    assert 1 in rules_hit(v)


def test_rule2_detected(small_world):
    students, units, _ = small_world
    ftr_k = by_name(units, "FTR.ÜNİT", "K")
    erkek = students[4]
    v = check_all(
        students, units, [make_assignment(erkek, ftr_k, "EYLÜL")], DEFAULT_MONTHS
    )
    assert 2 in rules_hit(v)


def test_rule3_detected(small_world):
    students, units, _ = small_world
    ftr_e = by_name(units, "FTR.ÜNİT", "E")
    kiz = students[0]
    v = check_all(
        students, units, [make_assignment(kiz, ftr_e, "EYLÜL")], DEFAULT_MONTHS
    )
    assert 3 in rules_hit(v)


def test_rule5_detected_cross_group(small_world):
    students, units, _ = small_world
    from rotasyon.models import Unit

    other = Unit(name="BAŞKA GRUP BİRİMİ", group=2, quota=1)
    v = check_all(
        students,
        units + [other],
        [make_assignment(students[0], other, "EYLÜL")],
        DEFAULT_MONTHS,
    )
    assert 5 in rules_hit(v)


def test_rule6_and_7_detected_at_period_end(small_world):
    students, units, _ = small_world
    dis = by_name(units, "DİŞ")
    ebe = students[-1]
    assert ebe.program == PROGRAM_EBELIK
    # dönemin son ayı dahil atanmış ama hiç core/doğum görmemiş
    assignments = [
        make_assignment(ebe, dis, "EYLÜL"),
        make_assignment(ebe, dis, DEFAULT_MONTHS[-1]),
    ]
    v = check_all(students, units, assignments, DEFAULT_MONTHS)
    assert 6 in rules_hit(v)
    assert 7 in rules_hit(v)


def test_rule6_not_reported_mid_period(small_world):
    students, units, _ = small_world
    dis = by_name(units, "DİŞ")
    v = check_all(
        students, units, [make_assignment(students[0], dis, "EYLÜL")], DEFAULT_MONTHS
    )
    assert 6 not in rules_hit(v)


def test_rule8_detected(small_world):
    students, units, _ = small_world
    dis = by_name(units, "DİŞ")
    s = students[0]
    s.banned_unit_ids = [dis.id]
    v = check_all(students, units, [make_assignment(s, dis, "EYLÜL")], DEFAULT_MONTHS)
    assert 8 in rules_hit(v)


def test_rule9_detected(small_world):
    students, units, _ = small_world
    dis = by_name(units, "DİŞ")
    s = students[0]
    s.dis_exempt = True
    v = check_all(students, units, [make_assignment(s, dis, "EYLÜL")], DEFAULT_MONTHS)
    assert 9 in rules_hit(v)


def test_rule12_quota_overflow_detected(small_world):
    students, units, _ = small_world
    dis = by_name(units, "DİŞ")  # quota 1
    v = check_all(
        students,
        units,
        [
            make_assignment(students[0], dis, "EYLÜL"),
            make_assignment(students[1], dis, "EYLÜL"),
        ],
        DEFAULT_MONTHS,
    )
    assert 12 in rules_hit(v)


def test_rule17_underfilled_ftr_detected(small_world):
    students, units, _ = small_world
    ftr_k = by_name(units, "FTR.ÜNİT", "K")
    # FTR-K dolu ama FTR-E boş → madde 17 ihlali
    v = check_all(
        students, units, [make_assignment(students[0], ftr_k, "EYLÜL")], DEFAULT_MONTHS
    )
    assert 17 in rules_hit(v)


def test_rule18_warning_when_ebelik_idle(small_world):
    students, units, _ = small_world
    dogum = by_name(units, "DOĞ.SAL-Y.DOĞ")
    dis = by_name(units, "DİŞ")
    ebe = students[-1]
    kiz = students[0]
    v = check_all(
        students,
        units,
        [
            make_assignment(kiz, dogum, "EYLÜL"),  # ebelik değilken öncelikli birimde
            make_assignment(ebe, dis, "EYLÜL"),
        ],
        DEFAULT_MONTHS,
    )
    hits = [x for x in v if x.rule_no == 18]
    assert hits and hits[0].severity == WARNING


def test_rule19_warning_for_repeated_pair(small_world):
    students, units, _ = small_world
    cerr = by_name(units, "1.KAT CERR.")  # quota 2
    dis = by_name(units, "DİŞ")
    s1, s2 = students[0], students[1]
    assignments = [
        make_assignment(s1, cerr, "EYLÜL"),
        make_assignment(s2, cerr, "EYLÜL"),
        make_assignment(s1, dis, "EKİM"),
        make_assignment(s2, dis, "EKİM"),
    ]
    v = check_all(students, units, assignments, DEFAULT_MONTHS)
    hits = [x for x in v if x.rule_no == 19]
    assert hits and hits[0].severity == WARNING


def test_rule16_student_history_query(small_world):
    """Madde 16: geçmiş görünümü ay sırasına göre döner."""
    students, units, _ = small_world
    dis = by_name(units, "DİŞ")
    cerr = by_name(units, "1.KAT CERR.")
    s = students[0]
    assignments = [
        make_assignment(s, dis, "EKİM"),
        make_assignment(s, cerr, "EYLÜL", day_note="Çrş günleri üro.pol"),
    ]
    hist = student_history(
        s.id, assignments, DEFAULT_MONTHS, {u.id: u for u in units}
    )
    assert [(m, u) for m, u, _ in hist] == [
        ("EYLÜL", "1.KAT CERR."),
        ("EKİM", "DİŞ"),
    ]
    assert hist[0][2] == "Çrş günleri üro.pol"  # madde 11 notu görünür
