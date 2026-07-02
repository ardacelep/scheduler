"""Uçtan uca: referans Excel'den seed'lenen gerçek veriyle çözüm.

Yeni bir dönem başlangıcı simüle edilir (geçmiş boş), 1. grup için ardışık
aylar çözülür ve sonuç kural denetiminden hatasız geçer.
"""
import json

import pytest

from rotasyon.excel_io import read_rotation_workbook
from rotasyon.importer import build_dataset
from rotasyon.models import Assignment, DEFAULT_SETTINGS
from rotasyon.rules import ERROR, check_all
from rotasyon.solver import solve_month

from conftest import REFERENCE_XLSX

pytestmark = pytest.mark.skipif(
    not REFERENCE_XLSX.exists(), reason="referans xlsx yok"
)

# Test hızı için kısaltılmış süre sınırı; FEASIBLE de kabul edilir
SETTINGS = json.loads(json.dumps(DEFAULT_SETTINGS))
SETTINGS["solver"]["time_limit_seconds"] = 10


@pytest.fixture(scope="module")
def seeded():
    ds = build_dataset(read_rotation_workbook(REFERENCE_XLSX))
    # bilinmeyen cinsiyetleri doldur (gerçekte kullanıcı arayüzden girer)
    for s in ds.students:
        if not s.gender:
            s.gender = "K"
    return ds


@pytest.mark.parametrize("group", [1, 2])
def test_single_month_solve_passes_rule_check(seeded, group):
    students = [s for s in seeded.students if s.group == group]
    units = [u for u in seeded.units if u.group in (0, group) and u.active]
    r = solve_month(students, units, "EYLÜL", history=[], settings=SETTINGS)
    assert r.ok, r.infeasible_reasons
    assignments = [
        Assignment(student_id=sid, month="EYLÜL", unit_id=uid)
        for sid, uid in r.assignments.items()
    ]
    violations = check_all(students, units, assignments, SETTINGS["months"])
    errors = [v for v in violations if v.severity == ERROR]
    assert errors == [], [e.message for e in errors]


def test_three_sequential_months_group1(seeded):
    """Aylar ardışık çözülür; geçmiş büyüdükçe kurallar korunur."""
    group = 1
    students = [s for s in seeded.students if s.group == group]
    units = [u for u in seeded.units if u.group in (0, group) and u.active]
    months = SETTINGS["months"]
    history: list[Assignment] = []
    for month in months[:3]:
        r = solve_month(
            students, units, month, history=history, settings=SETTINGS
        )
        assert r.ok, (month, r.infeasible_reasons)
        history += [
            Assignment(student_id=sid, month=month, unit_id=uid)
            for sid, uid in r.assignments.items()
        ]
    violations = check_all(students, units, history, months)
    errors = [v for v in violations if v.severity == ERROR]
    assert errors == [], [e.message for e in errors]
    # her ay herkes atanmış
    assert len(history) == 3 * len(students)
