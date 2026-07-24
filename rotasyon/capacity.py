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

from .models import (
    Assignment,
    BRANCH_DOGUM_SALONU,
    BRANCH_LABELS,
    DEFAULT_SETTINGS,
    PROGRAM_EBELIK,
    Student,
    Unit,
)
from .normalize import normalize_key

ERROR = "hata"
WARNING = "uyarı"

# Uyarı metinlerinde kaç öğrenci adı sayılsın (gerisi "ve N kişi daha")
_NAME_LIMIT = 6


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


# ===================== SEZON ZORUNLULUKLARI (ileriye dönük) =====================
#
# Kural denetleyicisi (rules._check_rule6_7) zorunlu branşları ancak dönemin
# SON AYI atandıktan sonra ihlal sayar — yani telafi imkânı kalmadığında.
# Buradaki denetim aynı zorunluluğu HER AY, kalan aylara bakarak önden
# hesaplar: "bu öğrenci palyatif görmeden sezon kapanacak" durumu daha
# EYLÜL'de görünsün. Kaçırılırsa geri dönüşü yoktur, o yüzden ayrı bir
# denetim olarak durur.


def _required_branches(units: list[Unit], settings: dict | None) -> list[str]:
    """Ayarlardaki zorunlu branşlar — yalnız o branşta birim tanımlıysa."""
    reqs = (settings or DEFAULT_SETTINGS).get("season_requirements", [])
    available = {u.branch_category for u in units if u.active and u.quota > 0}
    return [
        r["branch"]
        for r in reqs
        if r.get("branch") and r["branch"] in available
    ]


def _student_required(student: Student, req_branches: list[str],
                      available: set[str]) -> list[str]:
    """Bu öğrenci için geçerli zorunluluklar (ebelik → doğum salonu eklenir)."""
    out = list(req_branches)
    if (
        student.program == PROGRAM_EBELIK
        and BRANCH_DOGUM_SALONU in available
        and BRANCH_DOGUM_SALONU not in out
    ):
        out.append(BRANCH_DOGUM_SALONU)
    return out


def _reachable(student: Student, branch: str, units: list[Unit],
               visited_keys: set[str]) -> bool:
    """Öğrenci bu branşta gidebileceği bir birim BULABİLİR mi?

    Daha önce gittiği birime tekrar gidemez (madde 1), cinsiyet kısıtı ve
    yasaklı birimler elenir. Hiç uygun birim kalmadıysa zorunluluk artık
    matematiksel olarak karşılanamaz.
    """
    for u in units:
        if u.branch_category != branch:
            continue
        if not u.active or u.quota <= 0:
            continue
        if u.group not in (0, student.group):
            continue
        if u.gender_restriction and student.gender and (
            student.gender != u.gender_restriction
        ):
            continue
        if u.id in student.banned_unit_ids:
            continue
        key = normalize_key(u.name)
        if student.dis_exempt and "DİŞ" in key:
            continue
        if key in visited_keys:
            continue
        return True
    return False


def _names(students: list[Student]) -> str:
    adlar = [s.full_name for s in students[:_NAME_LIMIT]]
    kalan = len(students) - len(adlar)
    return ", ".join(adlar) + (f" ve {kalan} kişi daha" if kalan else "")


