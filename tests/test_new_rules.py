"""BÖLÜMLER VE ÖZELLİKLERİ belgesinden gelen yeni kurallar.

- Madde 20: peş peşe iki ay yoğun (veya hafif) bölüm yasak
- Yedek (gri) birimler: yalnız ihtiyaç olursa kullanılır
- Havuz birimlerinde kız/erkek dengesi
"""
import json

from rotasyon.models import (
    Student,
    Unit,
    BRANCH_DIGER,
    DEFAULT_MONTHS,
    DEFAULT_SETTINGS,
    FEMALE,
    INTENSITY_HAFIF,
    INTENSITY_YOGUN,
    MALE,
)
from rotasyon.rules import ERROR, WARNING, check_all
from rotasyon.solver import solve_month

from conftest import make_assignment


def _settings(**over):
    s = json.loads(json.dumps(DEFAULT_SETTINGS))
    s["season_requirements"] = []  # bu testlerde branş zorunlulukları izole edilir
    s["solver"]["time_limit_seconds"] = 3
    s.update(over)
    return s


# ---------- madde 20: peş peşe yoğunluk ----------

def test_solver_avoids_consecutive_yogun():
    settings = _settings()
    s = Student(full_name="A", gender=FEMALE, group=1)
    yogun1 = Unit(name="ACİL", group=1, quota=1, intensity=INTENSITY_YOGUN)
    yogun2 = Unit(name="YB/B", group=1, quota=1, intensity=INTENSITY_YOGUN)
    normal = Unit(name="LAB", group=1, quota=1)
    history = [make_assignment(s, yogun1, "EYLÜL")]
    r = solve_month(
        [s], [yogun1, yogun2, normal], "EKİM", history=history, settings=settings
    )
    assert r.ok
    assert r.assignments[s.id] == normal.id  # yoğundan sonra yoğun yasak


def test_solver_avoids_consecutive_hafif():
    settings = _settings()
    s = Student(full_name="A", gender=FEMALE, group=1)
    hafif1 = Unit(name="EVRAK", group=1, quota=1, intensity=INTENSITY_HAFIF)
    hafif2 = Unit(name="ECZANE", group=1, quota=1, intensity=INTENSITY_HAFIF)
    normal = Unit(name="LAB", group=1, quota=1)
    history = [make_assignment(s, hafif1, "EYLÜL")]
    r = solve_month(
        [s], [hafif1, hafif2, normal], "EKİM", history=history, settings=settings
    )
    assert r.ok
    assert r.assignments[s.id] == normal.id


def test_solver_checks_next_month_too():
    """Araya ay yeniden üretilirken SONRAKİ ayın yoğunluğu da denetlenir."""
    settings = _settings()
    s = Student(full_name="A", gender=FEMALE, group=1)
    yogun = Unit(name="ACİL", group=1, quota=1, intensity=INTENSITY_YOGUN)
    yogun2 = Unit(name="YB/B", group=1, quota=1, intensity=INTENSITY_YOGUN)
    normal = Unit(name="LAB", group=1, quota=1)
    history = [make_assignment(s, yogun, "KASIM")]  # sonraki ay yoğun
    r = solve_month(
        [s], [yogun, yogun2, normal], "EKİM", history=history, settings=settings
    )
    assert r.ok
    assert r.assignments[s.id] == normal.id


def test_solver_infeasible_reason_mentions_intensity():
    settings = _settings()
    s = Student(full_name="A", gender=FEMALE, group=1)
    yogun1 = Unit(name="ACİL", group=1, quota=1, intensity=INTENSITY_YOGUN)
    yogun2 = Unit(name="YB/B", group=1, quota=1, intensity=INTENSITY_YOGUN)
    history = [make_assignment(s, yogun1, "EYLÜL")]
    r = solve_month(
        [s], [yogun1, yogun2], "EKİM", history=history, settings=settings
    )
    assert not r.ok
    assert any("peş peşe" in x or "atanabilecek birim" in x for x in r.infeasible_reasons)


