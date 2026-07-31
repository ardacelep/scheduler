"""Doldurma politikası (rotasyon.fill_policy) — saf mantık.

Dört ayrı bayrağın (must_fill/single_slot/pool/reserve) tek seçimlik
politikaya doğru indirgenmesi ve grubun kapasite matematiği.
"""
from rotasyon.fill_policy import (
    POLICY_FREE,
    POLICY_MUST_FILL,
    POLICY_POOL,
    POLICY_PREFER_FILL,
    POLICY_RESERVE,
    apply_policy,
    group_capacity_plan,
    policy_of,
)
from rotasyon.models import Student, Unit


def U(name="X", group=1, quota=1, active=True, **flags):
    return Unit(name=name, group=group, quota=quota, active=active, **flags)


def S(i=0, group=1, active=True):
    return Student(full_name=f"Ö{i}", gender="K", group=group, active=active)


# ---- policy_of: bayraklardan politika okuma ----

def test_no_flags_is_free():
    assert policy_of(U()) == POLICY_FREE


def test_each_flag_maps_to_its_policy():
    assert policy_of(U(must_fill=True)) == POLICY_MUST_FILL
    assert policy_of(U(single_slot=True)) == POLICY_PREFER_FILL
    assert policy_of(U(pool=True)) == POLICY_POOL
    assert policy_of(U(reserve=True)) == POLICY_RESERVE


def test_must_fill_wins_over_single_slot():
    """Katalogdaki FTR.ÜNİT ikisini birden taşır; motorda must_fill baskındır."""
    assert policy_of(U(must_fill=True, single_slot=True)) == POLICY_MUST_FILL


def test_reserve_wins_over_pool():
    assert policy_of(U(pool=True, reserve=True)) == POLICY_RESERVE


# ---- apply_policy: politikadan bayrak yazma ----

def test_apply_sets_exactly_one_flag():
    u = U()
    apply_policy(u, POLICY_POOL)
    assert (u.must_fill, u.single_slot, u.pool, u.reserve) == (
        False, False, True, False
    )


def test_apply_clears_previous_flags():
    u = U(must_fill=True, single_slot=True)
    apply_policy(u, POLICY_RESERVE)
    assert (u.must_fill, u.single_slot, u.pool, u.reserve) == (
        False, False, False, True
    )


def test_apply_free_clears_everything():
    u = U(pool=True)
    apply_policy(u, POLICY_FREE)
    assert not any((u.must_fill, u.single_slot, u.pool, u.reserve))


def test_apply_reports_whether_it_changed():
    u = U(pool=True)
    assert apply_policy(u, POLICY_POOL) is False  # zaten öyle
    assert apply_policy(u, POLICY_FREE) is True


def test_apply_ignores_unknown_policy():
    u = U(pool=True)
    assert apply_policy(u, "bilinmeyen") is False
    assert u.pool is True


def test_policy_round_trip():
    for p in (POLICY_MUST_FILL, POLICY_PREFER_FILL, POLICY_POOL,
              POLICY_RESERVE, POLICY_FREE):
        u = U()
        apply_policy(u, p)
        assert policy_of(u) == p


# ---- group_capacity_plan: matematik ----

def test_buckets_count_units_and_quota():
    units = [
        U("a", quota=2, must_fill=True),
        U("b", quota=3, pool=True),
        U("c", quota=4, pool=True),
    ]
    plan = group_capacity_plan(units, [], 1)
    assert plan.buckets[POLICY_MUST_FILL].unit_count == 1
    assert plan.buckets[POLICY_MUST_FILL].quota_total == 2
    assert plan.buckets[POLICY_POOL].unit_count == 2
    assert plan.buckets[POLICY_POOL].quota_total == 7


def test_only_that_groups_active_units_count():
    units = [
        U("a", group=1, quota=5), U("b", group=2, quota=9),
        U("c", group=1, quota=3, active=False),
    ]
    assert group_capacity_plan(units, [], 1).active_quota_total == 5


def test_group_zero_unit_counts_for_both():
    units = [U("shared", group=0, quota=4)]
    assert group_capacity_plan(units, [], 1).active_quota_total == 4
    assert group_capacity_plan(units, [], 2).active_quota_total == 4


def test_student_count_only_active_of_that_group():
    students = [S(0), S(1), S(2, active=False), S(3, group=2)]
    assert group_capacity_plan([], students, 1).student_count == 2


def test_remaining_is_students_minus_must_fill():
    units = [U("a", quota=4, must_fill=True), U("b", quota=20, pool=True)]
    plan = group_capacity_plan(units, [S(i) for i in range(30)], 1)
    assert plan.must_fill_total == 4
    assert plan.remaining == 26


def test_pool_per_unit_reserves_one_for_each_prefer_fill():
    # 30 öğrenci, 4 tam dolan → 26 kalan; 6 "mümkünse" birimi birer kişi alır
    # → 20 öğrenci 5 havuz birimine ≈ 4.0
    units = (
        [U("m", quota=4, must_fill=True)]
        + [U(f"p{i}", quota=3, single_slot=True) for i in range(6)]
        + [U(f"h{i}", quota=6, pool=True) for i in range(5)]
    )
    plan = group_capacity_plan(units, [S(i) for i in range(30)], 1)
    assert plan.pool_per_unit == 4.0


