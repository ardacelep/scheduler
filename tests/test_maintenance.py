"""Veri bakımı (rotasyon/maintenance.py): kademeli silme + sahipsiz temizlik."""
import pytest

from rotasyon.maintenance import (
    orphan_assignments,
    remove_student,
    strip_orphan_assignments,
)
from rotasyon.models import (
    Assignment,
    CustomRule,
    RULE_AYRI_TUT,
    RULE_BIRLIKTE_TUT,
    RULE_SABIT_ATAMA,
    Student,
    Unit,
)


@pytest.fixture
def world():
    students = [
        Student(id=f"s{i}", full_name=f"Öğrenci {i}", gender="K", group=1)
        for i in range(4)
    ]
    units = [Unit(id="u1", name="DİŞ", quota=4, group=1)]
    assignments = [
        Assignment(student_id="s0", month="EYLÜL", unit_id="u1"),
        Assignment(student_id="s0", month="EKİM", unit_id="u1"),
        Assignment(student_id="s1", month="EYLÜL", unit_id="u1"),
    ]
    rules = [
        CustomRule(type=RULE_AYRI_TUT, student_ids=["s0", "s1"]),
        CustomRule(type=RULE_BIRLIKTE_TUT, student_ids=["s0", "s1", "s2"]),
        CustomRule(type=RULE_SABIT_ATAMA, student_ids=["s0"], unit_id="u1",
                   month="KASIM"),
        CustomRule(type=RULE_SABIT_ATAMA, student_ids=["s1"], unit_id="u1",
                   month="KASIM"),
    ]
    return students, units, assignments, rules


def test_remove_student_cascades(world):
    students, _units, assignments, rules = world
    r = remove_student(students, assignments, rules, "s0")
    assert [s.id for s in r.students] == ["s1", "s2", "s3"]
    # s0'ın 2 ataması gitti, s1'inki kaldı — sahipsiz atama yok
    assert r.removed_assignments == 2
    assert [a.student_id for a in r.assignments] == ["s1"]


def test_remove_student_prunes_rules(world):
    students, _units, assignments, rules = world
    r = remove_student(students, assignments, rules, "s0")
    kept_types = [(rule.type, rule.student_ids) for rule in r.rules]
    # ayrı-tut tek kişiye düştü → kuralın kendisi kalktı
    assert (RULE_AYRI_TUT, ["s1"]) not in kept_types
    # birlikte-tut 2 kişiyle hâlâ anlamlı → üyelik düşülerek korundu
    assert (RULE_BIRLIKTE_TUT, ["s1", "s2"]) in kept_types
    # s0'ın sabit ataması kalktı, s1'inki duruyor
    assert (RULE_SABIT_ATAMA, ["s1"]) in kept_types
    assert r.removed_rules == 2


def test_remove_student_does_not_mutate_inputs(world):
    students, _units, assignments, rules = world
    remove_student(students, assignments, rules, "s0")
    assert len(students) == 4 and len(assignments) == 3 and len(rules) == 4
    assert rules[1].student_ids == ["s0", "s1", "s2"]  # orijinal değişmedi


def test_orphan_detection_and_strip(world):
    students, units, assignments, _rules = world
    assignments = assignments + [
        Assignment(student_id="HAYALET", month="EYLÜL", unit_id="u1"),
        Assignment(student_id="s1", month="EKİM", unit_id="HAYALET-BIRIM"),
    ]
    orphans = orphan_assignments(students, units, assignments)
    assert len(orphans) == 2
    kept, removed = strip_orphan_assignments(students, units, assignments)
    assert removed == 2
    assert all(
        a.student_id.startswith("s") and a.unit_id == "u1" for a in kept
    )


def test_no_orphans_is_noop(world):
    students, units, assignments, _rules = world
    kept, removed = strip_orphan_assignments(students, units, assignments)
    assert removed == 0 and len(kept) == 3
