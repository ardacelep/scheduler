"""Zaman kapsamlı (temporal) özel kurallar: birim yasağı + pencere."""
from rotasyon.models import (
    CustomRule,
    DEFAULT_MONTHS,
    RULE_AYRI_TUT,
    RULE_BIRIM_YASAK,
    rule_active_in_month,
)
from rotasyon.rules import ERROR, check_all
from rotasyon.solver import solve_month
from conftest import make_assignment


def by_name(units, name, gender=""):
    return next(
        u for u in units if u.name == name and u.gender_restriction == gender
    )


# ---------- pencere yardımcısı ----------

def test_rule_active_in_month_window():
    r = CustomRule(type=RULE_AYRI_TUT, start_month="KASIM", end_month="OCAK")
    assert not rule_active_in_month(r, "EYLÜL", DEFAULT_MONTHS)
    assert not rule_active_in_month(r, "EKİM", DEFAULT_MONTHS)
    assert rule_active_in_month(r, "KASIM", DEFAULT_MONTHS)
    assert rule_active_in_month(r, "OCAK", DEFAULT_MONTHS)
    assert not rule_active_in_month(r, "ŞUBAT", DEFAULT_MONTHS)


def test_rule_active_unbounded():
    r = CustomRule(type=RULE_AYRI_TUT)  # boş pencere = tüm sezon
    assert all(rule_active_in_month(r, m, DEFAULT_MONTHS) for m in DEFAULT_MONTHS)


# ---------- çözücü: birim yasağı ----------

def test_solver_respects_active_ban(small_world, settings):
    """Yasak penceresi içindeki ayda öğrenci o birime atanmaz."""
    students, units, _ = small_world
    dis = by_name(units, "DİŞ")
    s0 = students[0]
    rule = CustomRule(
        type=RULE_BIRIM_YASAK, student_ids=[s0.id], unit_id=dis.id,
        start_month="EYLÜL",
    )
    r = solve_month(
        students, units, "EYLÜL", history=[], settings=settings,
        custom_rules=[rule],
    )
    assert r.ok
    assert r.assignments[s0.id] != dis.id


def test_solver_ban_covers_gender_variants(small_world, settings):
    """Yasak ada göre işler: FTR.ÜNİT k/e çiftinin ikisi de yasaklanır."""
    students, units, _ = small_world
    ftr_k = by_name(units, "FTR.ÜNİT", "K")
    ftr_e = by_name(units, "FTR.ÜNİT", "E")
    s0 = students[0]  # kız
    rule = CustomRule(
        type=RULE_BIRIM_YASAK, student_ids=[s0.id], unit_id=ftr_k.id,
    )
    r = solve_month(
        students, units, "EYLÜL", history=[], settings=settings,
        custom_rules=[rule],
    )
    assert r.ok
    assert r.assignments[s0.id] not in (ftr_k.id, ftr_e.id)


# ---------- denetleyici: pencere kapsamı ----------

def test_checker_ban_flags_within_window(small_world):
    students, units, _ = small_world
    dis = by_name(units, "DİŞ")
    s0 = students[0]
    rule = CustomRule(
        type=RULE_BIRIM_YASAK, student_ids=[s0.id], unit_id=dis.id,
        start_month="EKİM",
    )
    # EKİM penceresi içinde → ihlal
    v = check_all(
        students, units, [make_assignment(s0, dis, "EKİM")],
        DEFAULT_MONTHS, custom_rules=[rule],
    )
    assert any(x.rule_no == -1 for x in v)


def test_checker_ban_ignores_before_window(small_world):
    """Pencere öncesi (tamamlanmış geçmiş) ay geriye dönük ihlal sayılmaz."""
    students, units, _ = small_world
    dis = by_name(units, "DİŞ")
    s0 = students[0]
    rule = CustomRule(
        type=RULE_BIRIM_YASAK, student_ids=[s0.id], unit_id=dis.id,
        start_month="EKİM",
    )
    v = check_all(
        students, units, [make_assignment(s0, dis, "EYLÜL")],
        DEFAULT_MONTHS, custom_rules=[rule],
    )
    assert not any(x.rule_no == -1 for x in v)


