"""Gereksinim derleme katmanı (rotasyon.requirements) — saf mantık.

Kullanıcının cümlesi ("şu öğrenciler şu birimlerden şu kadarını görsün")
çözücünün anlayacağı somut birim id listesine doğru çevriliyor mu?
"""
from rotasyon.models import (
    PROGRAM_EBELIK,
    PROGRAM_HEMSIRELIK,
    Requirement,
    SCOPE_ALL,
    SCOPE_CLASS,
    SCOPE_GROUP,
    SCOPE_PROGRAM,
    SCOPE_STUDENTS,
    Student,
    Unit,
    BRANCH_DAHILI,
    BRANCH_DOGUM_SALONU,
    BRANCH_YOGUN_BAKIM,
)
from rotasyon.requirements import (
    applies_to,
    compile_for_student,
    describe,
    from_legacy_settings,
    met_count,
    unmet_count,
)


def U(name, group=1, active=True, branch=BRANCH_DAHILI):
    return Unit(name=name, group=group, active=active, branch_category=branch)


def S(name="Ali", group=1, class_name="A", program=PROGRAM_HEMSIRELIK, active=True):
    return Student(
        full_name=name, gender="K", group=group, class_name=class_name,
        program=program, active=active,
    )


def R(**kw):
    kw.setdefault("name", "Test")
    return Requirement(**kw)


# ---- applies_to: kapsam ----

def test_scope_all_covers_everyone():
    assert applies_to(R(scope=SCOPE_ALL), S(group=2, class_name="D"))


def test_scope_group_matches_only_that_group():
    req = R(scope=SCOPE_GROUP, scope_value="1")
    assert applies_to(req, S(group=1))
    assert not applies_to(req, S(group=2))


def test_scope_group_compares_as_string():
    # scope_value JSON'dan string gelir, Student.group int'tir
    assert applies_to(R(scope=SCOPE_GROUP, scope_value="2"), S(group=2))


def test_scope_class_is_case_and_space_insensitive():
    req = R(scope=SCOPE_CLASS, scope_value="d")
    assert applies_to(req, S(class_name="D"))
    assert not applies_to(req, S(class_name="C"))


def test_scope_program_matches_program():
    req = R(scope=SCOPE_PROGRAM, scope_value=PROGRAM_EBELIK)
    assert applies_to(req, S(program=PROGRAM_EBELIK))
    assert not applies_to(req, S(program=PROGRAM_HEMSIRELIK))


def test_scope_students_matches_listed_ids():
    s1, s2 = S("Ali"), S("Veli")
    req = R(scope=SCOPE_STUDENTS, student_ids=[s1.id])
    assert applies_to(req, s1)
    assert not applies_to(req, s2)


def test_inactive_requirement_covers_nobody():
    assert not applies_to(R(scope=SCOPE_ALL, active=False), S())


def test_inactive_student_is_not_covered():
    # sezon ortasında ayrılan öğrenciden sezon sonu zorunluluğu beklenmez
    assert not applies_to(R(scope=SCOPE_ALL), S(active=False))


# ---- compile_for_student: birim eşleştirme ----

def test_compiles_to_own_group_units_only():
    u1, u2 = U("YB/B", group=1), U("YB/B", group=2)
    req = R(unit_keys=["YB/B"])
    assert compile_for_student(req, S(group=1), [u1, u2]) == [u1.id]
    assert compile_for_student(req, S(group=2), [u1, u2]) == [u2.id]


def test_group_zero_unit_available_to_both_groups():
    shared = U("ACİL", group=0)
    req = R(unit_keys=["ACİL"])
    assert compile_for_student(req, S(group=1), [shared]) == [shared.id]
    assert compile_for_student(req, S(group=2), [shared]) == [shared.id]


def test_inactive_unit_is_excluded():
    live, dead = U("YB/B"), U("YB/C", active=False)
    req = R(unit_keys=["YB/B", "YB/C"])
    assert compile_for_student(req, S(), [live, dead]) == [live.id]


