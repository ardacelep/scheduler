"""Sezon zorunluluklarının İLERİYE DÖNÜK denetimi.

Kural denetleyicisi (rule 6/7) zorunlu branşları ancak dönemin son ayı
atandığında ihlal sayar — yani iş işten geçtiğinde. Buradaki denetim aynı
riski her ay önden hesaplar: "bu öğrenci palyatif görmeden sezon kapanacak".
"""
import pytest

from rotasyon.capacity import ERROR, WARNING, season_requirement_findings
from rotasyon.models import (
    Assignment,
    BRANCH_CERRAHI,
    BRANCH_DAHILI,
    BRANCH_DOGUM_SALONU,
    BRANCH_PALYATIF,
    PROGRAM_EBELIK,
    Student,
    Unit,
)

MONTHS = ["EYLÜL", "EKİM", "KASIM", "ARALIK"]
SETTINGS = {
    "season_requirements": [
        {"branch": BRANCH_CERRAHI},
        {"branch": BRANCH_DAHILI},
        {"branch": BRANCH_PALYATIF},
    ]
}


def units():
    return [
        Unit(id="cer", name="CERRAHİ", quota=5, group=1,
             branch_category=BRANCH_CERRAHI),
        Unit(id="dah", name="DAHİLİ", quota=5, group=1,
             branch_category=BRANCH_DAHILI),
        Unit(id="pal", name="PALYATİF", quota=5, group=1,
             branch_category=BRANCH_PALYATIF),
        Unit(id="dig", name="EVRAK", quota=5, group=1),
    ]


def student(**kw):
    base = dict(id="s1", full_name="Deneme Kişi", gender="K", group=1)
    base.update(kw)
    return Student(**base)


def levels(findings):
    return [f.level for f in findings]


def test_no_finding_when_requirements_reachable():
    """Sezon başı: 4 ay var, 3 zorunluluk eksik — bol pay, uyarı çıkmamalı."""
    f = season_requirement_findings(
        [student()], units(), MONTHS, [], SETTINGS
    )
    assert f == []


def test_error_when_months_run_out():
    """3 ay 'EVRAK'ta geçmiş; 1 ay kaldı ama 3 zorunluluk eksik → imkânsız."""
    s = student()
    assignments = [
        Assignment(student_id="s1", month=m, unit_id="dig")
        for m in MONTHS[:3]
    ]
    f = season_requirement_findings([s], units(), MONTHS, assignments, SETTINGS)
    assert ERROR in levels(f)
    msg = " ".join(x.message for x in f)
    assert "Deneme Kişi" in msg and "karşılanamaz" in msg


def test_warning_when_exactly_enough_months():
    """1 ay geçmiş, 3 ay kaldı, 3 zorunluluk eksik → sıfır pay uyarısı."""
    s = student()
    assignments = [Assignment(student_id="s1", month="EYLÜL", unit_id="dig")]
    f = season_requirement_findings([s], units(), MONTHS, assignments, SETTINGS)
    assert levels(f) == [WARNING]
    assert "hiç pay yok" in f[0].message


def test_no_finding_when_all_requirements_already_met():
    s = student()
    assignments = [
        Assignment(student_id="s1", month="EYLÜL", unit_id="cer"),
        Assignment(student_id="s1", month="EKİM", unit_id="dah"),
        Assignment(student_id="s1", month="KASIM", unit_id="pal"),
    ]
    f = season_requirement_findings([s], units(), MONTHS, assignments, SETTINGS)
    assert f == []


def test_error_when_branch_has_no_reachable_unit():
    """Tek palyatif birimi ERKEK kısıtlı → kız öğrenci oraya asla gidemez."""
    us = units()
    for u in us:
        if u.id == "pal":
            u.gender_restriction = "E"
    f = season_requirement_findings(
        [student(gender="K")], us, MONTHS, [], SETTINGS
    )
    assert ERROR in levels(f)
    assert "Palyatif" in " ".join(x.message for x in f)


def test_error_when_only_unit_already_visited():
    """Tek dahili birimine zaten gitmiş; tekrar yasağı yüzünden ulaşılamaz."""
    s = student()
    assignments = [Assignment(student_id="s1", month="EYLÜL", unit_id="dah")]
    us = [u for u in units()]
    f = season_requirement_findings([s], us, MONTHS, assignments, SETTINGS)
    # dahili görüldü; cerrahi+palyatif kaldı, 3 ay var → sorun yok
    assert f == []
    # ama cerrahiyi de görüp tek palyatifi yasaklarsak ulaşılamaz olur
    s2 = student(id="s2", full_name="İkinci Kişi", banned_unit_ids=["pal"])
    f2 = season_requirement_findings([s2], us, MONTHS, [], SETTINGS)
    assert ERROR in levels(f2)


def test_ebelik_student_needs_dogum_salonu():
    """Ebelik öğrencisi için doğum salonu ayarlardan bağımsız zorunludur."""
    us = units() + [
        Unit(id="dog", name="DOĞUM SALONU", quota=3, group=1,
             branch_category=BRANCH_DOGUM_SALONU)
    ]
    s = student(program=PROGRAM_EBELIK)
    # 4 zorunluluk (3 + doğum salonu), yalnız 2 ay kaldı → imkânsız
    assignments = [
        Assignment(student_id="s1", month=m, unit_id="dig")
        for m in MONTHS[:2]
    ]
    f = season_requirement_findings([s], us, MONTHS, assignments, SETTINGS)
    assert ERROR in levels(f)


def test_inactive_students_are_ignored():
    """Ayrılan öğrenci yeni aya atanmaz; onun için uyarı üretilmemeli."""
    s = student(active=False)
    assignments = [
        Assignment(student_id="s1", month=m, unit_id="dig")
        for m in MONTHS[:3]
    ]
    f = season_requirement_findings([s], units(), MONTHS, assignments, SETTINGS)
    assert f == []


def test_requirement_ignored_when_no_such_unit_exists():
    """O branşta hiç birim tanımlı değilse zorunluluk uygulanmaz."""
    us = [u for u in units() if u.id != "pal"]
    f = season_requirement_findings([student()], us, MONTHS, [], SETTINGS)
    assert f == []


def test_multiple_students_are_grouped_into_one_message():
    """64 kişilik sezonda her öğrenci için ayrı satır basılmamalı."""
    students = [
        student(id=f"s{i}", full_name=f"Öğrenci {i}") for i in range(10)
    ]
    assignments = [
        Assignment(student_id=s.id, month=m, unit_id="dig")
        for s in students
        for m in MONTHS[:3]
    ]
    f = season_requirement_findings(
        students, units(), MONTHS, assignments, SETTINGS
    )
    assert len(f) == 1  # tek toplu mesaj
    assert "10 öğrencinin" in f[0].message
    assert "ve 4 kişi daha" in f[0].message  # ad listesi kısaltıldı