def test_checker_flags_consecutive_intensity():
    s = Student(full_name="A", gender=FEMALE, group=1)
    y1 = Unit(name="ACİL", group=1, quota=1, intensity=INTENSITY_YOGUN)
    y2 = Unit(name="YB/B", group=1, quota=1, intensity=INTENSITY_YOGUN)
    assignments = [
        make_assignment(s, y1, "EYLÜL"),
        make_assignment(s, y2, "EKİM"),
    ]
    v = check_all([s], [y1, y2], assignments, DEFAULT_MONTHS)
    hits = [x for x in v if x.rule_no == 20]
    assert hits and hits[0].severity == ERROR
    assert "peş peşe" in hits[0].message


def test_checker_allows_gap_between_yogun_months():
    """Yoğun → normal → yoğun serbesttir; yalnız PEŞ PEŞE yasak."""
    s = Student(full_name="A", gender=FEMALE, group=1)
    y1 = Unit(name="ACİL", group=1, quota=1, intensity=INTENSITY_YOGUN)
    n = Unit(name="LAB", group=1, quota=1)
    y2 = Unit(name="YB/B", group=1, quota=1, intensity=INTENSITY_YOGUN)
    assignments = [
        make_assignment(s, y1, "EYLÜL"),
        make_assignment(s, n, "EKİM"),
        make_assignment(s, y2, "KASIM"),
    ]
    v = check_all([s], [y1, n, y2], assignments, DEFAULT_MONTHS)
    assert [x for x in v if x.rule_no == 20] == []


# ---------- yedek (gri) birimler ----------

def test_reserve_unit_avoided_when_capacity_suffices():
    settings = _settings()
    students = [
        Student(full_name="A", gender=FEMALE, group=1),
        Student(full_name="B", gender=MALE, group=1),
    ]
    normal = Unit(name="LAB", group=1, quota=2)
    reserve = Unit(name="MUTEMET", group=1, quota=1, reserve=True)
    r = solve_month(students, [normal, reserve], "EYLÜL", history=[], settings=settings)
    assert r.ok
    assert all(uid == normal.id for uid in r.assignments.values())


def test_reserve_unit_used_when_needed():
    settings = _settings()
    students = [
        Student(full_name="A", gender=FEMALE, group=1),
        Student(full_name="B", gender=MALE, group=1),
    ]
    normal = Unit(name="LAB", group=1, quota=1)
    reserve = Unit(name="MUTEMET", group=1, quota=1, reserve=True)
    r = solve_month(students, [normal, reserve], "EYLÜL", history=[], settings=settings)
    assert r.ok
    assert sorted(r.assignments.values()) == sorted([normal.id, reserve.id])


# ---------- havuzda cinsiyet dengesi ----------

def test_pool_gender_balance_soft():
    settings = _settings()
    students = [
        Student(full_name=f"K{i}", gender=FEMALE, group=1) for i in range(2)
    ] + [Student(full_name=f"E{i}", gender=MALE, group=1) for i in range(2)]
    p1 = Unit(name="KAT1", group=1, quota=2, pool=True, branch_category=BRANCH_DIGER)
    p2 = Unit(name="KAT2", group=1, quota=2, pool=True, branch_category=BRANCH_DIGER)
    r = solve_month(students, [p1, p2], "EYLÜL", history=[], settings=settings)
    assert r.ok
    by_unit = {p1.id: [], p2.id: []}
    genders = {s.id: s.gender for s in students}
    for sid, uid in r.assignments.items():
        by_unit[uid].append(genders[sid])
    for glist in by_unit.values():
        assert glist.count("K") == 1 and glist.count("E") == 1


def test_checker_warns_on_gender_imbalance():
    students = [
        Student(full_name=f"K{i}", gender=FEMALE, group=1) for i in range(3)
    ]
    pool = Unit(name="KAT1", group=1, quota=3, pool=True)
    assignments = [make_assignment(s, pool, "EYLÜL") for s in students]
    v = check_all(students, [pool], assignments, DEFAULT_MONTHS)
    hits = [x for x in v if x.rule_no == 21]
    assert hits and hits[0].severity == WARNING
