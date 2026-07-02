"""Kural ihlali denetleyicisi.

Mevcut atama tablosunu (elle düzenlenmiş olabilir) 19 kurala karşı denetler
ve Türkçe ihlal listesi döner. Solver'dan bağımsızdır: hem otomatik üretim
sonrası doğrulamada hem manuel düzenleme uyarılarında kullanılır.

Sert kurallar "hata", dengeleme/öncelik kuralları (4, 18, 19) "uyarı"
düzeyinde raporlanır.
"""
from __future__ import annotations

import itertools
from collections import defaultdict
from dataclasses import dataclass

from .models import (
    Assignment,
    Student,
    Unit,
    CORE_BRANCHES,
    BRANCH_DOGUM_SALONU,
    GENDER_LABELS,
    PROGRAM_EBELIK,
)
from .normalize import normalize_key

ERROR = "hata"
WARNING = "uyarı"


@dataclass
class Violation:
    rule_no: int
    severity: str  # ERROR | WARNING
    message: str
    student_id: str = ""
    month: str = ""
    unit_id: str = ""


def check_all(
    students: list[Student],
    units: list[Unit],
    assignments: list[Assignment],
    months: list[str],
) -> list[Violation]:
    """Tüm denetimleri çalıştırır; ihlal yoksa boş liste döner."""
    v: list[Violation] = []
    students_by_id = {s.id: s for s in students}
    units_by_id = {u.id: u for u in units}

    # Bilinmeyen referanslar (bozuk veri) — kural dışı ama sessiz geçilmez
    valid = []
    for a in assignments:
        if a.student_id not in students_by_id or a.unit_id not in units_by_id:
            v.append(
                Violation(
                    rule_no=0,
                    severity=ERROR,
                    message="Atama, silinmiş bir öğrenci veya birime işaret ediyor.",
                    student_id=a.student_id,
                    month=a.month,
                    unit_id=a.unit_id,
                )
            )
        else:
            valid.append(a)

    # Aynı öğrenci aynı ay iki atama
    seen: dict[tuple[str, str], Assignment] = {}
    for a in valid:
        key = (a.student_id, a.month)
        if key in seen:
            s = students_by_id[a.student_id]
            v.append(
                Violation(
                    rule_no=0,
                    severity=ERROR,
                    message=f"{s.full_name}: {a.month} ayında birden fazla birime atanmış.",
                    student_id=a.student_id,
                    month=a.month,
                )
            )
        seen[key] = a

    v += _check_rule1_no_repeat(valid, students_by_id, units_by_id)
    v += _check_rule23_gender(valid, students_by_id, units_by_id)
    v += _check_rule5_group(valid, students_by_id, units_by_id)
    v += _check_rule67_deadlines(valid, students_by_id, units_by_id, months)
    v += _check_rule8_banned(valid, students_by_id, units_by_id)
    v += _check_rule9_dis(valid, students_by_id, units_by_id)
    v += _check_rule12_quota(valid, students_by_id, units_by_id)
    v += _check_rule17_must_fill(valid, students_by_id, units_by_id)
    v += _check_rule18_ebelik_priority(valid, students_by_id, units_by_id, months)
    v += _check_rule19_repeat_pairs(valid, students_by_id, units_by_id)
    return v


def _check_rule1_no_repeat(assignments, students_by_id, units_by_id):
    """Madde 1: aynı bölüme (ad bazında) ikinci kez gitmek yasak."""
    out = []
    by_student: dict[str, list] = defaultdict(list)
    for a in assignments:
        by_student[a.student_id].append(a)
    for sid, items in by_student.items():
        seen: dict[str, str] = {}  # normalize ad -> ilk ay
        for a in sorted(items, key=lambda a: a.month):
            key = normalize_key(units_by_id[a.unit_id].name)
            if key in seen:
                s = students_by_id[sid]
                out.append(
                    Violation(
                        rule_no=1,
                        severity=ERROR,
                        message=(
                            f"{s.full_name}, {units_by_id[a.unit_id].name} birimine "
                            f"ikinci kez atanmış ({seen[key]} ve {a.month})."
                        ),
                        student_id=sid,
                        month=a.month,
                        unit_id=a.unit_id,
                    )
                )
            else:
                seen[key] = a.month
    return out