def test_checker_ayri_tut_window_scoped(small_world):
    """Sezon ortasında eklenen 'ayrı tut' geçmiş ayı ihlal saymaz."""
    students, units, _ = small_world
    cerr = by_name(units, "1.KAT CERR.")  # quota 2
    s1, s2 = students[0], students[1]
    rule = CustomRule(
        type=RULE_AYRI_TUT, student_ids=[s1.id, s2.id], start_month="KASIM",
    )
    # EYLÜL'de birlikteler ama kural KASIM'dan geçerli → ihlal yok
    before = check_all(
        students, units,
        [make_assignment(s1, cerr, "EYLÜL"), make_assignment(s2, cerr, "EYLÜL")],
        DEFAULT_MONTHS, custom_rules=[rule],
    )
    assert not any(x.rule_no == -1 for x in before)
    # KASIM'da birlikteler → ihlal
    after = check_all(
        students, units,
        [make_assignment(s1, cerr, "KASIM"), make_assignment(s2, cerr, "KASIM")],
        DEFAULT_MONTHS, custom_rules=[rule],
    )
    assert any(x.rule_no == -1 for x in after)


# ---------- round-trip: solver ileri-uyum + denetleyici pencere kapsamı ----------

def _full_eylul(students, units):
    """s0,s1 BİRLİKTE (1.KAT CERR.) olacak şekilde geçerli, tam bir EYLÜL."""
    cerr = by_name(units, "1.KAT CERR.")
    ftr_k = by_name(units, "FTR.ÜNİT", "K")
    ftr_e = by_name(units, "FTR.ÜNİT", "E")
    dah = by_name(units, "4.KAT DAH.")
    yb = by_name(units, "YB/A")
    dis = by_name(units, "DİŞ")
    dog = by_name(units, "DOĞ.SAL-Y.DOĞ")
    s = students
    return [
        make_assignment(s[0], cerr, "EYLÜL"), make_assignment(s[1], cerr, "EYLÜL"),
        make_assignment(s[2], ftr_k, "EYLÜL"), make_assignment(s[3], dah, "EYLÜL"),
        make_assignment(s[4], ftr_e, "EYLÜL"), make_assignment(s[5], yb, "EYLÜL"),
        make_assignment(s[6], dis, "EYLÜL"), make_assignment(s[7], dog, "EYLÜL"),
    ]


def test_midseason_rule_solver_output_passes_checker(small_world, settings):
    """Sezon ortasında eklenen 'ayrı tut' (KASIM'dan) round-trip tutarlılığı:
    solver KASIM'ı kurala UYARAK çözer, aynı kuralla çalışan denetleyici
    hem KASIM'ı temiz bulur hem de PENCERE ÖNCESİ (EYLÜL, birlikteyken)
    geriye dönük ihlal ÜRETMEZ. Yani solver ↔ check_all akış boyunca aynı
    zaman penceresinde anlaşır."""
    settings["season_requirements"] = []
    students, units, _ = small_world
    s0, s1 = students[0], students[1]
    history = _full_eylul(students, units)  # s0,s1 EYLÜL'de birlikte
    rule = CustomRule(
        type=RULE_AYRI_TUT, student_ids=[s0.id, s1.id], start_month="KASIM",
    )

    # Pencere öncesi EYLÜL, birliktelerken bile ihlal değil
    assert not any(
        x.rule_no == -1
        for x in check_all(students, units, history, DEFAULT_MONTHS, [rule])
    )

    # EKİM'i çöz (kural henüz pasif) → geçmiş büyür
    r_ekim = solve_month(
        students, units, "EKİM", history=history, settings=settings,
        custom_rules=[rule],
    )
    assert r_ekim.ok, r_ekim.infeasible_reasons
    history += [
        make_assignment(
            next(s for s in students if s.id == sid),
            next(u for u in units if u.id == uid), "EKİM",
        )
        for sid, uid in r_ekim.assignments.items()
    ]

    # KASIM'ı çöz (kural aktif) → solver s0,s1'i AYIRIR
    r_kasim = solve_month(
        students, units, "KASIM", history=history, settings=settings,
        custom_rules=[rule],
    )
    assert r_kasim.ok, r_kasim.infeasible_reasons
    assert r_kasim.assignments[s0.id] != r_kasim.assignments[s1.id]

    # Tüm sezon (EYLÜL+EKİM+KASIM) aynı kuralla denetlenir → sıfır ERROR,
    # sıfır özel-kural (-1) ihlali
    full = history + [
        make_assignment(
            next(s for s in students if s.id == sid),
            next(u for u in units if u.id == uid), "KASIM",
        )
        for sid, uid in r_kasim.assignments.items()
    ]
    v = check_all(students, units, full, DEFAULT_MONTHS, [rule], settings=settings)
    assert [x for x in v if x.severity == ERROR] == [], [
        x.message for x in v if x.severity == ERROR
    ]
    assert not any(x.rule_no == -1 for x in v)
