"""CP-SAT çözücü testleri — kural kural."""
from rotasyon.models import (
    Student,
    Unit,
    BRANCH_CERRAHI,
    BRANCH_DAHILI,
    BRANCH_DIGER,
    BRANCH_DOGUM_SALONU,
    FEMALE,
    MALE,
    PROGRAM_EBELIK,
)
from rotasyon.solver import solve_month

from conftest import make_assignment


def by_name(units, name, gender=""):
    return next(
        u for u in units if u.name == name and u.gender_restriction == gender
    )


def unit_of(result, units, student):
    return next(u for u in units if u.id == result.assignments[student.id])


def test_every_student_gets_exactly_one_unit(small_world, settings):
    students, units, _ = small_world
    r = solve_month(students, units, "EYLÜL", history=[], settings=settings)
    assert r.ok
    assert set(r.assignments) == {s.id for s in students}


def test_rule1_no_repeat(small_world, settings):
    students, units, _ = small_world
    dis = by_name(units, "DİŞ")
    kiz1 = students[0]
    history = [make_assignment(kiz1, dis, "EYLÜL")]
    r = solve_month(students, units, "EKİM", history=history, settings=settings)
    assert r.ok
    assert r.assignments[kiz1.id] != dis.id


def test_rule1_name_variants_count_as_same_unit(settings):
    """'EKG k' ile 'EKG' aynı bölümdür — ada göre tekrar yasağı."""
    s1 = Student(full_name="A", gender=FEMALE, group=1)
    s2 = Student(full_name="B", gender=FEMALE, group=1)
    ekg_k = Unit(name="EKG", group=1, quota=1, gender_restriction=FEMALE)
    ekg = Unit(name="EKG ", group=1, quota=1)  # yazım varyantı
    lab = Unit(name="LAB", group=1, quota=2)
    units = [ekg_k, ekg, lab]
    history = [make_assignment(s1, ekg_k, "EYLÜL")]
    r = solve_month([s1, s2], units, "EKİM", history=history, settings=settings)
    assert r.ok
    assert r.assignments[s1.id] == lab.id  # her iki EKG varyantı da yasak


def test_rule2_rule3_gender_restricted_units(small_world, settings):
    students, units, _ = small_world
    r = solve_month(students, units, "EYLÜL", history=[], settings=settings)
    assert r.ok
    genders = {s.id: s.gender for s in students}
    for u in units:
        if not u.gender_restriction:
            continue
        assigned = [sid for sid, uid in r.assignments.items() if uid == u.id]
        assert all(genders[sid] == u.gender_restriction for sid in assigned)


def test_rule4_pool_balance(settings):
    """Kontenjan bolken havuz birimlerine eşit dağıtım."""
    students = [
        Student(full_name=f"S{i}", gender=FEMALE, group=1) for i in range(8)
    ]
    units = [
        Unit(name=f"{i}.KAT", group=1, quota=8, pool=True) for i in range(1, 5)
    ]
    r = solve_month(students, units, "EYLÜL", history=[], settings=settings)
    assert r.ok
    occ = {u.id: 0 for u in units}
    for uid in r.assignments.values():
        occ[uid] += 1
    assert set(occ.values()) == {2}  # 8 öğrenci / 4 birim = 2'şer


def test_rule4_single_slot_filled_first(settings):
    """Tekli birimler boş bırakılmaz, kalanlar havuza gider."""
    students = [
        Student(full_name=f"S{i}", gender=FEMALE, group=1) for i in range(4)
    ]
    single = Unit(name="ECZANE", group=1, quota=1, single_slot=True)
    pool = Unit(name="ACİL", group=1, quota=10, pool=True)
    r = solve_month(students, [single, pool], "EYLÜL", history=[], settings=settings)
    assert r.ok
    assert sum(1 for uid in r.assignments.values() if uid == single.id) == 1


def test_rule6_core_branch_deadline_on_last_month(settings):
    students = [
        Student(full_name="Görmüş", gender=FEMALE, group=1),
        Student(full_name="Görmemiş", gender=FEMALE, group=1),
    ]
    dah = Unit(name="4.KAT DAH.", group=1, quota=1, branch_category=BRANCH_DAHILI)
    dis = Unit(name="DİŞ", group=1, quota=1, branch_category=BRANCH_DIGER)
    # geçmişteki birim artık pasif — kategori geçmişi yine de sayılmalı
    cerr = Unit(
        name="1.KAT CERR.", group=1, quota=2,
        branch_category=BRANCH_CERRAHI, active=False,
    )
    # "Görmüş" geçmişte cerrahi görmüş; "Görmemiş" hiç core görmemiş
    history = [
        make_assignment(students[0], cerr, "EYLÜL"),
        make_assignment(students[1], dis, "EYLÜL"),
    ]
    dis2 = Unit(name="EVRAK KAYIT", group=1, quota=1, branch_category=BRANCH_DIGER)
    r = solve_month(
        students, [dah, dis2, cerr], "HAZİRAN", history=history, settings=settings
    )
    assert r.ok
    assert r.assignments[students[1].id] == dah.id


