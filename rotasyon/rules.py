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
    CustomRule,
    Student,
    Unit,
    BRANCH_DOGUM_SALONU,
    BRANCH_LABELS,
    DEFAULT_SETTINGS,
    GENDER_LABELS,
    INTENSITY_LABELS,
    PROGRAM_EBELIK,
    RULE_AYRI_TUT,
    RULE_BIRIM_YASAK,
    RULE_BIRLIKTE_TUT,
    RULE_SABIT_ATAMA,
    rule_active_in_month,
)
from .normalize import normalize_key

ERROR = "hata"
WARNING = "uyarı"

# Özel (kullanıcı tanımlı) kural ihlalleri bu numarayla raporlanır
CUSTOM_RULE_NO = -1


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
    custom_rules: list[CustomRule] | None = None,
    settings: dict | None = None,
) -> list[Violation]:
    """Tüm denetimleri çalıştırır; ihlal yoksa boş liste döner.

    settings verilmezse sezon zorunlulukları (season_requirements)
    varsayılan listeden okunur.
    """
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
    v += _check_rule67_deadlines(
        valid, students_by_id, units_by_id, months, settings
    )
    v += _check_rule20_intensity(valid, students_by_id, units_by_id, months)
    v += _check_rule21_gender_balance(valid, students_by_id, units_by_id)
    v += _check_rule8_banned(valid, students_by_id, units_by_id)
    v += _check_rule9_dis(valid, students_by_id, units_by_id)
    v += _check_rule12_quota(valid, students_by_id, units_by_id)
    v += _check_rule17_must_fill(valid, students_by_id, units_by_id)
    v += _check_rule18_ebelik_priority(valid, students_by_id, units_by_id, months)
    v += _check_rule19_repeat_pairs(valid, students_by_id, units_by_id)
    v += _check_custom_rules(
        valid, students_by_id, units_by_id, custom_rules or [], months
    )
    _soften_past_violations(v, students_by_id, units_by_id, valid, months)
    return v


# Birim/öğrenci ÖZELLİĞİNE bağlı kurallar: özellik sezon ortasında
# değişebilir (kontenjan, cinsiyet kısıtı, yasak, muafiyet, grup, tam dolma).
# Geçmiş aylar o günkü tanıma göre yapılmıştı ve değiştirilemez.
_PAST_SOFTENED_RULES = {2, 3, 5, 8, 9, 12, 17}


def _soften_past_violations(v, students_by_id, units_by_id, assignments, months):
    """Tamamlanmış aylardaki özellik-bağımlı ihlalleri uyarıya indirir.

    'Tamamlanmış ay' = grubun EN SON planlanmış ayından önceki aylar.
    Kontenjan/kısıt sonradan değiştiyse eski aylar bugünkü tanımı sağlamaz;
    bu eyleme dönük bir hata değildir (geçmiş yeniden yazılmaz) ama kullanıcı
    yine de uyarı olarak görür. Son ay ve taslaklar hata düzeyinde kalır.
    """
    order = {m: i for i, m in enumerate(months)}
    last_by_group: dict[int, int] = {}
    for a in assignments:
        s = students_by_id.get(a.student_id)
        if s is None:
            continue
        idx = order.get(a.month, -1)
        if idx > last_by_group.get(s.group, -1):
            last_by_group[s.group] = idx
    if not last_by_group:
        return
    for x in v:
        if x.rule_no not in _PAST_SOFTENED_RULES or not x.month:
            continue
        if x.severity != ERROR:
            continue
        g = None
        if x.student_id and x.student_id in students_by_id:
            g = students_by_id[x.student_id].group
        elif x.unit_id and x.unit_id in units_by_id:
            g = units_by_id[x.unit_id].group
        if g == 0:  # her iki grupta ortak birim
            last = max(last_by_group.values())
        elif g in last_by_group:
            last = last_by_group[g]
        else:
            continue
        if order.get(x.month, 99) < last:
            x.severity = WARNING
            x.message += (
                " (Tamamlanmış ay: kural/kontenjan sonradan değiştiyse "
                "bilgi amaçlıdır, geçmiş yeniden yazılmaz.)"
            )


