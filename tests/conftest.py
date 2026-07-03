import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rotasyon.models import (
    Assignment,
    ClassGroup,
    Student,
    Unit,
    BRANCH_CERRAHI,
    BRANCH_DAHILI,
    BRANCH_DIGER,
    BRANCH_DOGUM_SALONU,
    BRANCH_YOGUN_BAKIM,
    DEFAULT_SETTINGS,
    FEMALE,
    MALE,
    PROGRAM_EBELIK,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_REFERENCE_CANDIDATES = [
    PROJECT_ROOT / "example" / "ARDA_ROTASYON.xlsx",
    PROJECT_ROOT / "ARDA_ROTASYON.xlsx",
]
REFERENCE_XLSX = next(
    (p for p in _REFERENCE_CANDIDATES if p.exists()), _REFERENCE_CANDIDATES[0]
)
# Gerçek dünyadan örnek belgeler (varsa ek testler koşar)
EXAMPLE_DIR = PROJECT_ROOT / "example"
GRUP_XLSX = EXAMPLE_DIR / "GRUP p.s.ç-ç.p.c (1).xlsx"
ROSTER_XLSX = EXAMPLE_DIR / "2025-2026 SML ÖĞRENCİ LİSTESİ.xlsx"


@pytest.fixture
def settings():
    import json

    return json.loads(json.dumps(DEFAULT_SETTINGS))


@pytest.fixture
def small_world():
    """8 öğrenci + kontenjan toplamı 8 olan sentetik birim seti.

    Kural testlerinin çoğu bu küçük dünya üzerinde koşar.
    """
    students = [
        Student(full_name="Kız 1", gender=FEMALE, group=1, class_name="A"),
        Student(full_name="Kız 2", gender=FEMALE, group=1, class_name="A"),
        Student(full_name="Kız 3", gender=FEMALE, group=1, class_name="B"),
        Student(full_name="Kız 4", gender=FEMALE, group=1, class_name="B"),
        Student(full_name="Erkek 1", gender=MALE, group=1, class_name="A"),
        Student(full_name="Erkek 2", gender=MALE, group=1, class_name="A"),
        Student(full_name="Erkek 3", gender=MALE, group=1, class_name="B"),
        Student(
            full_name="Ebe 1",
            gender=FEMALE,
            group=1,
            class_name="B",
            program=PROGRAM_EBELIK,
        ),
    ]
    units = [
        Unit(name="1.KAT CERR.", group=1, quota=2, branch_category=BRANCH_CERRAHI, pool=True),
        Unit(name="4.KAT DAH.", group=1, quota=1, branch_category=BRANCH_DAHILI, pool=True),
        Unit(name="YB/A", group=1, quota=1, branch_category=BRANCH_YOGUN_BAKIM, pool=True),
        Unit(
            name="FTR.ÜNİT",
            group=1,
            quota=1,
            gender_restriction=FEMALE,
            branch_category=BRANCH_DIGER,
            pool=True,
            must_fill=True,
        ),
        Unit(
            name="FTR.ÜNİT",
            group=1,
            quota=1,
            gender_restriction=MALE,
            branch_category=BRANCH_DIGER,
            pool=True,
            must_fill=True,
        ),
        Unit(name="DİŞ", group=1, quota=1, branch_category=BRANCH_DIGER, single_slot=True),
        Unit(
            name="DOĞ.SAL-Y.DOĞ",
            group=1,
            quota=1,
            branch_category=BRANCH_DOGUM_SALONU,
            ebelik_priority=True,
            single_slot=True,
        ),
    ]
    classes = [ClassGroup(name="A", color_hex="#FFFF00"), ClassGroup(name="B", color_hex="#FF00FF")]
    return students, units, classes


def make_assignment(student, unit, month, **kw):
    return Assignment(student_id=student.id, month=month, unit_id=unit.id, **kw)
