"""Sezon planlayıcı (toplu oluşturma) testleri."""
from rotasyon.planner import plan_remaining, remaining_months
from rotasyon.rules import ERROR, check_all
from conftest import make_assignment


def test_remaining_months_fresh_and_mid(small_world):
    students, units, _ = small_world
    ids = {s.id for s in students}
    months = ["EYLÜL", "EKİM", "KASIM"]
    assert remaining_months(months, [], ids) == months
    done = [make_assignment(students[0], units[0], "EYLÜL")]
    assert remaining_months(months, done, ids) == ["EKİM", "KASIM"]


def test_plan_full_from_scratch(small_world, settings):
    """Sezon başı: üç ay tek seferde, sırayla ve kurallara uygun üretilir."""
    students, units, _ = small_world
    settings["months"] = ["EYLÜL", "EKİM", "KASIM"]
    settings["solver"]["time_limit_seconds"] = 5
    # küçük dünya 3 ayda 4 branş zorunluluğunu taşıyamaz; test sıralamayı ölçer
    settings["season_requirements"] = []
    new, solved, failed = plan_remaining(
        students, units, settings["months"], [], settings=settings
    )
    assert failed == {}
    assert solved[1] == ["EYLÜL", "EKİM", "KASIM"]
    assert len(new) == len(students) * 3
    errors = [
        v
        for v in check_all(
            students, units, new, settings["months"], settings=settings
        )
        if v.severity == ERROR
    ]
    assert errors == [], [e.message for e in errors]


def test_plan_continues_mid_season(small_world, settings):
    """Sezon ortası: dolu ay geçmiş kabul edilir, kalan aylar üretilir ve
    kimse önceki birimine geri dönmez (madde 1)."""
    from rotasyon.solver import solve_month
    from rotasyon.models import Assignment

    students, units, _ = small_world
    settings["months"] = ["EYLÜL", "EKİM"]
    settings["solver"]["time_limit_seconds"] = 5
    settings["season_requirements"] = []  # sıralama testi; zorunluluklar ayrı test edilir
    r = solve_month(students, units, "EYLÜL", history=[], settings=settings)
    assert r.ok
    eylul = [
        Assignment(student_id=sid, month="EYLÜL", unit_id=uid)
        for sid, uid in r.assignments.items()
    ]
    new, solved, failed = plan_remaining(
        students, units, settings["months"], eylul, settings=settings
    )
    assert failed == {}
    assert solved[1] == ["EKİM"]  # EYLÜL yeniden üretilmez
    assert {a.month for a in new} == {"EKİM"}
    by_student_eylul = {a.student_id: a.unit_id for a in eylul}
    for a in new:
        assert a.unit_id != by_student_eylul[a.student_id]


def test_plan_reports_failure_and_keeps_earlier_months(small_world, settings):
    """Kurallar bir noktada tıkanınca önceki aylar korunur, neden raporlanır.

    small_world'de 7 farklı birim adı var (FTR k/e aynı ad); madde 1 gereği
    10 ay sürdürülemez — bir ayda başarısızlık kaçınılmazdır.
    """
    students, units, _ = small_world
    settings["solver"]["time_limit_seconds"] = 5
    attempts = []
    new, solved, failed = plan_remaining(
        students, units, settings["months"], [], settings=settings,
        on_month=lambda g, m, a: attempts.append(a),
    )
    assert 1 in failed
    fail_month, reasons = failed[1]
    assert reasons  # Türkçe neden üretilir
    assert solved[1]  # başarısızlıktan önceki aylar üretilmiş durumda
    assert {a.month for a in new} == set(solved[1])
    # Tıkanmada farklı tohumla bir kez daha denenir; ikinci deneme de aynı
    # ayda aynı nedenle durunca (yapısal çözümsüzlük) üçüncüsü açılmaz.
    assert max(attempts) == 2