def _check_custom_rules(assignments, students_by_id, units_by_id, custom_rules, months):
    """Kullanıcı tanımlı kurallar: ayrı/birlikte tut, birim yasağı, sabit atama.

    Zaman kapsamlı kurallar (start_month/end_month) yalnız pencereleri
    içindeki aylarda denetlenir; sezon ortasında eklenen bir kural geçmiş
    (tamamlanmış) ayları geriye dönük ihlal saymaz.
    """
    out = []
    by_student_month: dict[tuple[str, str], str] = {
        (a.student_id, a.month): a.unit_id for a in assignments
    }
    months_assigned: dict[str, set[str]] = defaultdict(set)
    for a in assignments:
        months_assigned[a.student_id].add(a.month)

    def _name(sid):
        return students_by_id[sid].full_name if sid in students_by_id else "?"

    for rule in custom_rules:
        if not rule.active:
            continue
        ids = [sid for sid in rule.student_ids if sid in students_by_id]
        if rule.type == RULE_BIRIM_YASAK and ids and rule.unit_id:
            banned = units_by_id.get(rule.unit_id)
            if banned is None:
                continue
            key = normalize_key(banned.name)
            for sid in ids:
                for month in sorted(months_assigned[sid]):
                    if not rule_active_in_month(rule, month, months):
                        continue
                    uid = by_student_month.get((sid, month))
                    if uid and normalize_key(units_by_id[uid].name) == key:
                        out.append(
                            Violation(
                                rule_no=CUSTOM_RULE_NO,
                                severity=ERROR,
                                message=(
                                    f"Özel kural (birim yasağı) ihlali: "
                                    f"{_name(sid)} {month} ayında yasaklı "
                                    f"birimde: {units_by_id[uid].name}."
                                ),
                                student_id=sid,
                                month=month,
                                unit_id=uid,
                            )
                        )
        elif rule.type == RULE_AYRI_TUT and len(ids) >= 2:
            months_union = set().union(*(months_assigned[sid] for sid in ids)) \
                if ids else set()
            for month in months_union:
                if not rule_active_in_month(rule, month, months):
                    continue
                units_used = defaultdict(list)
                for sid in ids:
                    uid = by_student_month.get((sid, month))
                    if uid:
                        units_used[uid].append(sid)
                for uid, together in units_used.items():
                    if len(together) > 1:
                        out.append(
                            Violation(
                                rule_no=CUSTOM_RULE_NO,
                                severity=ERROR,
                                message=(
                                    "Özel kural (ayrı tut) ihlali: "
                                    + " ile ".join(_name(s) for s in together)
                                    + f" {month} ayında aynı birimde: "
                                    + units_by_id[uid].name + "."
                                ),
                                month=month,
                                unit_id=uid,
                            )
                        )
        elif rule.type == RULE_BIRLIKTE_TUT and len(ids) >= 2:
            common_months = set.intersection(
                *(months_assigned[sid] for sid in ids)
            ) if all(months_assigned[sid] for sid in ids) else set()
            for month in common_months:
                if not rule_active_in_month(rule, month, months):
                    continue
                units_used = {by_student_month.get((sid, month)) for sid in ids}
                if len(units_used) > 1:
                    out.append(
                        Violation(
                            rule_no=CUSTOM_RULE_NO,
                            severity=ERROR,
                            message=(
                                "Özel kural (birlikte tut) ihlali: "
                                + ", ".join(_name(s) for s in ids)
                                + f" {month} ayında farklı birimlerde."
                            ),
                            month=month,
                        )
                    )
        elif rule.type == RULE_SABIT_ATAMA and ids and rule.unit_id:
            for sid in ids:
                assigned = by_student_month.get((sid, rule.month))
                if assigned is not None and assigned != rule.unit_id:
                    expected = units_by_id.get(rule.unit_id)
                    out.append(
                        Violation(
                            rule_no=CUSTOM_RULE_NO,
                            severity=ERROR,
                            message=(
                                f"Özel kural (sabit atama) ihlali: {_name(sid)} "
                                f"{rule.month} ayında "
                                f"{expected.name if expected else '?'} biriminde "
                                "olmalıydı."
                            ),
                            student_id=sid,
                            month=rule.month,
                            unit_id=rule.unit_id,
                        )
                    )
    return out


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


