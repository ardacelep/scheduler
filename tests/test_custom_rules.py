"""Kullanıcı tanımlı (özel) kurallar: solver + denetleyici + store."""
from rotasyon.models import (
    CustomRule,
    Student,
    Unit,
    DEFAULT_MONTHS,
    FEMALE,
    RULE_AYRI_TUT,
    RULE_BIRLIKTE_TUT,
    RULE_SABIT_ATAMA,
)
from rotasyon.rules import CUSTOM_RULE_NO, ERROR, check_all
from rotasyon.solver import solve_month
from rotasyon.store import Store

from conftest import make_assignment


def _world():
    students = [
        Student(full_name=f"S{i}", gender=FEMALE, group=1) for i in range(4)
    ]
    units = [
        Unit(name="U1", group=1, quota=2),
        Unit(name="U2", group=1, quota=2),
    ]
    return students, units


def test_solver_ayri_tut(settings):
    students, units = _world()
    a, b = students[0], students[1]
    rule = CustomRule(type=RULE_AYRI_TUT, student_ids=[a.id, b.id])
    r = solve_month(
        students, units, "EYLÜL", history=[], settings=settings,
        custom_rules=[rule],
    )
    assert r.ok
    assert r.assignments[a.id] != r.assignments[b.id]


def test_solver_output_passes_checker_with_same_rules(settings):
    """Tutarlılık round-trip'i: solver'ın özel kural + sert kurallara UYARAK
    ürettiği çözüm, AYNI kural kümesiyle çalıştırılan denetleyicide sıfır
    ERROR vermeli (solver ↔ check_all akış boyunca uyumlu)."""
    settings["season_requirements"] = []
    students = [
        Student(full_name=f"S{i}", gender=FEMALE, group=1) for i in range(4)
    ]
    units = [Unit(name=f"U{i}", group=1, quota=2) for i in range(3)]  # 6 koltuk
    a, b = students[0], students[1]
    c, d = students[2], students[3]
    rules = [
        CustomRule(type=RULE_AYRI_TUT, student_ids=[a.id, b.id]),
        CustomRule(type=RULE_BIRLIKTE_TUT, student_ids=[c.id, d.id]),
    ]
    r = solve_month(
        students, units, "EYLÜL", history=[], settings=settings,
        custom_rules=rules,
    )
    assert r.assignments[a.id] != r.assignments[b.id]
    assert r.assignments[c.id] == r.assignments[d.id]
    assert r.ok, r.infeasible_reasons
    assignments = [
        make_assignment(
            next(s for s in students if s.id == sid),
            next(u for u in units if u.id == uid),
            "EYLÜL",
        )
        for sid, uid in r.assignments.items()
    ]
    v = check_all(
        students, units, assignments, DEFAULT_MONTHS, rules, settings=settings
    )
    errors = [x for x in v if x.severity == ERROR]
    assert errors == [], [e.message for e in errors]


def test_solver_birlikte_tut(settings):
    students, units = _world()
    a, b = students[0], students[1]
    rule = CustomRule(type=RULE_BIRLIKTE_TUT, student_ids=[a.id, b.id])
    r = solve_month(
        students, units, "EYLÜL", history=[], settings=settings,
        custom_rules=[rule],
    )
    assert r.ok
    assert r.assignments[a.id] == r.assignments[b.id]


def test_solver_sabit_atama(settings):
    students, units = _world()
    a = students[0]
    rule = CustomRule(
        type=RULE_SABIT_ATAMA, student_ids=[a.id],
        unit_id=units[1].id, month="EYLÜL",
    )
    r = solve_month(
        students, units, "EYLÜL", history=[], settings=settings,
        custom_rules=[rule],
    )
    assert r.ok
    assert r.assignments[a.id] == units[1].id


def test_solver_sabit_atama_other_month_ignored(settings):
    students, units = _world()
    a = students[0]
    rule = CustomRule(
        type=RULE_SABIT_ATAMA, student_ids=[a.id],
        unit_id=units[1].id, month="EKİM",
    )
    r = solve_month(
        students, units, "EYLÜL", history=[], settings=settings,
        custom_rules=[rule],
    )
    assert r.ok  # kural başka aya ait, kısıt uygulanmaz