def _check_rule23_gender(assignments, students_by_id, units_by_id):
    """Madde 2/3: cinsiyet kısıtlı birimlere yalnız uygun cinsiyet."""
    out = []
    for a in assignments:
        u = units_by_id[a.unit_id]
        s = students_by_id[a.student_id]
        if u.gender_restriction and s.gender and s.gender != u.gender_restriction:
            out.append(
                Violation(
                    rule_no=2 if u.gender_restriction == "K" else 3,
                    severity=ERROR,
                    message=(
                        f"{u.name} birimi yalnız "
                        f"{GENDER_LABELS[u.gender_restriction].lower()} öğrenci alır; "
                        f"{s.full_name} ({GENDER_LABELS.get(s.gender, '?')}) atanamaz "
                        f"({a.month})."
                    ),
                    student_id=s.id,
                    month=a.month,
                    unit_id=u.id,
                )
            )
    return out


def _check_rule5_group(assignments, students_by_id, units_by_id):
    """Madde 5: gruplar bağımsız — öğrenci başka grubun birimine atanamaz."""
    out = []
    for a in assignments:
        u = units_by_id[a.unit_id]
        s = students_by_id[a.student_id]
        if u.group not in (0, s.group):
            out.append(
                Violation(
                    rule_no=5,
                    severity=ERROR,
                    message=(
                        f"{s.full_name} ({s.group}. grup) başka grubun birimine "
                        f"atanmış: {u.name} ({u.group}. grup, {a.month})."
                    ),
                    student_id=s.id,
                    month=a.month,
                    unit_id=u.id,
                )
            )
    return out


def _check_rule67_deadlines(assignments, students_by_id, units_by_id, months):
    """Madde 6/7: dönem sonuna kadar zorunlu kategori ziyaretleri.

    İhlal ancak dönemin son ayı da atandığı halde zorunluluk karşılanmadıysa
    "hata"; dönem bitmemişse rapor üretilmez (solver erken aylarda bonusla
    yönlendirir).
    """
    out = []
    if not months:
        return out
    last_month = months[-1]
    by_student: dict[str, list] = defaultdict(list)
    for a in assignments:
        by_student[a.student_id].append(a)
    for sid, items in by_student.items():
        s = students_by_id[sid]
        if not any(a.month == last_month for a in items):
            continue  # dönem henüz tamamlanmamış
        cats = {units_by_id[a.unit_id].branch_category for a in items}
        if not cats & set(CORE_BRANCHES):
            out.append(
                Violation(
                    rule_no=6,
                    severity=ERROR,
                    message=(
                        f"{s.full_name} dönem boyunca dahili/cerrahi/yoğun bakım/"
                        f"palyatif kategorilerinden hiçbirini görmemiş."
                    ),
                    student_id=sid,
                )
            )
        if s.program == PROGRAM_EBELIK and BRANCH_DOGUM_SALONU not in cats:
            out.append(
                Violation(
                    rule_no=7,
                    severity=ERROR,
                    message=(
                        f"{s.full_name} (ebelik) dönem boyunca doğum salonu "
                        f"görmemiş."
                    ),
                    student_id=sid,
                )
            )
    return out


def _check_rule8_banned(assignments, students_by_id, units_by_id):
    out = []
    for a in assignments:
        s = students_by_id[a.student_id]
        if a.unit_id in s.banned_unit_ids:
            out.append(
                Violation(
                    rule_no=8,
                    severity=ERROR,
                    message=(
                        f"{s.full_name}, yasaklı olduğu birime atanmış: "
                        f"{units_by_id[a.unit_id].name} ({a.month})."
                    ),
                    student_id=s.id,
                    month=a.month,
                    unit_id=a.unit_id,
                )
            )
    return out


def _check_rule9_dis(assignments, students_by_id, units_by_id):
    out = []
    for a in assignments:
        s = students_by_id[a.student_id]
        u = units_by_id[a.unit_id]
        if s.dis_exempt and "DİŞ" in normalize_key(u.name):
            out.append(
                Violation(
                    rule_no=9,
                    severity=ERROR,
                    message=(
                        f"{s.full_name} Diş Poliklinik muafiyetine rağmen "
                        f"{u.name} birimine atanmış ({a.month})."
                    ),
                    student_id=s.id,
                    month=a.month,
                    unit_id=u.id,
                )
            )
    return out


def _check_rule12_quota(assignments, students_by_id, units_by_id):
    """Madde 12: aylık kontenjan aşımı."""
    out = []
    occupancy: dict[tuple[str, str], int] = defaultdict(int)
    for a in assignments:
        occupancy[(a.month, a.unit_id)] += 1
    for (month, uid), count in occupancy.items():
        u = units_by_id[uid]
        if count > u.quota:
            out.append(
                Violation(
                    rule_no=12,
                    severity=ERROR,
                    message=(
                        f"{u.name} biriminin {month} kontenjanı aşılmış "
                        f"({count}/{u.quota})."
                    ),
                    month=month,
                    unit_id=uid,
                )
            )
    return out


