"""Sezon ortası dinamik değişiklik senaryoları.

Öğrenci ayrılması/katılması, birim kontenjan değişikliği gibi değişiklikler
İLERİYE dönük uygulanır: geçmiş aylar sabit kalır, referanslar kopmaz.
"""
from rotasyon.models import Assignment, DEFAULT_MONTHS, Student, Unit, FEMALE
from rotasyon.planner import plan_remaining
from rotasyon.rules import ERROR, check_all
from rotasyon.solver import solve_month
from conftest import make_assignment


def by_name(units, name, gender=""):
    return next(
        u for u in units if u.name == name and u.gender_restriction == gender
    )


def test_inactive_student_not_planned(small_world, settings):
    """Ayrılan öğrenci sonraki aylara atanmaz; diğerleri planlanır."""
    students, units, _ = small_world
    settings["months"] = ["EYLÜL", "EKİM"]
    settings["season_requirements"] = []
    leaver = students[0]
    leaver.active = False
    new, solved, failed = plan_remaining(
        students, units, settings["months"], [], settings=settings
    )
    assert failed == {}
    assert not any(a.student_id == leaver.id for a in new)
    # kalan 7 öğrencinin ikişer ayı üretildi
    assert len(new) == 7 * 2


def test_inactive_student_history_still_resolves(small_world):
    """Pasif öğrencinin geçmiş atamaları denetleyicide sahipsiz kalmaz
    (rule 0 'silinmiş öğrenci' hatası üretmez) ve sezon sonu zorunlulukları
    ondan istenmez."""
    students, units, _ = small_world
    dis = by_name(units, "DİŞ")
    leaver = students[0]
    assignments = [make_assignment(leaver, dis, "EYLÜL")]
    leaver.active = False
    v = check_all(students, units, assignments, DEFAULT_MONTHS)
    assert not any(x.rule_no == 0 for x in v)
    assert not any(x.rule_no in (6, 7) for x in v)


def test_new_student_joins_mid_season(small_world, settings):
    """Sezon ortasında katılan öğrenci sonraki aydan itibaren planlanır;
    geçmiş aylar (onsuz) geçerli kalır."""
    students, units, _ = small_world
    settings["months"] = ["EYLÜL", "EKİM"]
    settings["season_requirements"] = []
    r = solve_month(students, units, "EYLÜL", history=[], settings=settings)
    assert r.ok
    eylul = [
        Assignment(student_id=sid, month="EYLÜL", unit_id=uid)
        for sid, uid in r.assignments.items()
    ]
    yeni = Student(full_name="Yeni Gelen", gender=FEMALE, group=1)
    # kontenjan payı: yeni öğrenci için havuz büyüt
    cerr = by_name(units, "1.KAT CERR.")
    cerr.quota += 1
    new, solved, failed = plan_remaining(
        students + [yeni], units, settings["months"], eylul, settings=settings
    )
    assert failed == {}
    ekim = [a for a in new if a.month == "EKİM"]
    assert any(a.student_id == yeni.id for a in ekim)
    # EYLÜL yeniden üretilmedi
    assert {a.month for a in new} == {"EKİM"}


def test_quota_change_applies_forward(small_world, settings):
    """Kontenjan değişikliği sonraki ay çözümüne otomatik yansır."""
    students, units, _ = small_world
    settings["season_requirements"] = []
    cerr = by_name(units, "1.KAT CERR.")  # quota 2
    r1 = solve_month(students, units, "EYLÜL", history=[], settings=settings)
    assert r1.ok
    occupants = [sid for sid, uid in r1.assignments.items() if uid == cerr.id]
    assert len(occupants) <= 2
    history = [
        Assignment(student_id=sid, month="EYLÜL", unit_id=uid)
        for sid, uid in r1.assignments.items()
    ]
    # dinamik değişiklik: kontenjan 2 → 3 (başka birimden pay alarak)
    cerr.quota = 3
    by_name(units, "4.KAT DAH.").quota = 0
    r2 = solve_month(students, units, "EKİM", history=history, settings=settings)
    assert r2.ok
    occ2 = [sid for sid, uid in r2.assignments.items() if uid == cerr.id]
    assert len(occ2) == 3  # yeni kontenjan kullanılıyor (toplam = öğrenci sayısı)
    all_v = check_all(
        students, units, history + [
            Assignment(student_id=sid, month="EKİM", unit_id=uid)
            for sid, uid in r2.assignments.items()
        ], DEFAULT_MONTHS, settings=settings,
    )
    errors = [v for v in all_v if v.severity == ERROR]
    assert errors == [], [e.message for e in errors]
    # kontenjanı sonradan sıfırlanan birimin TAMAMLANMIŞ EYLÜL ayı hata
    # değil, açıklamalı uyarı olarak raporlanır (geçmiş yeniden yazılmaz)
    softened = [
        v for v in all_v
        if v.rule_no == 12 and v.month == "EYLÜL"
    ]
    assert softened and "Tamamlanmış ay" in softened[0].message


def test_deactivated_unit_keeps_history(small_world, settings):
    """Birim pasifleştirilince yeni ay ona atamaz ama geçmiş korunur ve
    madde 1 (tekrar yasağı) geçmişi hâlâ tanır."""
    students, units, _ = small_world
    settings["season_requirements"] = []
    dis = by_name(units, "DİŞ")
    s0 = students[0]
    history = [make_assignment(s0, dis, "EYLÜL")]
    dis.active = False
    # havuza pay aç ki toplam kontenjan yetsin
    by_name(units, "1.KAT CERR.").quota += 1
    r = solve_month(students, units, "EKİM", history=history, settings=settings)
    assert r.ok
    assert all(uid != dis.id for uid in r.assignments.values())