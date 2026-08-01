"""Gereksinimler ÜRETİME gerçekten etki ediyor mu?

Bu dosya bir regresyon bekçisidir. Gereksinim modeli, ekranı ve birim
testleri yazıldığı halde hiçbir çağrı yeri `requirements=` geçirmiyordu:
kullanıcı gereksinim tanımlıyor, çıktı hiç değişmiyordu. Testler geçiyordu
çünkü hepsi solve_season'ı DOĞRUDAN çağırıyordu.

Buradaki testler motoru UI'ın kullandığı üst seviye yollardan (planner,
risk, capacity) çağırır — yani parametre bir yerde düşerse burası kırılır.
"""
import inspect

from rotasyon.capacity import ERROR, season_requirement_findings
from rotasyon.models import (
    Assignment,
    Requirement,
    SCOPE_ALL,
    Student,
    Unit,
    BRANCH_DIGER,
)
from rotasyon.planner import plan_season
from rotasyon.risk import forward_risks

MONTHS = ["EYLÜL", "EKİM", "KASIM"]
SETTINGS = {
    "months": MONTHS,
    "season_requirements": [],  # eski yol BOŞ: etki varsa gereksinimden gelir
    "solver": {
        "time_limit_seconds": 5, "season_time_limit_seconds": 20,
        "num_workers": 1,
        "weights": {
            "pool_balance": 5, "repeat_pair": 10, "ebelik_priority": 20,
            "core_branch_early": 2, "single_slot_fill": 50, "reserve_use": 15,
            "gender_balance": 6, "intensive_surplus": 2,
        },
    },
}


def _units():
    return [
        Unit(name=n, group=1, quota=3, branch_category=BRANCH_DIGER, pool=True)
        for n in ("ACİL", "EKG", "DİYALİZ", "ALÇI")
    ]


def _students(n=3):
    return [
        Student(full_name=f"Ö{i}", gender="K", group=1, class_name="A")
        for i in range(n)
    ]


def _seen(new, units, students):
    by_id = {u.id: u for u in units}
    names = {s.id: s.full_name for s in students}
    out: dict[str, set[str]] = {s.full_name: set() for s in students}
    for a in new:
        out[names[a.student_id]].add(by_id[a.unit_id].name)
    return out


# ---- planner: toplu üretim yolu ----

def test_plan_season_honours_requirements():
    """UI'ın kullandığı plan_season gereksinimi UYGULAMALI."""
    units, students = _units(), _students()
    req = Requirement(name="Herkes ACİL görsün", scope=SCOPE_ALL,
                      unit_keys=["ACİL"])
    new, solved, failed = plan_season(
        students, units, MONTHS, [], settings=SETTINGS,
        requirements=[req],
    )
    assert not failed, failed
    for ad, birimler in _seen(new, units, students).items():
        assert "ACİL" in birimler, f"{ad}: {birimler}"


def test_plan_season_without_requirements_is_unconstrained():
    """Karşıt kanıt: gereksinim verilmezse ACİL zorunlu DEĞİL.

    (Aksi halde yukarıdaki test gereksinimden değil şanstan geçerdi.)
    """
    units, students = _units(), _students()
    # ACİL'i pasifleştir: gereksinim yokken sezon yine çözülmeli
    for u in units:
        if u.name == "ACİL":
            u.active = False
    new, solved, failed = plan_season(
        students, units, MONTHS, [], settings=SETTINGS,
    )
    assert not failed, failed
    assert all("ACİL" not in b for b in _seen(new, units, students).values())


def test_plan_season_reports_impossible_requirement():
    units, students = _units(), _students()
    req = Requirement(name="Olmayan birim", scope=SCOPE_ALL,
                      unit_keys=["ACİL"], min_count=1)
    for u in units:
        if u.name == "ACİL":
            u.active = False
    new, solved, failed = plan_season(
        students, units, MONTHS, [], settings=SETTINGS, requirements=[req],
    )
    # hastanede o birim yok → gereksinim uygulanmaz, sezon yine çözülür
    assert not failed, failed


# ---- risk: ileriye dönük denetim ----

def test_forward_risks_uses_requirements():
    """Kalan ayda karşılanamayacak gereksinim RİSK olarak görünmeli."""
    units, students = _units(), _students(1)
    s = students[0]
    # üç ayın ikisi dolu, kalan tek ay; iki ayrı gereksinim → yetişmez
    asg = [
        Assignment(student_id=s.id, month="EYLÜL", unit_id=units[1].id),
        Assignment(student_id=s.id, month="EKİM", unit_id=units[2].id),
    ]
    reqs = [
        Requirement(name="ACİL", scope=SCOPE_ALL, unit_keys=["ACİL"]),
        Requirement(name="ALÇI", scope=SCOPE_ALL, unit_keys=["ALÇI"]),
    ]
    risks = forward_risks(
        students, units, MONTHS, asg, None, SETTINGS, reqs
    )
    assert any(r.level == ERROR for r in risks), [r.message for r in risks]


def test_forward_risks_silent_without_requirements():
    """Karşıt kanıt: aynı veri, gereksinim yokken risk üretmemeli."""
    units, students = _units(), _students(1)
    s = students[0]
    asg = [
        Assignment(student_id=s.id, month="EYLÜL", unit_id=units[1].id),
        Assignment(student_id=s.id, month="EKİM", unit_id=units[2].id),
    ]
    risks = forward_risks(students, units, MONTHS, asg, None, SETTINGS)
    assert not [r for r in risks if r.level == ERROR]


def test_capacity_findings_name_the_requirement():
    units, students = _units(), _students(1)
    s = students[0]
    asg = [
        Assignment(student_id=s.id, month=m, unit_id=u.id)
        for m, u in zip(MONTHS, units[1:])
    ]
    req = Requirement(name="Kaçırılan gereksinim", scope=SCOPE_ALL,
                      unit_keys=["ACİL"])
    bulgular = season_requirement_findings(
        students, units, MONTHS, asg, SETTINGS, [req]
    )
    assert bulgular, "hiç bulgu yok"
    assert any("Kaçırılan gereksinim" in b.message for b in bulgular)


# ---- imza bekçisi ----

def test_engine_entry_points_accept_requirements():
    """Motora giden üst seviye yolların hepsi parametreyi TAŞIMALI.

    Yeni bir giriş noktası eklenip parametre unutulursa burası uyarır.
    """
    from rotasyon import planner, risk, rules, solver, capacity

    beklenen = [
        solver.solve_month, solver.solve_season,
        rules.check_all,
        planner.plan_remaining, planner.plan_season,
        risk.forward_risks, risk.deep_feasibility,
        capacity.season_requirement_findings,
    ]
    for fn in beklenen:
        assert "requirements" in inspect.signature(fn).parameters, fn.__name__
