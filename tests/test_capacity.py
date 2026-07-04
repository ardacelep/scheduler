"""Sezon kapasite ön-denetimi (rotasyon/capacity.py) testleri."""
from rotasyon.capacity import ERROR, WARNING, season_capacity_findings
from rotasyon.models import DEFAULT_MONTHS, Student, Unit, FEMALE, MALE
from conftest import make_assignment


def _world(n_students=8, dis_quota=4, headroom=0):
    students = [
        Student(full_name=f"K{i}", gender=FEMALE, group=1) for i in range(n_students // 2)
    ] + [
        Student(full_name=f"E{i}", gender=MALE, group=1)
        for i in range(n_students - n_students // 2)
    ]
    units = [
        Unit(name="DİŞ", group=1, quota=dis_quota),
        Unit(name="HAVUZ", group=1, quota=n_students - dis_quota + headroom),
    ]
    return students, units


def test_exact_fill_trap_warned():
    """Toplam kontenjan öğrenci sayısına eşitse uyarı üretilir."""
    students, units = _world()
    f = season_capacity_findings(students, units, DEFAULT_MONTHS, [])
    assert any(x.level == WARNING and "TAM eşit" in x.message for x in f)


def test_headroom_silences_trap():
    """Pay bırakılınca tuzak uyarısı ve DİŞ hatası kaybolur."""
    students, units = _world(headroom=3)
    f = season_capacity_findings(students, units, DEFAULT_MONTHS, [])
    assert f == []


def test_forced_unit_distinct_shortage_is_error():
    """8 öğrenci, DİŞ kontenjan 4, 10 ay → 40 farklı öğrenci gerekir ama 8
    kişi var: yapısal hata + kontenjan önerisi."""
    students, units = _world()
    f = season_capacity_findings(students, units, DEFAULT_MONTHS, [])
    errs = [x for x in f if x.level == ERROR]
    assert errs and "DİŞ" in errs[0].message
    assert "40 FARKLI" in errs[0].message


def test_must_fill_gender_shortage():
    """Yalnız-erkek must_fill birim: erkek sayısı < ay sayısı → hata
    (gerçek 7-erkek vakasının genellemesi)."""
    students = [
        Student(full_name=f"K{i}", gender=FEMALE, group=1) for i in range(12)
    ] + [Student(full_name=f"E{i}", gender=MALE, group=1) for i in range(4)]
    units = [
        Unit(name="FTR", group=1, quota=1, gender_restriction=MALE, must_fill=True),
        Unit(name="HAVUZ", group=1, quota=30),
    ]
    f = season_capacity_findings(students, units, DEFAULT_MONTHS, [])
    errs = [x for x in f if x.level == ERROR]
    assert errs and "erkek" in errs[0].message.lower()


def test_visited_students_reduce_capacity():
    """DİŞ'i görmüş öğrenciler kalan kapasiteden düşülür."""
    students, units = _world(headroom=0)
    dis = units[0]
    # 4 öğrenci EYLÜL'de DİŞ'e gitmiş; kalan 9 ayda 4×9=36 gerekir, uygun 4
    assignments = [make_assignment(s, dis, "EYLÜL") for s in students[:4]]
    # diğerleri de EYLÜL'de havuza gitmiş (ay 'dolu' sayılsın)
    assignments += [make_assignment(s, units[1], "EYLÜL") for s in students[4:]]
    f = season_capacity_findings(students, units, DEFAULT_MONTHS, assignments)
    errs = [x for x in f if x.level == ERROR and "DİŞ" in x.message]
    assert errs and "uygun yalnız 4" in errs[0].message


def test_inactive_students_excluded():
    """Ayrılan (pasif) öğrenci kapasite hesabına girmez."""
    students, units = _world(headroom=3)
    for s in students[:2]:
        s.active = False
    f = season_capacity_findings(students, units, DEFAULT_MONTHS, [])
    # 6 aktif öğrenci, DİŞ q=4 forced değil (headroom var) → bulgu yok
    assert f == []
