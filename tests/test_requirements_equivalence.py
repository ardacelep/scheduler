"""v1 ≡ v2 denkliği — bu aşamanın çekirdek kanıtı.

v2 gereksinim modeli, v1'in branş bazlı zorunluluklarını AYNEN ifade
edebilmeli: `from_legacy_settings` ile aktarılan bir sezon, çözücüde ve
denetleyicide v1 ile aynı sonucu vermeli. Aksi halde "aynı motor, farklı
ifade" iddiası boştur.

Ayrıca kullanıcının el tablosundaki iki cümle doğrudan test edilir:
"YB/B, YB/C, YB/D'den birini görmeli" ve "ebelik → doğum salonu".
"""
from rotasyon.models import (
    Assignment,
    PROGRAM_EBELIK,
    PROGRAM_HEMSIRELIK,
    Requirement,
    SCOPE_ALL,
    SCOPE_CLASS,
    SCOPE_PROGRAM,
    SEVERITY_PREFERRED,
    Student,
    Unit,
    BRANCH_CERRAHI,
    BRANCH_DAHILI,
    BRANCH_DIGER,
    BRANCH_DOGUM_SALONU,
    BRANCH_YOGUN_BAKIM,
)
from rotasyon.requirements import from_legacy_settings
from rotasyon.rules import WARNING, blocking_errors, check_all
from rotasyon.solver import solve_season

MONTHS = ["EYLÜL", "EKİM", "KASIM", "ARALIK"]

SETTINGS = {
    "months": MONTHS,
    "season_requirements": [
        {"branch": BRANCH_DAHILI},
        {"branch": BRANCH_CERRAHI},
        {"branch": BRANCH_YOGUN_BAKIM},
    ],
    "solver": {
        "time_limit_seconds": 5,
        "season_time_limit_seconds": 20,
        "num_workers": 1,
        "weights": {
            "pool_balance": 5, "repeat_pair": 10, "ebelik_priority": 20,
            "core_branch_early": 2, "single_slot_fill": 50, "reserve_use": 15,
            "gender_balance": 6, "intensive_surplus": 2,
        },
    },
}


def _units():
    """Tek grup, 4 ay için yeterli birim: her zorunlu branştan biri + dolgu."""
    spec = [
        ("4.KAT DAH", BRANCH_DAHILI, 2),
        ("1.KAT CERR", BRANCH_CERRAHI, 2),
        ("YB/B", BRANCH_YOGUN_BAKIM, 1),
        ("YB/C", BRANCH_YOGUN_BAKIM, 1),
        ("YB/D", BRANCH_YOGUN_BAKIM, 1),
        ("DOĞ.SAL", BRANCH_DOGUM_SALONU, 2),
        ("EKG", BRANCH_DIGER, 2),
        ("DİYALİZ", BRANCH_DIGER, 2),
    ]
    return [
        Unit(name=n, group=1, quota=q, branch_category=b)
        for n, b, q in spec
    ]


def _students():
    return [
        Student(full_name="Ayşe", gender="K", group=1, class_name="D",
                program=PROGRAM_EBELIK),
        Student(full_name="Fatma", gender="K", group=1, class_name="A",
                program=PROGRAM_HEMSIRELIK),
        Student(full_name="Mehmet", gender="E", group=1, class_name="A",
                program=PROGRAM_HEMSIRELIK),
    ]


def _branches_seen(result, students, units):
    """(öğrenci adı) -> gittiği birimlerin branşları."""
    by_id = {u.id: u for u in units}
    names = {s.id: s.full_name for s in students}
    seen: dict[str, set[str]] = {s.full_name: set() for s in students}
    for (sid, _m), uid in result.assignments.items():
        seen[names[sid]].add(by_id[uid].branch_category)
    return seen


def _unit_names_seen(result, students, units):
    by_id = {u.id: u for u in units}
    names = {s.id: s.full_name for s in students}
    seen: dict[str, set[str]] = {s.full_name: set() for s in students}
    for (sid, _m), uid in result.assignments.items():
        seen[names[sid]].add(by_id[uid].name)
    return seen


# ---- Çözücü denkliği ----

def test_legacy_and_compiled_requirements_both_solve():
    units, students = _units(), _students()
    reqs = from_legacy_settings(SETTINGS, units)

    v1 = solve_season(students, units, MONTHS, MONTHS, [], SETTINGS,
                      random_seed=7)
    v2 = solve_season(students, units, MONTHS, MONTHS, [], SETTINGS,
                      random_seed=7, requirements=reqs)

    assert v1.status in ("OPTIMAL", "FEASIBLE"), v1.infeasible_reasons
    assert v2.status in ("OPTIMAL", "FEASIBLE"), v2.infeasible_reasons


