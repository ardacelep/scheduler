"""Sabit atama aralığı ve "sabitlenen kazanır" önceliği.

Gerçek durum: "İKİ ÖĞRENCİ OCAK AYINA KADAR DİŞ'TE KALACAK". Bu, iki
yerleşik kuralla doğrudan çelişiyordu:

* madde 1 — aynı bölüme ikinci kez gidilmez (Eylül DİŞ → Ekim DİŞ yasak)
* madde 20 — peş peşe iki ay hafif bölüm olmaz (DİŞ hafif)

Kullanıcı her ay için ayrı sabit atama girdi; çözücü Ekim'i hiç üretemedi ve
sebep olarak alakasız kuralları (cinsiyet, FTR) saydı. Sezon çözücüsü ise
çatışan sabitlemeyi SESSİZCE yok sayıyordu.

İlke: sabitlenen hücre madde 1 ve madde 20'den muaftır; muafiyet yalnız o
hücreye aittir. Cinsiyet, kontenjan, yasak ve diş muafiyeti esnemez.
"""
import pytest

from rotasyon.models import (
    Assignment,
    CustomRule,
    DEFAULT_SETTINGS,
    INTENSITY_HAFIF,
    INTENSITY_YOGUN,
    RULE_SABIT_ATAMA,
    Student,
    Unit,
    pin_map,
    pinned_months,
)
from rotasyon.rules import ERROR, check_all
from rotasyon.solver import solve_month, solve_season

AYLAR = ["EYLÜL", "EKİM", "KASIM", "ARALIK", "OCAK", "ŞUBAT"]


def _ayar():
    import copy

    a = copy.deepcopy(DEFAULT_SETTINGS)
    a["months"] = AYLAR
    a["season_requirements"] = []
    a["solver"]["time_limit_seconds"] = 5
    a["solver"]["season_time_limit_seconds"] = 20
    a["solver"]["num_workers"] = 1
    return a


def S(ad, gender="K", group=1):
    return Student(full_name=ad, gender=gender, group=group, class_name="A")


def U(ad, quota=2, intensity="", gender="", group=1):
    return Unit(name=ad, group=group, quota=quota, intensity=intensity,
                gender_restriction=gender, pool=True)


def sabit(s, u, bas, bit=""):
    return CustomRule(type=RULE_SABIT_ATAMA, student_ids=[s.id],
                      unit_id=u.id, month=bas, end_month=bit)


def A(s, u, m):
    return Assignment(student_id=s.id, month=m, unit_id=u.id)


@pytest.fixture
def dunya():
    """DİŞ (hafif) + yeterince yoğun/hafif/nötr birim, üç öğrenci."""
    dis = U("DİŞ", quota=2, intensity=INTENSITY_HAFIF)
    birimler = [dis] + [
        U(f"YOĞUN{i}", quota=3, intensity=INTENSITY_YOGUN) for i in range(4)
    ] + [
        U(f"HAFİF{i}", quota=3, intensity=INTENSITY_HAFIF) for i in range(3)
    ] + [U(f"NÖTR{i}", quota=3) for i in range(4)]
    ogr = [S("KALAN BİR"), S("KALAN İKİ"), S("SERBEST")]
    return ogr, birimler, dis


# ---- aralık ----

def test_range_covers_every_month_inclusive():
    r = CustomRule(type=RULE_SABIT_ATAMA, month="EYLÜL", end_month="OCAK",
                   student_ids=["s"], unit_id="u")
    assert pinned_months(r, AYLAR) == ["EYLÜL", "EKİM", "KASIM", "ARALIK", "OCAK"]


def test_old_single_month_rules_still_work():
    r = CustomRule(type=RULE_SABIT_ATAMA, month="EKİM", student_ids=["s"], unit_id="u")
    assert pinned_months(r, AYLAR) == ["EKİM"]


def test_reversed_range_degrades_to_single_month():
    r = CustomRule(type=RULE_SABIT_ATAMA, month="KASIM", end_month="EKİM",
                   student_ids=["s"], unit_id="u")
    assert pinned_months(r, AYLAR) == ["KASIM"]


def test_inactive_rules_do_not_pin():
    r = CustomRule(type=RULE_SABIT_ATAMA, month="EKİM", student_ids=["s"],
                   unit_id="u", active=False)
    assert pin_map([r], AYLAR) == {}


# ---- çözücü: ay ay ----