def test_matching_ignores_spacing_and_trailing_dots():
    # normalize_key: "ECZ . SARF" == "ECZ.SARF", sondaki nokta atılır
    u = U("ECZ . SARF.")
    assert compile_for_student(R(unit_keys=["ecz.sarf"]), S(), [u]) == [u.id]


def test_empty_unit_keys_compiles_to_nothing():
    assert compile_for_student(R(unit_keys=[]), S(), [U("YB/B")]) == []


def test_unknown_unit_name_compiles_to_nothing():
    assert compile_for_student(R(unit_keys=["YOK BÖYLE"]), S(), [U("YB/B")]) == []


# ---- met_count / unmet_count: geçmiş düşümü ----

def test_unmet_counts_remaining_visits():
    req = R(unit_keys=["YB/B", "YB/C", "YB/D"], min_count=1)
    assert unmet_count(req, []) == 1
    assert unmet_count(req, ["YB/C"]) == 0


def test_min_count_three_requires_all_three():
    req = R(unit_keys=["YB/B", "YB/C", "YB/D"], min_count=3)
    assert unmet_count(req, []) == 3
    assert unmet_count(req, ["YB/B"]) == 2
    assert unmet_count(req, ["YB/B", "YB/C", "YB/D"]) == 0


def test_visits_outside_the_list_do_not_count():
    req = R(unit_keys=["YB/B"], min_count=1)
    assert unmet_count(req, ["1.KAT CERR"]) == 1


def test_met_count_is_name_normalized():
    req = R(unit_keys=["ECZ.SARF"], min_count=1)
    assert met_count(req, ["ecz . sarf"]) == 1


def test_unmet_is_not_capped_by_available_units():
    # 3 ziyaret istenip listede 2 birim varsa bu bir veri hatasıdır ve
    # sessizce 2'ye düşürülmez — çözücü "karşılanamıyor" diyebilmeli
    req = R(unit_keys=["YB/B", "YB/C"], min_count=3)
    assert unmet_count(req, []) == 3


# ---- from_legacy_settings: v1'den aktarım ----

def _legacy_units():
    return [
        U("4.KAT DAH", group=g, branch=BRANCH_DAHILI) for g in (1, 2)
    ] + [
        U("YB/B", group=g, branch=BRANCH_YOGUN_BAKIM) for g in (1, 2)
    ] + [
        U("DOĞ.SAL", group=g, branch=BRANCH_DOGUM_SALONU) for g in (1, 2)
    ]


def test_legacy_branch_becomes_all_scope_requirement():
    settings = {"season_requirements": [{"branch": BRANCH_DAHILI}]}
    reqs = from_legacy_settings(settings, _legacy_units())
    dahili = [r for r in reqs if r.unit_keys == ["4.KAT DAH"]]
    assert len(dahili) == 1
    assert dahili[0].scope == SCOPE_ALL
    assert dahili[0].min_count == 1


def test_legacy_branch_without_units_is_skipped():
    # v1 davranışı: o branştan birim yoksa zorunluluk uygulanmaz.
    # (Doğum birimi katalogda olduğu için ebelik satırı ayrıca üretilir.)
    settings = {"season_requirements": [{"branch": "palyatif"}]}
    reqs = from_legacy_settings(settings, _legacy_units())
    assert not any("Palyatif" in r.name for r in reqs)
    assert [r.name for r in reqs] == ["Ebelik → doğum salonu"]


def test_legacy_emits_visible_ebelik_dogum_requirement():
    reqs = from_legacy_settings({"season_requirements": []}, _legacy_units())
    assert len(reqs) == 1
    ebelik = reqs[0]
    assert ebelik.scope == SCOPE_PROGRAM
    assert ebelik.scope_value == PROGRAM_EBELIK
    assert ebelik.unit_keys == ["DOĞ.SAL"]


def test_legacy_ebelik_rule_skipped_when_no_dogum_unit():
    units = [U("4.KAT DAH", group=1, branch=BRANCH_DAHILI)]
    assert from_legacy_settings({"season_requirements": []}, units) == []