def test_compiled_requirements_enforce_same_branches_as_v1():
    """Her öğrenci v2 yolunda da dahili+cerrahi+YB görmeli; ebelik ayrıca doğum."""
    units, students = _units(), _students()
    reqs = from_legacy_settings(SETTINGS, units)
    res = solve_season(students, units, MONTHS, MONTHS, [], SETTINGS,
                       random_seed=7, requirements=reqs)
    assert res.status in ("OPTIMAL", "FEASIBLE"), res.infeasible_reasons

    seen = _branches_seen(res, students, units)
    for name in ("Ayşe", "Fatma", "Mehmet"):
        assert BRANCH_DAHILI in seen[name], name
        assert BRANCH_CERRAHI in seen[name], name
        assert BRANCH_YOGUN_BAKIM in seen[name], name
    # madde 7: yalnız ebelik öğrencisi doğum salonu görmek zorunda
    assert BRANCH_DOGUM_SALONU in seen["Ayşe"]


def test_v1_and_v2_agree_on_infeasibility():
    """Zorunluluk karşılanamıyorsa iki yol da çözümsüz demeli."""
    # Yoğun bakım birimi hiç yok ama zorunluluk listesinde duruyor:
    # v1 "branştan birim yoksa atla" der → çözülür. v2 aktarımı da o
    # zorunluluğu hiç üretmez → aynı sonuç.
    units = [u for u in _units() if u.branch_category != BRANCH_YOGUN_BAKIM]
    students = _students()
    reqs = from_legacy_settings(SETTINGS, units)

    v1 = solve_season(students, units, MONTHS, MONTHS, [], SETTINGS,
                      random_seed=3)
    v2 = solve_season(students, units, MONTHS, MONTHS, [], SETTINGS,
                      random_seed=3, requirements=reqs)
    assert v1.status == v2.status
    assert not any("Yoğun Bakım" in r.name for r in reqs)


# ---- Kullanıcının el tablosundaki cümleler ----

def test_yogun_bakim_one_of_three_is_satisfied():
    """"YB/B, YB/C, YB/D'den birini görmeli" — branşsız, doğrudan birim adıyla."""
    units, students = _units(), _students()
    req = Requirement(
        name="Yoğun bakım",
        scope=SCOPE_ALL,
        unit_keys=["YB/B", "YB/C", "YB/D"],
        min_count=1,
    )
    res = solve_season(students, units, MONTHS, MONTHS, [], SETTINGS,
                       random_seed=11, requirements=[req])
    assert res.status in ("OPTIMAL", "FEASIBLE"), res.infeasible_reasons
    seen = _unit_names_seen(res, students, units)
    for name in seen:
        assert seen[name] & {"YB/B", "YB/C", "YB/D"}, f"{name}: YB görmemiş"


def test_class_scoped_requirement_hits_only_that_class():
    """"D sınıfı doğum birimlerini görmeli" — sınıf bazlı kapsam."""
    units, students = _units(), _students()
    req = Requirement(
        name="D sınıfı doğum",
        scope=SCOPE_CLASS,
        scope_value="D",
        unit_keys=["DOĞ.SAL"],
        min_count=1,
    )
    res = solve_season(students, units, MONTHS, MONTHS, [], SETTINGS,
                       random_seed=5, requirements=[req])
    assert res.status in ("OPTIMAL", "FEASIBLE"), res.infeasible_reasons
    seen = _unit_names_seen(res, students, units)
    assert "DOĞ.SAL" in seen["Ayşe"]  # D sınıfı — zorunlu


def test_program_scoped_requirement_replaces_hardcoded_rule():
    """Ebelik → doğum artık koda gömülü değil, normal bir gereksinim satırı."""
    units, students = _units(), _students()
    req = Requirement(
        name="Ebelik doğum",
        scope=SCOPE_PROGRAM,
        scope_value=PROGRAM_EBELIK,
        unit_keys=["DOĞ.SAL"],
    )
    res = solve_season(students, units, MONTHS, MONTHS, [], SETTINGS,
                       random_seed=5, requirements=[req])
    assert res.status in ("OPTIMAL", "FEASIBLE"), res.infeasible_reasons
    assert "DOĞ.SAL" in _unit_names_seen(res, students, units)["Ayşe"]


