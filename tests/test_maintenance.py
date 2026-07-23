"""Veri bakımı (rotasyon/maintenance.py): kademeli silme + sahipsiz temizlik."""
import pytest

from rotasyon.maintenance import (
    apply_class_group,
    class_group_state,
    orphan_assignments,
    remove_student,
    strip_orphan_assignments,
    students_changed_by,
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


# ---------------- sınıf → grup yeniden eşleştirme ----------------

def _class_world():
    return [
        Student(id="a1", full_name="A Bir", gender="K", group=1, class_name="A"),
        Student(id="a2", full_name="A İki", gender="E", group=1, class_name="A"),
        Student(id="b1", full_name="B Bir", gender="K", group=2, class_name="B"),
        # karışık şube: C'nin biri 1. biri 2. grupta, çoğunluk 1
        Student(id="c1", full_name="C Bir", gender="K", group=1, class_name="C"),
        Student(id="c2", full_name="C İki", gender="E", group=1, class_name="C"),
        Student(id="c3", full_name="C Üç", gender="K", group=2, class_name="C"),
    ]


def test_class_group_state_reports_groups_and_counts():
    states = {s.name: s for s in class_group_state(_class_world())}
    assert states["A"].student_count == 2
    assert states["A"].groups == [1] and not states["A"].is_mixed
    assert states["B"].groups == [2]


def test_class_group_state_detects_mixed_and_suggests_majority():
    states = {s.name: s for s in class_group_state(_class_world())}
    assert states["C"].is_mixed and states["C"].groups == [1, 2]
    assert states["C"].suggested == 1  # 2 kişi 1. grupta, 1 kişi 2. grupta


def test_class_group_state_includes_classes_without_students():
    states = {s.name: s for s in class_group_state(_class_world(), ["D"])}
    assert states["D"].student_count == 0
    assert states["D"].suggested == 1  # öğrencisi yokken makul varsayılan


def test_students_changed_by_only_lists_real_changes():
    students = _class_world()
    changed = students_changed_by(students, {"A": 2, "B": 2, "C": 1})
    # A'nın ikisi değişir, B zaten 2, C'nin yalnız 2. gruptaki üyesi değişir
    assert sorted(s.id for s in changed) == ["a1", "a2", "c3"]


def test_apply_class_group_moves_students_and_counts():
    students = _class_world()
    updated, n = apply_class_group(students, {"A": 2, "C": 1})
    assert n == 3
    by_id = {s.id: s for s in updated}
    assert by_id["a1"].group == 2 and by_id["a2"].group == 2
    assert by_id["c3"].group == 1  # karışık şube tek gruba toplandı
    assert by_id["b1"].group == 2  # eşleştirmede yok, dokunulmadı


def test_apply_class_group_does_not_mutate_input():
    students = _class_world()
    apply_class_group(students, {"A": 2})
    assert students[0].group == 1  # orijinal nesne korundu


def test_apply_class_group_is_idempotent():
    students = _class_world()
    once, n1 = apply_class_group(students, {"A": 2})
    twice, n2 = apply_class_group(once, {"A": 2})
    assert n1 == 2 and n2 == 0
    assert [s.group for s in once] == [s.group for s in twice]