def _check_rule17_must_fill(assignments, students_by_id, units_by_id):
    """Madde 17: FTR k/e çifti gibi zorunlu dolan birimler her ay tam dolmalı.

    Yalnız o grup için atama yapılmış aylar denetlenir.
    """
    out = []
    months_with_assignments: dict[int, set[str]] = defaultdict(set)
    for a in assignments:
        s = students_by_id[a.student_id]
        months_with_assignments[s.group].add(a.month)
    occupancy: dict[tuple[str, str], int] = defaultdict(int)
    for a in assignments:
        occupancy[(a.month, a.unit_id)] += 1
    for u in units_by_id.values():
        if not (u.must_fill and u.active and u.quota > 0):
            continue
        for month in months_with_assignments.get(u.group, set()):
            count = occupancy.get((month, u.id), 0)
            if count != u.quota:
                out.append(
                    Violation(
                        rule_no=17,
                        severity=ERROR,
                        message=(
                            f"{u.name} ({GENDER_LABELS.get(u.gender_restriction, '?')}) "
                            f"biriminin {month} kontenjanı tam dolmalı "
                            f"({count}/{u.quota}) — FTR'ye her ay 1 kız 1 erkek kuralı."
                        ),
                        month=month,
                        unit_id=u.id,
                    )
                )
    return out


def _check_rule18_ebelik_priority(assignments, students_by_id, units_by_id, months):
    """Madde 18: öncelikli birimde ebelik-dışı öğrenci varken o ay boşta
    (o birimi henüz görmemiş) ebelik öğrencisi kalmışsa uyarı."""
    out = []
    ebelik_ids = {
        sid for sid, s in students_by_id.items() if s.program == PROGRAM_EBELIK
    }
    if not ebelik_ids:
        return out
    by_month: dict[str, list] = defaultdict(list)
    for a in assignments:
        by_month[a.month].append(a)
    for month, items in by_month.items():
        for a in items:
            u = units_by_id[a.unit_id]
            s = students_by_id[a.student_id]
            if not u.ebelik_priority or s.id in ebelik_ids:
                continue
            # Aynı ay aynı grupta öncelikli birime atanmamış ebelik öğrencisi var mı?
            assigned_here = {
                b.student_id for b in items if b.unit_id == a.unit_id
            }
            idle_ebelik = [
                students_by_id[sid].full_name
                for sid in ebelik_ids
                if students_by_id[sid].group == u.group
                and sid not in assigned_here
                and not any(
                    b.student_id == sid
                    and units_by_id[b.unit_id].ebelik_priority
                    for b in items
                )
            ]
            if idle_ebelik:
                out.append(
                    Violation(
                        rule_no=18,
                        severity=WARNING,
                        message=(
                            f"{u.name} ({month}) ebelik öncelikli olduğu halde "
                            f"{s.full_name} (ebelik değil) atanmış; uygun ebelik "
                            f"öğrencileri: {', '.join(idle_ebelik[:3])}."
                        ),
                        student_id=s.id,
                        month=month,
                        unit_id=u.id,
                    )
                )
    return out


def _check_rule19_repeat_pairs(assignments, students_by_id, units_by_id):
    """Madde 19: aynı ikili birden fazla ay aynı birimde — uyarı."""
    out = []
    by_month_unit: dict[tuple[str, str], list[str]] = defaultdict(list)
    for a in assignments:
        by_month_unit[(a.month, a.unit_id)].append(a.student_id)
    pair_months: dict[tuple[str, str], list[str]] = defaultdict(list)
    for (month, _uid), ids in by_month_unit.items():
        for s1, s2 in itertools.combinations(sorted(ids), 2):
            pair_months[(s1, s2)].append(month)
    for (s1, s2), months_together in pair_months.items():
        if len(months_together) > 1:
            n1 = students_by_id[s1].full_name
            n2 = students_by_id[s2].full_name
            out.append(
                Violation(
                    rule_no=19,
                    severity=WARNING,
                    message=(
                        f"{n1} ile {n2} birden fazla ay aynı birimde: "
                        f"{', '.join(sorted(months_together))}."
                    ),
                    student_id=s1,
                )
            )
    return out