def test_stay_is_produced_month_by_month(dunya):
    """Asıl vaka: Eylül DİŞ'teydi, Ocak'a kadar DİŞ'te kalsın."""
    ogr, birimler, dis = dunya
    kurallar = [sabit(ogr[0], dis, "EYLÜL", "OCAK"), sabit(ogr[1], dis, "EYLÜL", "OCAK")]
    gecmis = [A(ogr[0], dis, "EYLÜL"), A(ogr[1], dis, "EYLÜL"),
              A(ogr[2], birimler[1], "EYLÜL")]
    for ay in AYLAR[1:5]:
        r = solve_month(ogr, birimler, ay, gecmis, _ayar(), custom_rules=kurallar)
        assert r.ok, (ay, r.infeasible_reasons)
        assert r.assignments[ogr[0].id] == dis.id
        assert r.assignments[ogr[1].id] == dis.id
        gecmis += [Assignment(student_id=sid, month=ay, unit_id=uid)
                   for sid, uid in r.assignments.items()]
    # kalış bitti: Şubat'ta DİŞ'e dönülmez ve (Ocak hafif olduğu için) hafif verilmez
    r = solve_month(ogr, birimler, "ŞUBAT", gecmis, _ayar(), custom_rules=kurallar)
    assert r.ok, r.infeasible_reasons
    by_id = {u.id: u for u in birimler}
    for s in ogr[:2]:
        u = by_id[r.assignments[s.id]]
        assert u.name != "DİŞ"
        assert u.intensity != INTENSITY_HAFIF


def test_without_the_exemption_this_was_infeasible(dunya):
    """Karşıt kanıt: sabitleme olmadan aynı istek madde 1'e takılır.

    (Elle kilit = sabitleme değildir; kalıcı karar Özel Kurallar'dadır.)
    """
    ogr, birimler, dis = dunya
    gecmis = [A(ogr[0], dis, "EYLÜL")]
    r = solve_month(ogr, birimler, "EKİM", gecmis, _ayar(),
                    locked={ogr[0].id: dis.id})
    assert not r.ok


def test_free_month_before_a_pinned_hafif_month_is_not_hafif(dunya):
    """Kasım'da DİŞ'e sabitlenen öğrenciye Ekim'de hafif bölüm verilmez."""
    ogr, birimler, dis = dunya
    kurallar = [sabit(ogr[0], dis, "KASIM", "ARALIK")]
    gecmis = [A(ogr[0], birimler[1], "EYLÜL")]  # yoğun
    r = solve_month(ogr, birimler, "EKİM", gecmis, _ayar(), custom_rules=kurallar)
    assert r.ok, r.infeasible_reasons
    u = {u.id: u for u in birimler}[r.assignments[ogr[0].id]]
    assert u.intensity != INTENSITY_HAFIF
    assert u.name != "DİŞ"  # sabitlenen birim önceden de kullanılmaz


def test_pin_still_respects_gender_with_a_clear_reason():
    """Cinsiyet esnemez; sebep alakasız kural adları değil, açık cümle."""
    e = U("ALÇI", quota=1, gender="E")
    kiz = S("KIZ ÖĞRENCİ", gender="K")
    diger = [U("A", quota=3), U("B", quota=3)]
    r = solve_month([kiz], [e] + diger, "EKİM", [], _ayar(),
                    custom_rules=[sabit(kiz, e, "EKİM")])
    assert not r.ok
    assert any("KIZ ÖĞRENCİ" in x and "erkek" in x for x in r.infeasible_reasons)


def test_pins_over_quota_are_reported_by_name():
    tek = U("TEKLİ", quota=1)
    a, b = S("BİR"), S("İKİ")
    r = solve_month([a, b], [tek, U("X", quota=3)], "EKİM", [], _ayar(),
                    custom_rules=[sabit(a, tek, "EKİM"), sabit(b, tek, "EKİM")])
    assert not r.ok
    assert any("TEKLİ" in x and "kontenjanı 1" in x for x in r.infeasible_reasons)


def test_pin_to_inactive_unit_is_reported():
    kapali = U("KAPALI", quota=1)
    kapali.active = False
    s = S("BİR")
    r = solve_month([s], [kapali, U("X", quota=3)], "EKİM", [], _ayar(),
                    custom_rules=[sabit(s, kapali, "EKİM")])
    assert not r.ok
    assert any("pasif" in x for x in r.infeasible_reasons)