def test_min_count_three_forces_all_three_units():
    units, students = _units(), _students()
    req = Requirement(
        name="Üç yoğun bakım",
        scope=SCOPE_ALL,
        unit_keys=["YB/B", "YB/C", "YB/D"],
        min_count=3,
    )
    # 3 öğrenci × 3 YB ziyareti = 9 ziyaret ama YB kontenjanı ayda 3,
    # 4 ayda 12 → sığar
    res = solve_season(students, units, MONTHS, MONTHS, [], SETTINGS,
                       random_seed=13, requirements=[req])
    assert res.status in ("OPTIMAL", "FEASIBLE"), res.infeasible_reasons
    seen = _unit_names_seen(res, students, units)
    for name in seen:
        assert {"YB/B", "YB/C", "YB/D"} <= seen[name], f"{name}: {seen[name]}"


def test_impossible_requirement_reports_clear_reason():
    """Listede 2 birim varken 3 ziyaret istenirse sessizce kırpılmaz."""
    units, students = _units(), _students()
    req = Requirement(
        name="İmkânsız", scope=SCOPE_ALL,
        unit_keys=["YB/B", "YB/C"], min_count=3,
    )
    res = solve_season(students, units, MONTHS, MONTHS, [], SETTINGS,
                       requirements=[req])
    assert res.status == "INFEASIBLE"
    assert any("İmkânsız" in r for r in res.infeasible_reasons)


# ---- Denetleyici denkliği ----

def _full_season_assignments(students, units):
    """Her öğrenciye 4 ay atama: zorunlulukları KARŞILAYAN bir tablo."""
    by_name = {u.name: u for u in units}
    plan = {
        "Ayşe": ["4.KAT DAH", "1.KAT CERR", "YB/B", "DOĞ.SAL"],
        "Fatma": ["1.KAT CERR", "4.KAT DAH", "YB/C", "EKG"],
        "Mehmet": ["YB/D", "4.KAT DAH", "1.KAT CERR", "DİYALİZ"],
    }
    out = []
    for s in students:
        for month, unit_name in zip(MONTHS, plan[s.full_name]):
            out.append(
                Assignment(student_id=s.id, month=month,
                           unit_id=by_name[unit_name].id)
            )
    return out


def test_checker_agrees_when_requirements_are_met():
    units, students = _units(), _students()
    reqs = from_legacy_settings(SETTINGS, units)
    asg = _full_season_assignments(students, units)

    v1 = check_all(students, units, asg, MONTHS, settings=SETTINGS)
    v2 = check_all(students, units, asg, MONTHS, settings=SETTINGS,
                   requirements=reqs)
    # ikisi de sezon zorunluluğu ihlali görmemeli
    assert [x for x in v1 if x.rule_no in (6, 7)] == []
    assert [x for x in v2 if x.rule_no in (6, 7)] == []


def test_checker_reports_requirement_by_its_own_name():
    units, students = _units(), _students()
    asg = _full_season_assignments(students, units)
    req = Requirement(
        name="Palyatif deneyimi", scope=SCOPE_ALL, unit_keys=["EKG"],
    )
    found = [
        v for v in check_all(students, units, asg, MONTHS, settings=SETTINGS,
                             requirements=[req])
        if v.rule_no == 6
    ]
    # yalnız EKG'ye gitmeyenler raporlanır, mesajda gereksinimin ADI geçer
    adlar = {students[i].full_name for i in (0, 2)}  # Ayşe, Mehmet
    assert {v.student_id for v in found} == {
        s.id for s in students if s.full_name in adlar
    }
    assert all("Palyatif deneyimi" in v.message for v in found)


def test_checker_silent_before_season_ends():
    """Son ay atanmadıysa zorunluluk ihlali raporlanmaz (dönem bitmemiş)."""
    units, students = _units(), _students()
    asg = [
        a for a in _full_season_assignments(students, units)
        if a.month != MONTHS[-1]
    ]
    req = Requirement(name="Hiç karşılanmayan", scope=SCOPE_ALL,
                      unit_keys=["DOĞ.SAL"])
    found = [
        v for v in check_all(students, units, asg, MONTHS, settings=SETTINGS,
                             requirements=[req])
        if v.rule_no == 6
    ]
    assert found == []


# ---- "Tercih" (yumuşak) gereksinimler ----