def test_solver_inactive_rule_ignored(settings):
    students, units = _world()
    a, b = students[0], students[1]
    rule = CustomRule(
        type=RULE_BIRLIKTE_TUT, student_ids=[a.id, b.id], active=False
    )
    r = solve_month(
        students, units, "EYLÜL", history=[], settings=settings,
        custom_rules=[rule],
    )
    assert r.ok  # pasif kural kısıt üretmez


def test_solver_conflicting_custom_rules_reported(settings):
    """Çelişen özel kurallar Türkçe nedenle raporlanır."""
    students, units = _world()
    a, b = students[0], students[1]
    rules = [
        CustomRule(type=RULE_AYRI_TUT, student_ids=[a.id, b.id]),
        CustomRule(type=RULE_BIRLIKTE_TUT, student_ids=[a.id, b.id]),
    ]
    r = solve_month(
        students, units, "EYLÜL", history=[], settings=settings,
        custom_rules=rules,
    )
    assert not r.ok
    assert any("Özel kural" in reason for reason in r.infeasible_reasons)


def test_checker_detects_ayri_tut_violation():
    students, units = _world()
    a, b = students[0], students[1]
    rule = CustomRule(type=RULE_AYRI_TUT, student_ids=[a.id, b.id])
    assignments = [
        make_assignment(a, units[0], "EYLÜL"),
        make_assignment(b, units[0], "EYLÜL"),
    ]
    v = check_all(students, units, assignments, DEFAULT_MONTHS, [rule])
    hits = [x for x in v if x.rule_no == CUSTOM_RULE_NO]
    assert hits and hits[0].severity == ERROR
    assert "ayrı tut" in hits[0].message


def test_checker_detects_birlikte_tut_violation():
    students, units = _world()
    a, b = students[0], students[1]
    rule = CustomRule(type=RULE_BIRLIKTE_TUT, student_ids=[a.id, b.id])
    assignments = [
        make_assignment(a, units[0], "EYLÜL"),
        make_assignment(b, units[1], "EYLÜL"),
    ]
    v = check_all(students, units, assignments, DEFAULT_MONTHS, [rule])
    assert any(
        x.rule_no == CUSTOM_RULE_NO and "birlikte tut" in x.message for x in v
    )


def test_checker_detects_sabit_atama_violation():
    students, units = _world()
    a = students[0]
    rule = CustomRule(
        type=RULE_SABIT_ATAMA, student_ids=[a.id],
        unit_id=units[1].id, month="EYLÜL",
    )
    assignments = [make_assignment(a, units[0], "EYLÜL")]
    v = check_all(students, units, assignments, DEFAULT_MONTHS, [rule])
    assert any(
        x.rule_no == CUSTOM_RULE_NO and "sabit atama" in x.message for x in v
    )


def test_checker_clean_when_rules_satisfied():
    students, units = _world()
    a, b = students[0], students[1]
    rules = [
        CustomRule(type=RULE_AYRI_TUT, student_ids=[a.id, b.id]),
        CustomRule(
            type=RULE_SABIT_ATAMA, student_ids=[a.id],
            unit_id=units[0].id, month="EYLÜL",
        ),
    ]
    assignments = [
        make_assignment(a, units[0], "EYLÜL"),
        make_assignment(b, units[1], "EYLÜL"),
    ]
    v = check_all(students, units, assignments, DEFAULT_MONTHS, rules)
    assert [x for x in v if x.rule_no == CUSTOM_RULE_NO] == []


def test_store_roundtrip(tmp_path):
    store = Store(tmp_path)
    rules = [
        CustomRule(type=RULE_AYRI_TUT, student_ids=["a", "b"], note="kavgalılar"),
        CustomRule(
            type=RULE_SABIT_ATAMA, student_ids=["c"],
            unit_id="u1", month="MART", active=False,
        ),
    ]
    store.save_custom_rules(rules)
    loaded = store.load_custom_rules()
    assert len(loaded) == 2
    assert loaded[0].note == "kavgalılar"
    assert loaded[1].active is False