def test_legacy_dedupes_unit_names_across_groups():
    # aynı ad grup-1 ve grup-2 satırı olarak iki kez var; anahtar tek olmalı
    settings = {"season_requirements": [{"branch": BRANCH_YOGUN_BAKIM}]}
    reqs = from_legacy_settings(settings, _legacy_units())
    yb = [r for r in reqs if "YB/B" in r.unit_keys][0]
    assert yb.unit_keys == ["YB/B"]


def test_legacy_ignores_inactive_units():
    units = [U("YB/B", group=1, active=False, branch=BRANCH_YOGUN_BAKIM)]
    settings = {"season_requirements": [{"branch": BRANCH_YOGUN_BAKIM}]}
    assert from_legacy_settings(settings, units) == []


# ---- describe: okunur özet ----

def test_describe_reads_like_a_sentence():
    req = R(scope=SCOPE_PROGRAM, scope_value=PROGRAM_EBELIK,
            unit_keys=["DOĞ.SAL", "2.KAT DOĞUM"], min_count=1)
    text = describe(req)
    assert "Ebe Yardımcılığı" in text
    assert "DOĞ.SAL" in text
    assert "en az 1" in text
    assert "zorunlu" in text


# ---- min_visits_needed: kesişen gereksinimler ----

def test_disjoint_requirements_add_up():
    """Hiç kesişmeyen borçlar ayrı ayrı ay ister."""
    from rotasyon.requirements import min_visits_needed
    assert min_visits_needed([({"A"}, 1), ({"B"}, 1), ({"C"}, 1)]) == 3


def test_subset_requirement_does_not_add_a_month():
    """YB ⊂ yoğun bölüm: bir YB ziyareti ikisini de kapatır.

    Toplama (1+1=2) gereken ay sayısını şişirir ve "yetişmez" diye yanlış
    çözümsüzlük üretirdi.
    """
    from rotasyon.requirements import min_visits_needed
    yogun = {"5.KAT", "YB/B", "YB/C"}
    yb = {"YB/B", "YB/C"}
    assert min_visits_needed([(yogun, 1), (yb, 1)]) == 1


def test_partial_overlap_does_not_add_a_month():
    from rotasyon.requirements import min_visits_needed
    assert min_visits_needed([({"A", "B"}, 1), ({"B", "C"}, 1)]) == 1


def test_real_default_set_needs_four_months_not_five():
    """Varsayılan beş gereksinim 4 ayda karşılanabilir (kesişimler sayesinde).

    Cerrahi ∩ Yoğun bölüm = 6.KAT CERR · Yoğun bakım ⊂ Yoğun bölüm ·
    Palyatif ⊂ Yoğun bölüm → ayrık en fazla dört küme seçilebilir.
    """
    from rotasyon.catalog import load_default_requirements
    from rotasyon.normalize import normalize_key
    from rotasyon.requirements import min_visits_needed

    reqs = [r for r in load_default_requirements() if r.scope == SCOPE_ALL]
    assert len(reqs) == 5, "varsayılan evrensel gereksinim sayısı değişti"
    items = [
        ({normalize_key(k) for k in r.unit_keys}, r.min_count) for r in reqs
    ]
    assert min_visits_needed(items) == 4


def test_min_count_is_respected_for_disjoint_sets():
    from rotasyon.requirements import min_visits_needed
    assert min_visits_needed([({"A", "B"}, 2), ({"C"}, 1)]) == 3


def test_empty_and_zero_items_ignored():
    from rotasyon.requirements import min_visits_needed
    assert min_visits_needed([]) == 0
    assert min_visits_needed([(set(), 3), ({"A"}, 0)]) == 0


def test_lower_bound_never_exceeds_naive_sum():
    """Alt sınır her zaman ≤ toplam olmalı — asla şişirmemeli."""
    from rotasyon.requirements import min_visits_needed
    ornekler = [
        [({"A"}, 1), ({"A"}, 1), ({"A"}, 1)],
        [({"A", "B"}, 2), ({"B", "C"}, 1), ({"D"}, 3)],
        [({"X"}, 5)],
    ]
    for items in ornekler:
        assert min_visits_needed(items) <= sum(n for _s, n in items)