def season_requirement_findings(
    students: list[Student],
    units: list[Unit],
    months: list[str],
    assignments: list[Assignment],
    settings: dict | None = None,
) -> list[CapacityFinding]:
    """Zorunlu branşların sezon SONUNA kadar karşılanabilirliği.

    Üç ayrı risk raporlanır:
      1. Kalan ay sayısı, eksik zorunlu branş sayısından AZ  → artık imkânsız
      2. Bir branşta gidebileceği birim kalmamış             → artık imkânsız
      3. Kalan ay sayısı eksik branş sayısına TAM EŞİT       → sıfır pay
    """
    findings: list[CapacityFinding] = []
    units_by_id = {u.id: u for u in units}
    active = [s for s in students if getattr(s, "active", True)]
    req_branches = _required_branches(units, settings)
    available = {u.branch_category for u in units if u.active and u.quota > 0}
    if not req_branches and BRANCH_DOGUM_SALONU not in available:
        return findings

    # öğrenci → gördüğü branşlar / birim adları / dolu aylar
    seen_branch: dict[str, set[str]] = {}
    seen_key: dict[str, set[str]] = {}
    done_months: dict[str, set[str]] = {}
    for a in assignments:
        u = units_by_id.get(a.unit_id)
        done_months.setdefault(a.student_id, set()).add(a.month)
        if u is None:
            continue
        seen_branch.setdefault(a.student_id, set()).add(u.branch_category)
        seen_key.setdefault(a.student_id, set()).add(normalize_key(u.name))

    imkansiz_ay: dict[int, list[Student]] = {}
    imkansiz_birim: dict[tuple[int, str], list[Student]] = {}
    sifir_pay: dict[int, list[Student]] = {}

    for s in active:
        required = _student_required(s, req_branches, available)
        if not required:
            continue
        gorulen = seen_branch.get(s.id, set())
        eksik = [b for b in required if b not in gorulen]
        if not eksik:
            continue
        kalan = [m for m in months if m not in done_months.get(s.id, set())]

        # 2) hiç uygun birim kalmamış branşlar
        ulasilamaz = [
            b for b in eksik
            if not _reachable(s, b, units, seen_key.get(s.id, set()))
        ]
        for b in ulasilamaz:
            imkansiz_birim.setdefault((s.group, b), []).append(s)

        # 1) ay sayısı yetmiyor  /  3) tam denk
        gercekten_eksik = [b for b in eksik if b not in ulasilamaz]
        if len(gercekten_eksik) > len(kalan):
            imkansiz_ay.setdefault(s.group, []).append(s)
        elif gercekten_eksik and len(gercekten_eksik) == len(kalan):
            sifir_pay.setdefault(s.group, []).append(s)

    for g, ogrenciler in sorted(imkansiz_ay.items()):
        findings.append(
            CapacityFinding(
                level=ERROR,
                group=g,
                message=(
                    f"Grup {g}: {len(ogrenciler)} öğrencinin sezon zorunluluğu "
                    "artık karşılanamaz — görmeleri gereken zorunlu branş "
                    "sayısı, kalan ay sayısından fazla. Sezon bu haliyle "
                    "biterse bu öğrenciler eksik mezun olur. Çözüm: geçmiş "
                    f"ayların birkaçını düzeltin. ({_names(ogrenciler)})"
                ),
            )
        )
    for (g, b), ogrenciler in sorted(imkansiz_birim.items()):
        findings.append(
            CapacityFinding(
                level=ERROR,
                group=g,
                message=(
                    f"Grup {g} · {BRANCH_LABELS.get(b, b)}: "
                    f"{len(ogrenciler)} öğrenci bu zorunlu branşı artık "
                    "göremez — gidebilecekleri (daha önce gitmedikleri, "
                    "cinsiyet/yasak kısıtlarına uyan) bu branşta birim "
                    "kalmadı. Çözüm: bu branşta birim ekleyin/aktifleştirin "
                    f"ya da kısıtları gevşetin. ({_names(ogrenciler)})"
                ),
            )
        )
    for g, ogrenciler in sorted(sifir_pay.items()):
        findings.append(
            CapacityFinding(
                level=WARNING,
                group=g,
                message=(
                    f"Grup {g}: {len(ogrenciler)} öğrencinin kalan her ayı "
                    "zorunlu bir branşa denk gelmek zorunda — hiç pay yok. "
                    "Bu aylarda başka bir birime kaydırılırlarsa zorunluluk "
                    f"karşılanamaz hale gelir. ({_names(ogrenciler)})"
                ),
            )
        )
    return findings
