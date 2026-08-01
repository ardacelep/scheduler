"""Kurulum durumu (rotasyon.setup_status) — sihirbazın "nerede kaldım?" mantığı.

Adım durumları tamamen VERİDEN türetilir; kullanıcı hiçbir şey işaretlemez.
"""
from rotasyon.models import (
    Assignment,
    ClassGroup,
    Requirement,
    SCOPE_ALL,
    SEVERITY_PREFERRED,
    Student,
    Unit,
)
from rotasyon.setup_status import (
    STATE_BLOCKED,
    STATE_DONE,
    STATE_TODO,
    STATE_WARN,
    first_actionable,
    progress,
    setup_steps,
)

MONTHS = ["EYLÜL", "EKİM"]
SETTINGS = {"months": MONTHS}


def S(i=0, group=1, gender="K", active=True):
    return Student(full_name=f"Ö{i}", gender=gender, group=group,
                   class_name="A", active=active)


def U(name="X", group=1, quota=5, **flags):
    return Unit(name=name, group=group, quota=quota, **flags)


def R(name="Gereksinim", **kw):
    return Requirement(name=name, scope=SCOPE_ALL, unit_keys=["X"], **kw)


def _steps(students=(), units=(), classes=(), reqs=(), asg=()):
    return setup_steps(
        list(students), list(units), list(classes), list(reqs), list(asg),
        SETTINGS,
    )


def _by_key(steps):
    return {s.key: s for s in steps}


# ---- adım 1: öğrenciler ----

def test_students_step_todo_when_empty():
    step = _by_key(_steps())["ogrenciler"]
    assert step.state == STATE_TODO
    assert step.page == "excel"


def test_students_step_warns_on_missing_gender():
    step = _by_key(_steps(students=[S(0), S(1, gender="")]))["ogrenciler"]
    assert step.state == STATE_WARN
    assert "cinsiyeti" in step.detail


def test_students_step_done_when_complete():
    step = _by_key(_steps(students=[S(0), S(1)]))["ogrenciler"]
    assert step.state == STATE_DONE
    assert "2 öğrenci" in step.detail


def test_inactive_student_missing_gender_does_not_warn():
    # ayrılan öğrencinin cinsiyeti eksikse yeni aya atanmayacağı için sorun değil
    step = _by_key(
        _steps(students=[S(0), S(1, gender="", active=False)])
    )["ogrenciler"]
    assert step.state == STATE_DONE


# ---- adım 2: gruplar ----

def test_groups_step_blocked_without_students():
    assert _by_key(_steps())["gruplar"].state == STATE_BLOCKED


def test_groups_step_warns_when_everyone_in_one_group():
    step = _by_key(_steps(students=[S(0), S(1)]))["gruplar"]
    assert step.state == STATE_WARN
    assert "grup 1" in step.detail


def test_groups_step_done_with_two_groups():
    step = _by_key(_steps(students=[S(0, group=1), S(1, group=2)]))["gruplar"]
    assert step.state == STATE_DONE
    assert "Grup 1: 1" in step.detail and "Grup 2: 1" in step.detail


# ---- adım 3: kapasite ----

def test_capacity_step_todo_without_units():
    step = _by_key(_steps(students=[S(0)]))["kapasite"]
    assert step.state == STATE_TODO


def test_capacity_step_blocked_without_students():
    step = _by_key(_steps(units=[U()]))["kapasite"]
    assert step.state == STATE_BLOCKED


def test_capacity_step_warns_on_plan_problem():
    # tam dolmalı kontenjanı öğrenci sayısını aşıyor
    units = [U("m", quota=9, must_fill=True)]
    step = _by_key(_steps(students=[S(0), S(1)], units=units))["kapasite"]
    assert step.state == STATE_WARN
    assert "Tam dolmalı" in step.detail


def test_capacity_step_done_when_healthy():
    students = [S(i) for i in range(4)]
    units = [U("a", quota=4, pool=True), U("b", quota=4, pool=True)]
    step = _by_key(_steps(students=students, units=units))["kapasite"]
    assert step.state == STATE_DONE


# ---- adım 4: gereksinimler ----

def test_requirements_step_blocked_without_units():
    assert _by_key(_steps())["gereksinimler"].state == STATE_BLOCKED


def test_requirements_step_todo_when_none_defined():
    step = _by_key(_steps(units=[U()]))["gereksinimler"]
    assert step.state == STATE_TODO


def test_requirements_step_ignores_inactive():
    step = _by_key(
        _steps(units=[U()], reqs=[R(active=False)])
    )["gereksinimler"]
    assert step.state == STATE_TODO


def test_requirements_step_counts_required_and_preferred():
    reqs = [R("a"), R("b"), R("c", severity=SEVERITY_PREFERRED)]
    step = _by_key(_steps(units=[U()], reqs=reqs))["gereksinimler"]
    assert step.state == STATE_DONE
    assert "2 zorunlu" in step.detail and "1 tercih" in step.detail


# ---- adım 5: üretim ----

def test_generate_step_todo_when_no_assignments():
    step = _by_key(_steps(students=[S(0)]))["uret"]
    assert step.state == STATE_TODO


def test_generate_step_warns_when_partially_done():
    s = S(0)
    asg = [Assignment(student_id=s.id, month="EYLÜL", unit_id="u")]
    step = _by_key(_steps(students=[s], asg=asg))["uret"]
    assert step.state == STATE_WARN
    assert "EKİM" in step.detail


def test_generate_step_done_when_all_months_filled():
    s = S(0)
    asg = [Assignment(student_id=s.id, month=m, unit_id="u") for m in MONTHS]
    step = _by_key(_steps(students=[s], asg=asg))["uret"]
    assert step.state == STATE_DONE


def test_generate_step_ignores_other_students_assignments():
    s, other = S(0), S(1)
    asg = [Assignment(student_id=other.id, month=m, unit_id="u") for m in MONTHS]
    # other da aktif öğrenci olduğu için ayları dolu sayılır
    step = _by_key(_steps(students=[s, other], asg=asg))["uret"]
    assert step.state == STATE_DONE


# ---- ilerleme / sıradaki adım ----

def test_progress_counts_done_steps():
    done, total = progress(_steps())
    assert total == 5 and done == 0


def test_first_actionable_is_the_earliest_unfinished():
    assert first_actionable(_steps()).key == "ogrenciler"


def test_first_actionable_skips_completed_steps():
    students = [S(0, group=1), S(1, group=2)]
    steps = _steps(students=students)
    # öğrenciler ✅, gruplar ✅ → sıradaki kapasite
    assert first_actionable(steps).key == "kapasite"


def test_first_actionable_none_when_everything_done():
    students = [S(0, group=1), S(1, group=2)]
    units = [U("a", group=1, quota=3, pool=True),
             U("b", group=2, quota=3, pool=True)]
    asg = [
        Assignment(student_id=s.id, month=m, unit_id="u")
        for s in students for m in MONTHS
    ]
    steps = _steps(students=students, units=units, reqs=[R()], asg=asg,
                   classes=[ClassGroup(name="A")])
    assert first_actionable(steps) is None
    assert progress(steps) == (5, 5)
