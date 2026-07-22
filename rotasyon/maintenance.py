"""Veri bakımı: silme sonrası tutarlılık ve sahipsiz kayıt temizliği.

Denetleyici (rules.check_all) silinmiş öğrenci/birime işaret eden atamaları
"kural 0" hatası olarak raporlar ama onları TEMİZLEYEMEZ; motorun geri kalanı
bu kayıtları sessizce yok sayar. Teknik olmayan kullanıcı JSON'a giremeyeceği
için temizlik uygulama içinden yapılabilmelidir — bu modül o işlemlerin saf
(UI'sız, test edilebilir) mantığıdır. Hiçbir fonksiyon girdiyi değiştirmez;
yeni listeler döndürür, kalıcılaştırma çağıranın işidir.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import (
    Assignment,
    CustomRule,
    RULE_AYRI_TUT,
    RULE_BIRLIKTE_TUT,
    Student,
    Unit,
)

# İkili/grup kuralları en az 2 öğrenciyle anlamlıdır; sabit atama ve birim
# yasağı tek öğrenciyle de çalışır.
_MIN_STUDENTS = {RULE_AYRI_TUT: 2, RULE_BIRLIKTE_TUT: 2}


@dataclass
class StudentRemoval:
    """Öğrenci silmenin dökümü — UI onay metni bunu kullanır."""

    students: list[Student]
    assignments: list[Assignment]
    rules: list[CustomRule]
    removed_assignments: int
    removed_rules: int


def remove_student(
    students: list[Student],
    assignments: list[Assignment],
    rules: list[CustomRule],
    student_id: str,
) -> StudentRemoval:
    """Öğrenciyi atamaları ve kural üyelikleriyle birlikte kaldırır.

    Sahipsiz atama bırakılmaz (kural 0 hatası doğurur ve kullanıcının
    temizleme aracı yoktur). Öğrencinin geçtiği özel kurallardan üyeliği
    düşülür; kural anlamını yitirirse (ayrı/birlikte tut 2 kişinin altına
    inerse ya da hiç öğrenci kalmazsa) kuralın kendisi de kaldırılır.
    """
    kept_students = [s for s in students if s.id != student_id]
    kept_assignments = [a for a in assignments if a.student_id != student_id]
    kept_rules, dropped = _prune_rules(rules, {student_id})
    return StudentRemoval(
        students=kept_students,
        assignments=kept_assignments,
        rules=kept_rules,
        removed_assignments=len(assignments) - len(kept_assignments),
        removed_rules=dropped,
    )


def _prune_rules(
    rules: list[CustomRule], gone_student_ids: set[str]
) -> tuple[list[CustomRule], int]:
    kept: list[CustomRule] = []
    dropped = 0
    for r in rules:
        remaining = [sid for sid in r.student_ids if sid not in gone_student_ids]
        if len(remaining) < _MIN_STUDENTS.get(r.type, 1):
            dropped += 1
            continue
        if len(remaining) != len(r.student_ids):
            r = CustomRule(**{**r.to_dict(), "student_ids": remaining})
        kept.append(r)
    return kept, dropped


def orphan_assignments(
    students: list[Student],
    units: list[Unit],
    assignments: list[Assignment],
) -> list[Assignment]:
    """Silinmiş öğrenci/birime işaret eden atamalar (kural 0'ın kaynağı).

    Normal akışta oluşmaz (birim silme korumalı, öğrenci silme kademeli);
    eski yedeğin kısmi geri yüklenmesi ya da elle düzenlenmiş JSON ile
    ortaya çıkabilir.
    """
    student_ids = {s.id for s in students}
    unit_ids = {u.id for u in units}
    return [
        a
        for a in assignments
        if a.student_id not in student_ids or a.unit_id not in unit_ids
    ]


def strip_orphan_assignments(
    students: list[Student],
    units: list[Unit],
    assignments: list[Assignment],
) -> tuple[list[Assignment], int]:
    """Sahipsiz atamaları ayıklar. Dönüş: (kalanlar, atılan sayısı)."""
    orphans = {id(a) for a in orphan_assignments(students, units, assignments)}
    kept = [a for a in assignments if id(a) not in orphans]
    return kept, len(assignments) - len(kept)