def test_preference_never_makes_season_infeasible():
    """Tercih karşılanamasa bile sezon çözülebilmeli — zorunlu DEĞİL."""
    units, students = _units(), _students()
    imkansiz = Requirement(
        name="Tercih ama imkânsız", scope=SCOPE_ALL,
        unit_keys=["YB/B", "YB/C"], min_count=3, severity=SEVERITY_PREFERRED,
    )
    res = solve_season(students, units, MONTHS, MONTHS, [], SETTINGS,
                       random_seed=4, requirements=[imkansiz])
    assert res.status in ("OPTIMAL", "FEASIBLE"), res.infeasible_reasons


def test_same_requirement_as_required_is_infeasible():
    """Aynı gereksinim ZORUNLU olsaydı çözümsüz olurdu — fark budur."""
    units, students = _units(), _students()
    zorunlu = Requirement(
        name="Zorunlu ve imkânsız", scope=SCOPE_ALL,
        unit_keys=["YB/B", "YB/C"], min_count=3,
    )
    res = solve_season(students, units, MONTHS, MONTHS, [], SETTINGS,
                       requirements=[zorunlu])
    assert res.status == "INFEASIBLE"


def test_preference_is_still_pursued_when_possible():
    """Tercih zorunlu değil ama karşılanabiliyorsa çözücü onu seçmeli."""
    units, students = _units(), _students()
    tercih = Requirement(
        name="DİYALİZ tercihi", scope=SCOPE_ALL, unit_keys=["DİYALİZ"],
        severity=SEVERITY_PREFERRED,
    )
    res = solve_season(students, units, MONTHS, MONTHS, [], SETTINGS,
                       random_seed=21, requirements=[tercih])
    assert res.status in ("OPTIMAL", "FEASIBLE"), res.infeasible_reasons
    seen = _unit_names_seen(res, students, units)
    # 4 ay, 3 öğrenci, DİYALİZ kontenjanı 2 → herkese yetecek yer var
    assert all("DİYALİZ" in v for v in seen.values()), seen


def test_unmet_preference_is_warning_not_error():
    """Denetleyici tercihi UYARI sayar; kaydı engellemez."""
    units, students = _units(), _students()
    asg = _full_season_assignments(students, units)
    tercih = Requirement(
        name="Karşılanmayan tercih", scope=SCOPE_ALL,
        unit_keys=["DOĞ.SAL"], severity=SEVERITY_PREFERRED,
    )
    found = [
        v for v in check_all(students, units, asg, MONTHS, settings=SETTINGS,
                             requirements=[tercih])
        if v.rule_no == 6
    ]
    assert found, "tercih karşılanmadığında rapor edilmeli"
    assert all(v.severity == WARNING for v in found)
    # kaydı engellememeli
    assert blocking_errors(found) == []


def test_checker_skips_requirement_with_no_matching_unit():
    """Hastanede o birim hiç yoksa kullanıcı boş yere uyarılmaz."""
    units, students = _units(), _students()
    asg = _full_season_assignments(students, units)
    req = Requirement(name="Olmayan birim", scope=SCOPE_ALL,
                      unit_keys=["HİPERBARİK"])
    found = [
        v for v in check_all(students, units, asg, MONTHS, settings=SETTINGS,
                             requirements=[req])
        if v.rule_no == 6
    ]
    assert found == []


# ---- Gereksinimler + kullanıcı kuralları birlikte ----

def test_requirements_and_custom_rules_work_together():
    """'Ayrı tut' gibi kullanıcı kuralları gereksinimlerle birlikte geçerli.

    Gereksinim ve özel kural AYRI kavramlardır; biri diğerinin yerine geçmez.
    """
    from rotasyon.models import CustomRule, RULE_AYRI_TUT

    units, students = _units(), _students()
    ayse, fatma = students[0], students[1]
    kural = CustomRule(type=RULE_AYRI_TUT,
                       student_ids=[ayse.id, fatma.id])
    reqs = from_legacy_settings(SETTINGS, units)

    res = solve_season(students, units, MONTHS, MONTHS, [], SETTINGS,
                       custom_rules=[kural], random_seed=9, requirements=reqs)
    assert res.status in ("OPTIMAL", "FEASIBLE"), res.infeasible_reasons

    # ayrı tut: hiçbir ay aynı birimde olmamalılar
    for m in MONTHS:
        assert res.assignments[(ayse.id, m)] != res.assignments[(fatma.id, m)], m

    # gereksinimler yine de karşılanmış olmalı
    seen = _branches_seen(res, students, units)
    for name in ("Ayşe", "Fatma", "Mehmet"):
        assert BRANCH_YOGUN_BAKIM in seen[name], name
    assert BRANCH_DOGUM_SALONU in seen["Ayşe"]