# ---- çözücü: bütün sezon ----

def test_season_solver_honours_the_stay(dunya):
    ogr, birimler, dis = dunya
    kurallar = [sabit(ogr[0], dis, "EYLÜL", "OCAK")]
    r = solve_season(ogr, birimler, AYLAR, AYLAR, [], _ayar(), custom_rules=kurallar)
    assert r.ok, r.infeasible_reasons
    for ay in AYLAR[:5]:
        assert r.assignments[(ogr[0].id, ay)] == dis.id
    assert r.assignments[(ogr[0].id, "ŞUBAT")] != dis.id


def test_season_solver_never_silently_drops_a_pin(dunya):
    """Eskiden: sabitlemenin değişkeni tekrar yasağıyla budanıyor, sabitleme
    `if ... in x` ile SESSİZCE atlanıyordu — çözüm "başarılı" dönüyordu."""
    ogr, birimler, dis = dunya
    gecmis = [A(ogr[0], dis, "EYLÜL")]
    kurallar = [sabit(ogr[0], dis, "EKİM", "KASIM")]
    r = solve_season(ogr, birimler, AYLAR, AYLAR[1:], gecmis, _ayar(),
                     custom_rules=kurallar)
    assert r.ok, r.infeasible_reasons
    assert r.assignments[(ogr[0].id, "EKİM")] == dis.id
    assert r.assignments[(ogr[0].id, "KASIM")] == dis.id


def test_season_solver_reports_an_impossible_pin():
    e = U("ALÇI", quota=1, gender="E")
    kiz = S("KIZ")
    r = solve_season([kiz], [e, U("A", 3), U("B", 3), U("C", 3)], AYLAR[:3],
                     AYLAR[:3], [], _ayar(), custom_rules=[sabit(kiz, e, "EKİM")])
    assert not r.ok
    assert any("KIZ" in x for x in r.infeasible_reasons)


# ---- denetleyici ----

def _hatalar(ogr, birimler, atamalar, kurallar):
    return [v for v in check_all(ogr, birimler, atamalar, AYLAR, kurallar)
            if v.severity == ERROR]


def test_checker_accepts_a_pinned_stay(dunya):
    ogr, birimler, dis = dunya
    atamalar = [A(ogr[0], dis, m) for m in AYLAR[:5]]
    kurallar = [sabit(ogr[0], dis, "EYLÜL", "OCAK")]
    assert not [v for v in _hatalar(ogr, birimler, atamalar, kurallar)
                if v.rule_no in (1, 20)]


def test_checker_accepts_stay_whose_first_month_was_not_pinned(dunya):
    """Eylül elle atanmış, sonradan Ekim–Ocak sabitlenmiş: tek kalış."""
    ogr, birimler, dis = dunya
    atamalar = [A(ogr[0], dis, m) for m in AYLAR[:5]]
    kurallar = [sabit(ogr[0], dis, "EKİM", "OCAK")]
    assert not [v for v in _hatalar(ogr, birimler, atamalar, kurallar)
                if v.rule_no == 1]


def test_checker_still_flags_the_same_stay_without_a_pin(dunya):
    """Karşıt kanıt: sabitleme yoksa aynı tablo iki kuralı da çiğner."""
    ogr, birimler, dis = dunya
    atamalar = [A(ogr[0], dis, m) for m in AYLAR[:3]]
    kurallar_no = {v.rule_no for v in _hatalar(ogr, birimler, atamalar, [])}
    assert {1, 20} <= kurallar_no


def test_checker_flags_returning_after_the_stay(dunya):
    """Kalış bittikten sonra DİŞ'e geri dönmek yine madde 1 ihlali."""
    ogr, birimler, dis = dunya
    atamalar = [A(ogr[0], dis, m) for m in AYLAR[:2]] + [
        A(ogr[0], birimler[1], "KASIM"), A(ogr[0], dis, "ARALIK")]
    kurallar = [sabit(ogr[0], dis, "EYLÜL", "EKİM")]
    ihlal = [v for v in _hatalar(ogr, birimler, atamalar, kurallar) if v.rule_no == 1]
    assert ihlal and ihlal[0].month == "ARALIK"