def _check_rule67_deadlines(
    assignments, students_by_id, units_by_id, months, settings=None
):
    """Madde 6/7: dönem sonuna kadar zorunlu branş ziyaretleri.

    Sezon zorunlulukları (settings.season_requirements — örn. bir cerrahi,
    bir dahili, bir yoğun bakım, bir palyatif) branş bazında AYRI AYRI
    denetlenir; ebelik → doğum salonu (madde 7) her zaman eklidir.
    Bir zorunluluk yalnız o branştan birim tanımlıysa uygulanır.
    İhlal ancak dönemin son ayı da atandığı halde zorunluluk
    karşılanmadıysa "hata"; dönem bitmemişse rapor üretilmez (solver erken
    aylarda bonusla yönlendirir).
    """
    out = []
    if not months:
        return out
    requirements = (settings or DEFAULT_SETTINGS).get("season_requirements", [])
    available = {u.branch_category for u in units_by_id.values()}
    req_branches = [
        r["branch"]
        for r in requirements
        if r.get("branch") and r["branch"] in available
    ]
    last_month = months[-1]
    by_student: dict[str, list] = defaultdict(list)
    for a in assignments:
        by_student[a.student_id].append(a)
    for sid, items in by_student.items():
        s = students_by_id[sid]
        if not any(a.month == last_month for a in items):
            continue  # dönem henüz tamamlanmamış
        cats = {units_by_id[a.unit_id].branch_category for a in items}
        for b in req_branches:
            if b not in cats:
                out.append(
                    Violation(
                        rule_no=6,
                        severity=ERROR,
                        message=(
                            f"{s.full_name} dönem boyunca hiç "
                            f"{BRANCH_LABELS.get(b, b)} birimi görmemiş "
                            "(sezon zorunluluğu)."
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


def _check_rule20_intensity(assignments, students_by_id, units_by_id, months):
    """Madde 20 (BÖLÜMLER VE ÖZELLİKLERİ): bir öğrenci peş peşe iki ay
    yoğun bölüme ya da peş peşe iki ay hafif bölüme verilmez."""
    out = []
    order = {m: i for i, m in enumerate(months)}
    by_student: dict[str, dict[int, Unit]] = defaultdict(dict)
    for a in assignments:
        if a.month in order:
            by_student[a.student_id][order[a.month]] = units_by_id[a.unit_id]
    for sid, by_idx in by_student.items():
        s = students_by_id[sid]
        for i in sorted(by_idx):
            u1, u2 = by_idx.get(i), by_idx.get(i + 1)
            if u1 is None or u2 is None:
                continue
            if u1.intensity and u1.intensity == u2.intensity:
                label = INTENSITY_LABELS.get(u1.intensity, u1.intensity)
                out.append(
                    Violation(
                        rule_no=20,
                        severity=ERROR,
                        message=(
                            f"{s.full_name}: {months[i]} ve {months[i + 1]} "
                            f"aylarında peş peşe {label.lower()} bölüme "
                            f"verilmiş ({u1.name} → {u2.name})."
                        ),
                        student_id=sid,
                        month=months[i + 1],
                        unit_id=u2.id,
                    )
                )
    return out


def _check_rule21_gender_balance(assignments, students_by_id, units_by_id):
    """Madde 21 (BÖLÜMLER VE ÖZELLİKLERİ): havuz birimlerinde kız/erkek
    sayısı dengeli olmalı.

    Yalnız GİDERİLEBİLİR dengesizlik uyarı üretir: aynı ay aynı gruptaki
    başka bir havuz biriminde eksik cinsiyetten en az 2 öğrenci varsa bir
    takas dengeyi düzeltirdi, uyarı verilir. Grubun kendisi dengesizse
    (örn. 24 kız / 7 erkek — çoğu havuza erkek düşmez) uyarı ÜRETİLMEZ:
    kimsenin düzeltemeyeceği dağılım için uyarı gürültüdür.
    """
    out = []
    per_unit_month: dict[tuple[str, str], list[str]] = defaultdict(list)
    for a in assignments:
        u = units_by_id[a.unit_id]
        if u.pool and not u.gender_restriction:
            g = students_by_id[a.student_id].gender
            if g:
                per_unit_month[(a.unit_id, a.month)].append(g)
    for (uid, month), genders in per_unit_month.items():
        k, e = genders.count("K"), genders.count("E")
        if abs(k - e) < 3:
            continue
        u = units_by_id[uid]
        scarce = "E" if e < k else "K"
        fixable = any(
            other_genders.count(scarce) >= 2
            for (oid, m2), other_genders in per_unit_month.items()
            if m2 == month and oid != uid and units_by_id[oid].group == u.group
        )
        if not fixable:
            continue
        out.append(
            Violation(
                rule_no=21,
                severity=WARNING,
                message=(
                    f"{u.name} ({month}): kız/erkek dağılımı dengesiz "
                    f"({k} kız, {e} erkek)."
                ),
                month=month,
                unit_id=uid,
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
    """Madde 18: öncelikli birimde ebelik-dışı öğrenci varken, o birime
    GERÇEKTEN atanabilecek boşta ebelik öğrencisi kalmışsa uyarı.

    "Atanabilir" tanımı çözücüyle aynı: cinsiyet kısıtı, tekrar yasağı
    (madde 1, ad bazında), yasaklı birimler, diş muafiyeti ve komşu ay
    yoğunluk yasağı (madde 20) sağlanmalı. Aksi halde çözücünün zorunlu
    bıraktığı atamalar (örn. yalnız erkek alan birime tüm ebelikler kızken)
    yanlış uyarı üretir.
    """
    out = []
    ebelik_ids = {
        sid for sid, s in students_by_id.items() if s.program == PROGRAM_EBELIK
    }
    if not ebelik_ids:
        return out
    order = {m: i for i, m in enumerate(months)}
    by_month: dict[str, list] = defaultdict(list)
    visited_keys: dict[str, set[tuple[str, str]]] = defaultdict(set)
    unit_by_student_month: dict[tuple[str, str], Unit] = {}
    for a in assignments:
        by_month[a.month].append(a)
        visited_keys[a.student_id].add(
            (a.month, normalize_key(units_by_id[a.unit_id].name))
        )
        unit_by_student_month[(a.student_id, a.month)] = units_by_id[a.unit_id]

    def eligible(sid: str, u: Unit, month: str) -> bool:
        s = students_by_id[sid]
        if u.gender_restriction and s.gender and s.gender != u.gender_restriction:
            return False
        if u.id in s.banned_unit_ids:
            return False
        if s.dis_exempt and "DİŞ" in normalize_key(u.name):
            return False
        # tekrar yasağı: bu ay dışındaki aylarda aynı bölümü görmüş mü?
        key = normalize_key(u.name)
        if any(m != month and k == key for m, k in visited_keys[sid]):
            return False
        # komşu ay yoğunluk yasağı (madde 20)
        if u.intensity and month in order:
            idx = order[month]
            for i in (idx - 1, idx + 1):
                if 0 <= i < len(months):
                    prev = unit_by_student_month.get((sid, months[i]))
                    if prev is not None and prev.intensity == u.intensity:
                        return False
        return True

    for month, items in by_month.items():
        for a in items:
            u = units_by_id[a.unit_id]
            s = students_by_id[a.student_id]
            if not u.ebelik_priority or s.id in ebelik_ids:
                continue
            # Aynı ay aynı grupta öncelikli birime atanmamış ve bu birime
            # atanabilir durumda ebelik öğrencisi var mı?
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
                and eligible(sid, u, month)
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