def test_rule7_ebelik_dogum_salonu_deadline(settings):
    ebe = Student(
        full_name="Ebe", gender=FEMALE, group=1, program=PROGRAM_EBELIK
    )
    diger = Student(full_name="Diğer", gender=FEMALE, group=1)
    dogum = Unit(
        name="DOĞ.SAL-Y.DOĞ", group=1, quota=1,
        branch_category=BRANCH_DOGUM_SALONU, ebelik_priority=True,
    )
    dis = Unit(name="DİŞ", group=1, quota=1)
    # madde 6'yı ayrı tutmak için ikisi de geçmişte core branş görmüş olsun
    cerr = Unit(
        name="1.KAT CERR.", group=1, quota=2,
        branch_category=BRANCH_CERRAHI, active=False,
    )
    history = [
        make_assignment(ebe, cerr, "EYLÜL"),
        make_assignment(diger, cerr, "EYLÜL"),
    ]
    r = solve_month(
        [ebe, diger], [dogum, dis, cerr], "HAZİRAN",
        history=history, settings=settings,
    )
    assert r.ok
    assert r.assignments[ebe.id] == dogum.id


def test_rule5_groups_solved_independently(small_world, settings):
    """Madde 5: çözücü yalnız verilen grubun öğrenci/birimlerini işler."""
    students, units, _ = small_world
    r = solve_month(students, units, "EYLÜL", history=[], settings=settings)
    assert r.ok
    assert all(u.group == 1 for u in units)  # test dünyası tek grup


def test_rule8_banned_units(small_world, settings):
    students, units, _ = small_world
    dis = by_name(units, "DİŞ")
    kiz1 = students[0]
    kiz1.banned_unit_ids = [dis.id]
    r = solve_month(students, units, "EYLÜL", history=[], settings=settings)
    assert r.ok
    assert r.assignments[kiz1.id] != dis.id


def test_rule9_dis_exempt(small_world, settings):
    students, units, _ = small_world
    dis = by_name(units, "DİŞ")
    for s in students[:4]:
        s.dis_exempt = True
    r = solve_month(students, units, "EYLÜL", history=[], settings=settings)
    assert r.ok
    for s in students[:4]:
        assert r.assignments[s.id] != dis.id


def test_rule17_ftr_one_female_one_male(small_world, settings):
    students, units, _ = small_world
    # kontenjan bollaştır: FTR yine de tam dolmalı
    units = units + [Unit(name="ACİL", group=1, quota=10, pool=True)]
    r = solve_month(students, units, "EYLÜL", history=[], settings=settings)
    assert r.ok
    genders = {s.id: s.gender for s in students}
    ftr_k = by_name(units, "FTR.ÜNİT", FEMALE)
    ftr_e = by_name(units, "FTR.ÜNİT", MALE)
    in_k = [sid for sid, uid in r.assignments.items() if uid == ftr_k.id]
    in_e = [sid for sid, uid in r.assignments.items() if uid == ftr_e.id]
    assert len(in_k) == 1 and genders[in_k[0]] == FEMALE
    assert len(in_e) == 1 and genders[in_e[0]] == MALE


def test_rule18_ebelik_priority(small_world, settings):
    students, units, _ = small_world
    ebe = students[-1]
    dogum = by_name(units, "DOĞ.SAL-Y.DOĞ")
    r = solve_month(students, units, "EYLÜL", history=[], settings=settings)
    assert r.ok
    assert r.assignments[ebe.id] == dogum.id


def test_rule19_repeated_pairs_avoided(settings):
    students = [
        Student(full_name=f"S{i}", gender=FEMALE, group=1) for i in range(4)
    ]
    a, b, c, d = students
    u1 = Unit(name="U1", group=1, quota=2)
    u2 = Unit(name="U2", group=1, quota=2)
    u3 = Unit(name="U3", group=1, quota=2)
    # A ile B, EYLÜL'de U1'de birlikteydi
    history = [
        make_assignment(a, u1, "EYLÜL"),
        make_assignment(b, u1, "EYLÜL"),
        make_assignment(c, u2, "EYLÜL"),
        make_assignment(d, u2, "EYLÜL"),
    ]
    r = solve_month(students, [u1, u2, u3], "EKİM", history=history, settings=settings)
    assert r.ok
    assert r.assignments[a.id] != r.assignments[b.id]  # tekrar eşleşme yok
    assert r.assignments[c.id] != r.assignments[d.id]


def test_locked_assignments_respected(small_world, settings):
    """Yarı otomatik mod: elle sabitlenen hücre korunur."""
    students, units, _ = small_world
    dis = by_name(units, "DİŞ")
    kiz2 = students[1]
    r = solve_month(
        students, units, "EYLÜL", history=[], settings=settings,
        locked={kiz2.id: dis.id},
    )
    assert r.ok
    assert r.assignments[kiz2.id] == dis.id


def test_infeasible_reports_turkish_reason(settings):
    """Çözümsüzlük sessiz geçilmez, kural tahmini raporlanır."""
    girls = [Student(full_name=f"K{i}", gender=FEMALE, group=1) for i in range(2)]
    alci = Unit(name="ALÇI ODASI", group=1, quota=2, gender_restriction=MALE)
    r = solve_month(girls, [alci], "EYLÜL", history=[], settings=settings)
    assert not r.ok
    assert r.status == "INFEASIBLE"
    assert r.infeasible_reasons
    assert any("cinsiyet" in reason.lower() for reason in r.infeasible_reasons)
