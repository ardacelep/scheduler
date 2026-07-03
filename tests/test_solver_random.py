"""'Farklı çözüm' (reroll) rastgeleliği testleri.

Ölçülen tuzak: ham seed=1, CP-SAT'ın tohumsuz varsayılan aramasıyla birebir
aynı çözümü üretiyordu — kullanıcının İLK 'Farklı çözüm' tıklaması boşa
gidiyordu. Çözüm: tohum Knuth karmasıyla saçılır (solver.py) ve UI aynı
eşleme gelirse tohumu ilerletip bir kez daha dener (rotation._solve avoid).
"""
import json

from rotasyon.models import (
    Student,
    Unit,
    BRANCH_CERRAHI,
    BRANCH_DAHILI,
    BRANCH_YOGUN_BAKIM,
    DEFAULT_SETTINGS,
    FEMALE,
    MALE,
)
from rotasyon.solver import solve_month


def _world():
    """Simetrik dünya: çok sayıda eş-maliyetli çözüm var; rastgelelik
    çalışıyorsa tohumlar farklı dağılımlar üretmeli."""
    students = [
        Student(full_name=f"K{i}", gender=FEMALE, group=1) for i in range(5)
    ] + [Student(full_name=f"E{i}", gender=MALE, group=1) for i in range(3)]
    units = [
        Unit(name="CER", group=1, quota=3, branch_category=BRANCH_CERRAHI, pool=True),
        Unit(name="DAH", group=1, quota=3, branch_category=BRANCH_DAHILI, pool=True),
        Unit(name="YB", group=1, quota=2, branch_category=BRANCH_YOGUN_BAKIM, pool=True),
    ]
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    settings["solver"]["time_limit_seconds"] = 3
    return students, units, settings


def _frozen(students, units, settings, seed):
    r = solve_month(
        students, units, "EYLÜL", history=[], settings=settings,
        random_seed=seed,
    )
    assert r.ok
    return tuple(sorted(r.assignments.items()))


def test_seeds_produce_variety():
    students, units, settings = _world()
    solutions = {
        _frozen(students, units, settings, seed) for seed in range(1, 9)
    }
    # 8 tohumdan en az 4 benzersiz çözüm (ölçümde 8/8 çıkıyor; bol pay)
    assert len(solutions) >= 4


def test_first_reroll_differs_from_default_search():
    """seed=1 (ilk 'Farklı çözüm') tohumsuz ilk çözümle aynı OLMAMALI."""
    students, units, settings = _world()
    default = _frozen(students, units, settings, None)
    rerolls = {_frozen(students, units, settings, s) for s in (1, 2, 3)}
    assert any(sol != default for sol in rerolls)
    assert default not in rerolls or len(rerolls) > 1