def test_checker_blames_the_free_month_after_a_stay(dunya):
    """Ocak DİŞ (sabit, hafif), Şubat hafif: değişmesi gereken Şubat."""
    ogr, birimler, dis = dunya
    hafif = next(u for u in birimler if u.name == "HAFİF0")
    atamalar = [A(ogr[0], dis, "OCAK"), A(ogr[0], hafif, "ŞUBAT")]
    kurallar = [sabit(ogr[0], dis, "OCAK")]
    ihlal = [v for v in _hatalar(ogr, birimler, atamalar, kurallar) if v.rule_no == 20]
    assert ihlal and ihlal[0].month == "ŞUBAT"


def test_checker_blames_the_free_month_before_a_stay(dunya):
    ogr, birimler, dis = dunya
    hafif = next(u for u in birimler if u.name == "HAFİF0")
    atamalar = [A(ogr[0], hafif, "EKİM"), A(ogr[0], dis, "KASIM")]
    kurallar = [sabit(ogr[0], dis, "KASIM")]
    ihlal = [v for v in _hatalar(ogr, birimler, atamalar, kurallar) if v.rule_no == 20]
    assert ihlal and ihlal[0].month == "EKİM"


def test_checker_reports_pin_not_followed_in_every_month_of_the_range(dunya):
    ogr, birimler, dis = dunya
    atamalar = [A(ogr[0], dis, "EYLÜL"), A(ogr[0], birimler[1], "EKİM")]
    kurallar = [sabit(ogr[0], dis, "EYLÜL", "EKİM")]
    ihlal = [v for v in _hatalar(ogr, birimler, atamalar, kurallar) if v.rule_no == -1]
    assert ihlal and ihlal[0].month == "EKİM"


def test_checker_reports_two_pins_on_the_same_cell(dunya):
    ogr, birimler, dis = dunya
    kurallar = [sabit(ogr[0], dis, "EKİM"), sabit(ogr[0], birimler[1], "EKİM")]
    ihlal = [v for v in _hatalar(ogr, birimler, [], kurallar)
             if "birden fazla sabit" in v.message]
    assert ihlal


def test_rule1_message_uses_season_order_not_alphabetical(dunya):
    """"EKİM" alfabede "EYLÜL"den önce gelir; ilk ay yanlış yazılıyordu."""
    ogr, birimler, dis = dunya
    atamalar = [A(ogr[0], dis, "EYLÜL"), A(ogr[0], dis, "EKİM")]
    ihlal = [v for v in _hatalar(ogr, birimler, atamalar, []) if v.rule_no == 1]
    assert ihlal[0].month == "EKİM"
    assert "(EYLÜL ve EKİM)" in ihlal[0].message


# ---- risk: kural eklerken ön uyarı ----

def test_preview_does_not_warn_about_the_stay_itself(dunya):
    from rotasyon.risk import fixed_assignment_conflicts

    ogr, birimler, dis = dunya
    kural = sabit(ogr[0], dis, "EKİM", "OCAK")
    sorun = fixed_assignment_conflicts(
        kural, {s.id: s for s in ogr}, {u.id: u for u in birimler},
        [A(ogr[0], dis, "EYLÜL")], [kural], AYLAR,
    )
    assert not sorun, sorun


def test_preview_warns_when_the_student_returns_to_the_unit(dunya):
    from rotasyon.risk import fixed_assignment_conflicts

    ogr, birimler, dis = dunya
    kural = sabit(ogr[0], dis, "KASIM")
    sorun = fixed_assignment_conflicts(
        kural, {s.id: s for s in ogr}, {u.id: u for u in birimler},
        [A(ogr[0], dis, "EYLÜL"), A(ogr[0], birimler[1], "EKİM")], [kural], AYLAR,
    )
    assert any("ayrı bir ziyaret" in x for x in sorun)


def test_preview_counts_quota_in_every_month_of_overlapping_ranges(dunya):
    from rotasyon.risk import fixed_assignment_conflicts

    ogr, birimler, dis = dunya  # DİŞ kontenjanı 2
    kurallar = [sabit(ogr[0], dis, "EYLÜL", "OCAK"),
                sabit(ogr[1], dis, "EKİM", "KASIM"),
                sabit(ogr[2], dis, "KASIM")]
    sorun = fixed_assignment_conflicts(
        kurallar[2], {s.id: s for s in ogr}, {u.id: u for u in birimler},
        [], kurallar, AYLAR,
    )
    assert any("KASIM" in x and "3 öğrenci" in x for x in sorun)
