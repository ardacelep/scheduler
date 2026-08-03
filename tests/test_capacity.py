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


def test_exact_fill_alone_is_not_a_warning():
    """Sıfır boşluk TEK BAŞINA uyarı değildir.

    Eski model birimleri sabit alıp öğrencileri onlara yerleştiriyordu; orada
    "pay bırakın" makul bir tavsiyeydi. Yeni modelde kontenjanlar öğrenci
    sayısına göre belirleniyor — tam oturmak HEDEF. Kullanıcının elle
    hazırladığı gerçek rotasyonlar da tam oturuyor (36 öğrenci / 36 yer).

    Burada DİŞ birimi ayrıca gerçek bir darboğaz yaratıyor; onun HATA'sı
    kalmalı. Yasaklanan şey yalnız genel "tam eşit" uyarısı.
    """
    students, units = _world()
    f = season_capacity_findings(students, units, DEFAULT_MONTHS, [])
    assert not [x for x in f if x.level == WARNING]
    assert not any("pay bırak" in x.message.lower() for x in f)


def test_exact_fill_still_drives_the_per_unit_check():
    """Sıfır boşluk denetimi KAPATMAZ: tıkanan birim adıyla söylenmeli.

    Uyarıyı kaldırırken asıl değerli kontrolü de kaldırmadığımızın kanıtı.
    """
    students, units = _world()
    f = season_capacity_findings(students, units, DEFAULT_MONTHS, [])
    errs = [x for x in f if x.level == ERROR]
    assert errs and "DİŞ" in errs[0].message


def test_headroom_silences_the_error():
    """Pay bırakılınca DİŞ hatası da kaybolur (bulgu hiç kalmaz)."""
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