def test_pool_per_unit_none_without_pool_units():
    units = [U("a", quota=5, single_slot=True)]
    assert group_capacity_plan(units, [S(i) for i in range(5)], 1).pool_per_unit is None


def test_pool_per_unit_never_negative():
    # tam dolanlar herkesi yutuyor → havuza kimse kalmıyor
    units = [U("m", quota=10, must_fill=True), U("h", quota=5, pool=True)]
    plan = group_capacity_plan(units, [S(i) for i in range(10)], 1)
    assert plan.pool_per_unit == 0.0


def test_balance_is_quota_minus_students():
    units = [U("a", quota=8)]
    assert group_capacity_plan(units, [S(i) for i in range(5)], 1).balance == 3


# ---- uyarılar ----

def _warn_text(plan):
    return " ".join(plan.warnings)


def test_warns_when_must_fill_exceeds_students():
    units = [U("m", quota=12, must_fill=True)]
    plan = group_capacity_plan(units, [S(i) for i in range(10)], 1)
    assert "hiçbir ay üretilemez" in _warn_text(plan)


def test_warns_when_must_fill_consumes_everyone():
    units = [U("m", quota=10, must_fill=True)]
    plan = group_capacity_plan(units, [S(i) for i in range(10)], 1)
    assert "tamamını" in _warn_text(plan)


def test_warns_when_capacity_below_students():
    units = [U("a", quota=3, pool=True)]
    plan = group_capacity_plan(units, [S(i) for i in range(10)], 1)
    assert "yer yok" in _warn_text(plan)


def test_warns_on_exact_fill_trap():
    units = [U("a", quota=5, pool=True), U("b", quota=5, pool=True)]
    plan = group_capacity_plan(units, [S(i) for i in range(10)], 1)
    assert "tam eşit" in _warn_text(plan)


def test_warns_when_no_pool_unit_for_remaining_students():
    units = [U("m", quota=2, must_fill=True), U("s", quota=20, single_slot=True)]
    plan = group_capacity_plan(units, [S(i) for i in range(10)], 1)
    assert "Havuz" in _warn_text(plan)


def test_healthy_setup_has_no_warnings():
    units = (
        [U("m", quota=4, must_fill=True)]
        + [U(f"h{i}", quota=5, pool=True) for i in range(6)]
    )
    plan = group_capacity_plan(units, [S(i) for i in range(20)], 1)
    assert plan.warnings == []


def test_no_warnings_without_students():
    units = [U("m", quota=99, must_fill=True)]
    assert group_capacity_plan(units, [], 1).warnings == []


# ---- çözücü ön-denetimi: "tam dolmalı" toplamı grubu aşamaz ----

def test_solver_names_must_fill_overload_as_the_reason():
    """Kapasite panelinin verdiği uyarıyı çözücü de aynı sebeple doğrulamalı.

    Bu kontrol eklenmeden önce unsat core alakasız bir aile gösteriyordu
    ("elle sabitlenen atamalar" — hiç kilitli hücre yokken).
    """
    from rotasyon.solver import solve_month

    settings = {
        "months": ["EYLÜL", "EKİM"],
        "season_requirements": [],
        "solver": {"time_limit_seconds": 5, "num_workers": 1, "weights": {
            "pool_balance": 5, "repeat_pair": 10, "ebelik_priority": 20,
            "core_branch_early": 2, "single_slot_fill": 50, "reserve_use": 15,
            "gender_balance": 6, "intensive_surplus": 2,
        }},
    }
    units = [
        U("A", quota=5, must_fill=True),
        U("B", quota=5, must_fill=True),
        U("C", quota=9, pool=True),
    ]
    students = [S(i) for i in range(4)]  # 4 öğrenci, 10 zorunlu yer
    res = solve_month(students, units, "EYLÜL", [], settings)
    assert res.status == "INFEASIBLE"
    assert any("Tam dolmalı" in r for r in res.infeasible_reasons), \
        res.infeasible_reasons


def test_solver_accepts_must_fill_that_fits():
    from rotasyon.solver import solve_month

    settings = {
        "months": ["EYLÜL", "EKİM"],
        "season_requirements": [],
        "solver": {"time_limit_seconds": 5, "num_workers": 1, "weights": {
            "pool_balance": 5, "repeat_pair": 10, "ebelik_priority": 20,
            "core_branch_early": 2, "single_slot_fill": 50, "reserve_use": 15,
            "gender_balance": 6, "intensive_surplus": 2,
        }},
    }
    units = [U("A", quota=2, must_fill=True), U("C", quota=9, pool=True)]
    res = solve_month([S(i) for i in range(4)], units, "EYLÜL", [], settings)
    assert res.status in ("OPTIMAL", "FEASIBLE"), res.infeasible_reasons
