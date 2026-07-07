"""Sezon kapasite ön-denetimi.

Toplu/aylık üretim 8. ayda duvara çarpmadan ÖNCE, verinin sezon sonuna
kadar taşıyıp taşımayacağını ucuz aritmetikle denetler ve somut Türkçe
önerilerle raporlar. Kritik örnek: toplam kontenjan öğrenci sayısına tam
eşitse her birim her ay dolmak zorundadır; kontenjanı q olan bir birim
sezonda (kalan ay × q) FARKLI öğrenci ister (madde 1 tekrar yasağı) —
uygun öğrenci sayısı bunun altındaysa sezon matematiksel olarak taşınamaz.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import Assignment, Student, Unit
from .normalize import normalize_key

ERROR = "hata"
WARNING = "uyarı"


@dataclass
class CapacityFinding:
    level: str  # ERROR | WARNING
    group: int
    message: str


def _eligible_unvisited(
    unit: Unit,
    students: list[Student],
    visited_names: dict[str, set[str]],
) -> int:
    """Bu birime sezonda hâlâ atanabilecek (hiç gitmemiş + kısıtları uyan)
    öğrenci sayısı."""
    key = normalize_key(unit.name)
    n = 0
    for s in students:
        if unit.gender_restriction and s.gender and s.gender != unit.gender_restriction:
            continue
        if unit.id in s.banned_unit_ids:
            continue
        if s.dis_exempt and "DİŞ" in key:
            continue
        if key in visited_names.get(s.id, set()):
            continue
        n += 1
    return n


def season_capacity_findings(
    students: list[Student],
    units: list[Unit],
    months: list[str],
    assignments: list[Assignment],
) -> list[CapacityFinding]:
    """Grup grup, kalan sezonun kapasite denetimi.

    Yalnız DOLMAK ZORUNDA olan birimler denetlenir: must_fill işaretliler
    ve — toplam kontenjan öğrenci sayısına eşitse — bütün birimler
    (güvercin yuvası: boşluk yoksa her birim dolar).
    """
    findings: list[CapacityFinding] = []
    units_by_id = {u.id: u for u in units}
    active_students = [s for s in students if getattr(s, "active", True)]
    groups = sorted({s.group for s in active_students})
    for g in groups:
        g_students = [s for s in active_students if s.group == g]
        g_ids = {s.id for s in g_students}
        g_units = [
            u for u in units if u.group in (0, g) and u.active and u.quota > 0
        ]
        done_months = {a.month for a in assignments if a.student_id in g_ids}
        remaining = [m for m in months if m not in done_months]
        if not remaining:
            continue
        total_quota = sum(u.quota for u in g_units)
        n = len(g_students)
        exact_fill = total_quota == n
        if exact_fill:
            findings.append(
                CapacityFinding(
                    level=WARNING,
                    group=g,
                    message=(
                        f"Grup {g}: toplam kontenjan ({total_quota}) öğrenci "
                        f"sayısıyla ({n}) TAM eşit. Böyle olunca her birim her "
                        "ay dolmak zorunda kalır; kimse aynı birime iki kez "
                        "gidemediği için geniş kontenjanlı birimler birkaç ayda "
                        "uygun öğrenci bırakmaz. En az birkaç kişilik boşluk "
                        "bırakın: bir birimin kontenjanını artırın ya da yedek "
                        "birim ekleyin."
                    ),
                )
            )

        # her öğrencinin gördüğü bölüm adları (madde 1 ad bazında işler)
        visited_names: dict[str, set[str]] = {}
        for a in assignments:
            if a.student_id in g_ids and a.unit_id in units_by_id:
                visited_names.setdefault(a.student_id, set()).add(
                    normalize_key(units_by_id[a.unit_id].name)
                )

        for u in g_units:
            forced = u.must_fill or exact_fill
            if not forced:
                continue
            need = len(remaining) * u.quota
            have = _eligible_unvisited(u, g_students, visited_names)
            if have < need:
                fits = have // u.quota if u.quota else 0
                why = (
                    "bu birim her ay dolmak zorunda (çiftte her ay bir kız bir "
                    "erkek bulunmalı)"
                    if u.must_fill
                    else "toplam kontenjan öğrenci sayısına eşit olduğu için her "
                    "birim her ay dolmak zorunda"
                )
                max_q = have // len(remaining)
                suggestion = (
                    f"bu birimin kontenjanını en fazla {max_q} yapın"
                    if max_q >= 1
                    else "bu birimin 'her ay dolmalı' zorunluluğunu kaldırın ya "
                    "da uygun öğrenci sayısını artırın (kontenjan payı bırakın "
                    "veya kısıtları gevşetin)"
                )
                findings.append(
                    CapacityFinding(
                        level=ERROR,
                        group=g,
                        message=(
                            f"Grup {g} · {u.friendly_name}: {why}. Kimse aynı "
                            "birime iki kez gidemediği için kalan "
                            f"{len(remaining)} ayda {need} FARKLI uygun öğrenci "
                            f"gerekir; uygun yalnız {have} kişi var (en çok "
                            f"{fits} ay dolar). Çözüm: {suggestion}."
                        ),
                    )
                )
    return findings
