"""Gereksinimden tek tek öğrenci hariç tutma ("tüm öğrenciler, X ve Y hariç").

Gerçek durum: iki öğrenci sonradan doğan bir ihtiyaç yüzünden sezon sonuna
kadar belirli birimlere sabitlendi. "Sabitlenen kazanır" onları oraya koyuyor
ama "tüm öğrenciler yoğun bakım görmeli" gereksinimi artık karşılanamıyor ve
ay üretilemiyor. Tek çıkış kapsamı "Seçili öğrenciler"e çevirip kalan 58
kişiyi tek tek seçmekti.
"""
import copy

from rotasyon.models import (
    Assignment,
    CustomRule,
    DEFAULT_SETTINGS,
    RULE_SABIT_ATAMA,
    Requirement,
    SCOPE_ALL,
    SCOPE_GROUP,
    SCOPE_STUDENTS,
    Student,
    Unit,
)
from rotasyon.normalize import normalize_key
from rotasyon.requirements import applies_to, describe
from rotasyon.rules import ERROR, check_all
from rotasyon.solver import solve_month

AYLAR = ["EYLÜL", "EKİM", "KASIM", "ARALIK"]


def _ayar():
    a = copy.deepcopy(DEFAULT_SETTINGS)
    a["months"] = AYLAR
    a["season_requirements"] = []
    a["solver"]["time_limit_seconds"] = 5
    a["solver"]["num_workers"] = 1
    return a


def S(ad, group=1):
    return Student(full_name=ad, gender="K", group=group, class_name="A")


def U(ad, quota=3):
    return Unit(name=ad, group=1, quota=quota, pool=True)


def yb_gereksinimi(**kw):
    return Requirement(name="Yoğun bakım", scope=SCOPE_ALL,
                       unit_keys=[normalize_key("YB")], **kw)


# ---- kapsam ----

def test_excluded_student_is_not_covered():
    a, b = S("BİR"), S("İKİ")
    req = yb_gereksinimi(excluded_ids=[a.id])
    assert not applies_to(req, a)
    assert applies_to(req, b)


def test_exclusion_works_with_group_scope():
    a, b, c = S("BİR"), S("İKİ"), S("ÜÇ", group=2)
    req = Requirement(name="x", scope=SCOPE_GROUP, scope_value="1",
                      excluded_ids=[a.id])
    assert [applies_to(req, s) for s in (a, b, c)] == [False, True, False]


def test_old_files_without_the_field_still_load():
    d = yb_gereksinimi().to_dict()
    d.pop("excluded_ids")
    assert Requirement.from_dict(d).excluded_ids == []


def test_describe_mentions_the_exclusions():
    req = yb_gereksinimi(excluded_ids=["x", "y"])
    assert "Tüm öğrenciler (2 öğrenci hariç)" in describe(req)
    assert "hariç" not in describe(yb_gereksinimi())


def test_describe_ignores_exclusions_on_explicit_student_lists():
    req = Requirement(name="x", scope=SCOPE_STUDENTS, student_ids=["a"],
                      excluded_ids=["b"])
    assert "hariç" not in describe(req)


# ---- çözücü + denetleyici: asıl vaka ----

def _vaka():
    """BİR, KASIM–ARALIK DİŞ'e sabit; EYLÜL/EKİM'de YB görmedi."""
    yb, dis = U("YB"), U("DİŞ")
    digerleri = [U(f"N{i}") for i in range(4)]
    birimler = [yb, dis] + digerleri
    bir, iki = S("BİR"), S("İKİ")
    gecmis = [
        Assignment(student_id=bir.id, month="EYLÜL", unit_id=digerleri[0].id),
        Assignment(student_id=bir.id, month="EKİM", unit_id=digerleri[1].id),
        Assignment(student_id=iki.id, month="EYLÜL", unit_id=digerleri[2].id),
        Assignment(student_id=iki.id, month="EKİM", unit_id=digerleri[3].id),
    ]
    sabit = CustomRule(type=RULE_SABIT_ATAMA, student_ids=[bir.id],
                       unit_id=dis.id, month="KASIM", end_month="ARALIK")
    return [bir, iki], birimler, gecmis, [sabit], yb, dis


def test_pinned_student_makes_the_month_infeasible_and_says_how_to_fix():
    ogr, birimler, gecmis, kurallar, _, _ = _vaka()
    r = solve_month(ogr, birimler, "KASIM", gecmis, _ayar(),
                    custom_rules=kurallar, requirements=[yb_gereksinimi()])
    assert not r.ok
    assert any("BİR" in x and "hariç tutun" in x for x in r.infeasible_reasons)


def test_excluding_the_pinned_student_unblocks_the_month():
    ogr, birimler, gecmis, kurallar, yb, dis = _vaka()
    req = yb_gereksinimi(excluded_ids=[ogr[0].id])
    r = solve_month(ogr, birimler, "KASIM", gecmis, _ayar(),
                    custom_rules=kurallar, requirements=[req])
    assert r.ok, r.infeasible_reasons
    assert r.assignments[ogr[0].id] == dis.id
    # Diğer öğrenci için gereksinim hâlâ geçerli: son iki ayın birinde YB
    gecmis += [Assignment(student_id=sid, month="KASIM", unit_id=uid)
               for sid, uid in r.assignments.items()]
    r2 = solve_month(ogr, birimler, "ARALIK", gecmis, _ayar(),
                     custom_rules=kurallar, requirements=[req])
    assert r2.ok, r2.infeasible_reasons
    gordu = {a.unit_id for a in gecmis if a.student_id == ogr[1].id}
    gordu.add(r2.assignments[ogr[1].id])
    assert yb.id in gordu


def test_checker_does_not_flag_the_excluded_student():
    ogr, birimler, gecmis, kurallar, yb, dis = _vaka()
    bir, iki = ogr
    atamalar = gecmis + [
        Assignment(student_id=bir.id, month="KASIM", unit_id=dis.id),
        Assignment(student_id=bir.id, month="ARALIK", unit_id=dis.id),
        Assignment(student_id=iki.id, month="KASIM", unit_id=yb.id),
        Assignment(student_id=iki.id, month="ARALIK", unit_id=birimler[2].id),
    ]

    def hatalar(req):
        return [v for v in check_all(ogr, birimler, atamalar, AYLAR, kurallar,
                                     requirements=[req])
                if v.severity == ERROR and "Yoğun bakım" in v.message]

    assert any("BİR" in v.message for v in hatalar(yb_gereksinimi()))
    assert hatalar(yb_gereksinimi(excluded_ids=[bir.id])) == []
