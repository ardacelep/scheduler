"""İleriye dönük risk denetimi — "sonra fark edilirse telafisi yok" durumları.

`rules.py` bir kuralın ÇİĞNENDİĞİNİ çok iyi yakalar, ama bazı riskler
anlaşıldığında iş işten geçmiş olur: öğrencinin palyatif görmediği HAZİRAN'da
anlaşılırsa yapılacak bir şey yoktur. Bu modül aynı soruları KALAN aylara
bakarak sorar ve kullanıcıyı olmadan önce uyarır.

İki kademe:

* `forward_risks` — ucuz aritmetik, her sayfa açılışında koşabilir. Kesin
  çelişkileri (matematiksel olarak imkânsız durumlar) bulur.
* `deep_feasibility` — kalan sezonu GERÇEKTEN çözmeyi dener. Aritmetiğin
  göremeyeceği kombinatorik çıkmazlara kesin cevap verir; yavaş olduğu için
  yalnız kullanıcı isteyince (butonla) çalışır.

ÖNEMLİ: bu modül ortools'u modül düzeyinde İÇE AKTARMAZ. Panel her sayfa
açılışında render edilir; ortools'un bozuk olduğu bir kurulumda (Python 3.14
ile `Solve()` süreci çökertiyor) panelin uygulamayı düşürmemesi gerekir.
Çözücü yalnız `deep_feasibility` içinde, tembel olarak yüklenir.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .capacity import (
    ERROR,
    WARNING,
    season_capacity_findings,
    season_requirement_findings,
)
from .models import (
    Assignment,
    CustomRule,
    RULE_AYRI_TUT,
    RULE_BIRLIKTE_TUT,
    RULE_SABIT_ATAMA,
    Student,
    Unit,
    rule_active_in_month,
)
from .normalize import normalize_key

# Risk kategorileri — panelde başlık olarak kullanılır
CAT_QUOTA = "Kontenjan"
CAT_REQUIREMENT = "Sezon zorunlulukları"
CAT_RUNWAY = "Gidilecek birim kalmıyor"
CAT_CUSTOM = "Özel kurallar"

_NAME_LIMIT = 6


@dataclass
class Risk:
    level: str  # ERROR | WARNING
    category: str
    message: str
    group: int = 0  # 0 = yapısal / gruptan bağımsız


@dataclass
class DeepResult:
    """Deneme çözümünün grup bazında sonucu."""

    group: int
    months: list[str]
    status: str  # OPTIMAL | FEASIBLE | INFEASIBLE | UNKNOWN | ATLANDI
    reasons: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in ("OPTIMAL", "FEASIBLE")


def _names(students: list[Student]) -> str:
    adlar = [s.full_name for s in students[:_NAME_LIMIT]]
    kalan = len(students) - len(adlar)
    return ", ".join(adlar) + (f" ve {kalan} kişi daha" if kalan else "")


def _usable(unit: Unit) -> bool:
    return unit.active and unit.quota > 0


def can_attend(student: Student, unit: Unit) -> bool:
    """Öğrenci bu birime (geçmişi saymadan) prensipte atanabilir mi?

    capacity._eligible_unvisited ile aynı eleme mantığı; tekrar yasağı
    (madde 1) ayrıca uygulanır çünkü o öğrencinin geçmişine bağlıdır.
    """
    if unit.group not in (0, student.group):
        return False
    if unit.gender_restriction and student.gender:
        if student.gender != unit.gender_restriction:
            return False
    if unit.id in student.banned_unit_ids:
        return False
    if student.dis_exempt and "DİŞ" in normalize_key(unit.name):
        return False
    return True


def _visited_keys(
    assignments: list[Assignment], units_by_id: dict[str, Unit]
) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for a in assignments:
        u = units_by_id.get(a.unit_id)
        if u is not None:
            out.setdefault(a.student_id, set()).add(normalize_key(u.name))
    return out


def _done_months(assignments: list[Assignment]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for a in assignments:
        out.setdefault(a.student_id, set()).add(a.month)
    return out


# --------------------------------------------------------------------------
# R1: grup için toplam kontenjan yetmiyor
# --------------------------------------------------------------------------
def _risk_total_quota(students, units, months, assignments) -> list[Risk]:
    """Bir grubun kullanabileceği toplam kontenjan, o gruptaki öğrenci
    sayısından azsa hiçbir ay çözülemez.

    Gerekli koşul olarak bakılır: grup g'nin öğrencileri yalnız group ∈ {0, g}
    birimlere gidebildiğinden, bu birimlerin toplamı n_g'nin altındaysa o ay
    matematiksel olarak imkânsızdır (0 grubu birimler diğer grupla paylaşılsa
    bile durum ancak daha kötü olur).
    """
    out = []
    done = _done_months(assignments)
    for g in sorted({s.group for s in students}):
        g_students = [s for s in students if s.group == g]
        kalan = [
            m for m in months
            if not any(m in done.get(s.id, set()) for s in g_students)
        ]
        if not kalan:
            continue
        quota = sum(u.quota for u in units if _usable(u) and u.group in (0, g))
        n = len(g_students)
        if quota < n:
            out.append(
                Risk(
                    level=ERROR,
                    category=CAT_QUOTA,
                    group=g,
                    message=(
                        f"Grup {g}: bu grubun gidebileceği birimlerin toplam "
                        f"kontenjanı {quota}, ama grupta {n} aktif öğrenci var. "
                        f"{n - quota} öğrenciye hiçbir ay yer bulunamaz. "
                        "Çözüm: kontenjanları artırın, pasif birimleri "
                        "aktifleştirin ya da yeni birim ekleyin."
                    ),
                )
            )
    return out


# --------------------------------------------------------------------------
# R2: öğrencinin gidebileceği farklı birim tükeniyor (madde 1 çıkmazı)
# --------------------------------------------------------------------------
def _risk_unit_runway(students, units, months, assignments) -> list[Risk]:
    """Kimse aynı bölüme iki kez gidemez (madde 1). Bir öğrencinin daha
    gitmediği uygun birim sayısı, kalan ay sayısından azsa sezon o öğrenci
    için tamamlanamaz.

    Birimler AD bazında sayılır: "FTR.ÜNİT k" ve "FTR.ÜNİT e" aynı bölümdür.
    """
    units_by_id = {u.id: u for u in units}
    visited = _visited_keys(assignments, units_by_id)
    done = _done_months(assignments)
    dar: dict[int, list[Student]] = {}
    bitmis: dict[int, list[Student]] = {}
    for s in students:
        kalan_ay = [m for m in months if m not in done.get(s.id, set())]
        if not kalan_ay:
            continue
        gorulen = visited.get(s.id, set())
        secenek = {
            normalize_key(u.name)
            for u in units
            if _usable(u) and can_attend(s, u) and normalize_key(u.name) not in gorulen
        }
        if len(secenek) < len(kalan_ay):
            (bitmis if not secenek else dar).setdefault(s.group, []).append(s)
    out = []
    for g, ogr in sorted(bitmis.items()):
        out.append(
            Risk(
                level=ERROR,
                category=CAT_RUNWAY,
                group=g,
                message=(
                    f"Grup {g}: {len(ogr)} öğrencinin gidebileceği hiçbir birim "
                    "kalmadı — hepsine ya daha önce gitmişler ya da cinsiyet "
                    "kısıtı/yasak eliyor. Bu öğrenciler için hiçbir yeni ay "
                    f"üretilemez. ({_names(ogr)})"
                ),
            )
        )
    for g, ogr in sorted(dar.items()):
        out.append(
            Risk(
                level=ERROR,
                category=CAT_RUNWAY,
                group=g,
                message=(
                    f"Grup {g}: {len(ogr)} öğrencinin daha gitmediği farklı "
                    "birim sayısı, kalan ay sayısından az. Kimse aynı bölüme "
                    "iki kez gidemediği için sezonun tamamı doldurulamaz. "
                    "Çözüm: bu öğrencilere uygun yeni birim ekleyin ya da "
                    f"kısıtlarını (yasaklı birim) gevşetin. ({_names(ogr)})"
                ),
            )
        )
    return out


# --------------------------------------------------------------------------
# R3: sabit atama gelecekte patlayacak
# --------------------------------------------------------------------------
def fixed_assignment_conflicts(
    rule: CustomRule,
    students_by_id: dict[str, Student],
    units_by_id: dict[str, Unit],
    assignments: list[Assignment],
    all_rules: list[CustomRule] | None = None,
) -> list[str]:
    """Tek bir 'sabit atama' kuralının gelecekte yaratacağı çakışmalar.

    Kural EKLENİRKEN de (Veri Yönetimi ▸ Kurallar) aynı fonksiyon çağrılır;
    kullanıcı sorunu oluşmadan görsün diye ayrı fonksiyon olarak durur.
    Dönüş: Türkçe açıklama listesi (boşsa sorun yok).
    """
    out: list[str] = []
    unit = units_by_id.get(rule.unit_id)
    if unit is None:
        return ["Kuralın işaret ettiği birim artık yok."]
    if not _usable(unit):
        out.append(
            f"{unit.name} pasif ya da kontenjanı 0 — {rule.month} ayında "
            "buraya atama yapılamaz."
        )

    visited = _visited_keys(assignments, units_by_id)
    key = normalize_key(unit.name)
    for sid in rule.student_ids:
        s = students_by_id.get(sid)
        if s is None:
            out.append("Kuraldaki öğrencilerden biri artık yok.")
            continue
        # aynı bölüme başka bir ayda gidilmiş → madde 1 ihlali garanti
        if key in visited.get(sid, set()):
            gecmis = [
                a.month
                for a in assignments
                if a.student_id == sid
                and a.unit_id in units_by_id
                and normalize_key(units_by_id[a.unit_id].name) == key
                and a.month != rule.month
            ]
            if gecmis:
                out.append(
                    f"{s.full_name} {unit.name} birimine zaten "
                    f"{', '.join(gecmis)} ayında gidiyor — aynı bölüme ikinci "
                    f"kez gidilemez, {rule.month} ayında kural çiğnenecek."
                )
        if unit.group not in (0, s.group):
            out.append(
                f"{s.full_name} {s.group}. grupta ama {unit.name} "
                f"{unit.group}. grubun birimi."
            )
        if unit.gender_restriction and s.gender and s.gender != unit.gender_restriction:
            out.append(
                f"{s.full_name} ({'kız' if s.gender == 'K' else 'erkek'}) "
                f"{unit.friendly_name} birimine atanamaz."
            )
        if unit.id in s.banned_unit_ids:
            out.append(
                f"{unit.name}, {s.full_name} için yasaklı birim olarak "
                "işaretli — sabit atama bununla çelişiyor."
            )
        if s.dis_exempt and "DİŞ" in key:
            out.append(
                f"{s.full_name} diş muafiyetli ama sabit atama {unit.name} "
                "birimine yönlendiriyor."
            )

    # aynı ay + aynı birime sabit atanan toplam öğrenci kontenjanı aşıyor mu
    if all_rules:
        ayni = {
            sid
            for r in all_rules
            if r.active
            and r.type == RULE_SABIT_ATAMA
            and r.unit_id == rule.unit_id
            and r.month == rule.month
            for sid in r.student_ids
        }
        if len(ayni) > unit.quota:
            out.append(
                f"{rule.month} ayında {unit.name} birimine sabit atanan "
                f"{len(ayni)} öğrenci var ama kontenjanı {unit.quota}."
            )
    return out


def _risk_fixed_assignments(
    students, units, months, assignments, custom_rules
) -> list[Risk]:
    students_by_id = {s.id: s for s in students}
    units_by_id = {u.id: u for u in units}
    done = _done_months(assignments)
    out = []
    for rule in custom_rules:
        if not rule.active or rule.type != RULE_SABIT_ATAMA:
            continue
        # yalnız HENÜZ ÜRETİLMEMİŞ aylar risk; geçmiş ay zaten rules.py'de
        already = any(
            rule.month in done.get(sid, set()) for sid in rule.student_ids
        )
        if already or rule.month not in months:
            continue
        sorunlar = fixed_assignment_conflicts(
            rule, students_by_id, units_by_id, assignments, custom_rules
        )
        for msg in sorunlar:
            g = next(
                (students_by_id[s].group for s in rule.student_ids
                 if s in students_by_id),
                0,
            )
            out.append(
                Risk(
                    level=ERROR,
                    category=CAT_CUSTOM,
                    group=g,
                    message=f"Sabit atama ({rule.month}): {msg}",
                )
            )
    return out


# --------------------------------------------------------------------------
# R4: birlikte tut imkânsız
# --------------------------------------------------------------------------
def units_fitting_all(group: list[Student], units: list[Unit]) -> list[Unit]:
    """Verilen öğrencilerin TAMAMINI aynı anda alabilecek birimler.

    'Birlikte tut' kuralının uygulanabilirliği budur; Kurallar sekmesi de
    kural eklenirken aynı fonksiyonu çağırır (tek kaynak).
    """
    k = len(group)
    return [
        u for u in units
        if _usable(u) and u.quota >= k and all(can_attend(s, u) for s in group)
    ]


def _risk_together(students, units, months, assignments, custom_rules) -> list[Risk]:
    """'Birlikte tut' kuralındaki k kişiyi aynı anda alabilecek birim var mı?

    Kontenjanı k'dan küçük birimler bu grubu alamaz; grup/cinsiyet/yasak
    kısıtları da hepsine birden uymalı. Hiç uygun birim yoksa kural her ay
    ihlal edilir.
    """
    students_by_id = {s.id: s for s in students}
    out = []
    for rule in custom_rules:
        if not rule.active or rule.type != RULE_BIRLIKTE_TUT:
            continue
        grup = [students_by_id[s] for s in rule.student_ids if s in students_by_id]
        if len(grup) < 2:
            continue
        k = len(grup)
        uygun = units_fitting_all(grup, units)
        if not uygun:
            adlar = ", ".join(s.full_name for s in grup)
            out.append(
                Risk(
                    level=ERROR,
                    category=CAT_CUSTOM,
                    group=grup[0].group,
                    message=(
                        f"Birlikte tut ({adlar}): bu {k} öğrenciyi aynı anda "
                        "alabilecek hiçbir birim yok — kontenjanı yeten ve "
                        "hepsinin kısıtlarına uyan birim bulunmuyor. Kural her "
                        "ay ihlal edilir. Çözüm: bir birimin kontenjanını en az "
                        f"{k} yapın ya da kuralı kaldırın."
                    ),
                )
            )
    return out


# --------------------------------------------------------------------------
# R5: ayrı tut ↔ birlikte tut çelişkisi
# --------------------------------------------------------------------------
def _pairs(ids):
    ids = sorted(ids)
    return {(a, b) for i, a in enumerate(ids) for b in ids[i + 1:]}


def _windows_overlap(r1: CustomRule, r2: CustomRule, months: list[str]) -> bool:
    return any(
        rule_active_in_month(r1, m, months) and rule_active_in_month(r2, m, months)
        for m in months
    )


def _risk_contradictions(students, months, custom_rules) -> list[Risk]:
    students_by_id = {s.id: s for s in students}
    ayri = [r for r in custom_rules if r.active and r.type == RULE_AYRI_TUT]
    birlikte = [r for r in custom_rules if r.active and r.type == RULE_BIRLIKTE_TUT]
    out = []
    seen = set()
    for a in ayri:
        for b in birlikte:
            ortak = _pairs(a.student_ids) & _pairs(b.student_ids)
            if not ortak or not _windows_overlap(a, b, months):
                continue
            for pair in sorted(ortak):
                if pair in seen:
                    continue
                seen.add(pair)
                adlar = " ve ".join(
                    students_by_id[p].full_name if p in students_by_id else "?"
                    for p in pair
                )
                out.append(
                    Risk(
                        level=ERROR,
                        category=CAT_CUSTOM,
                        group=(
                            students_by_id[pair[0]].group
                            if pair[0] in students_by_id else 0
                        ),
                        message=(
                            f"{adlar} için hem 'ayrı tut' hem 'birlikte tut' "
                            "kuralı tanımlı ve ikisi aynı aylarda geçerli — "
                            "bu ikisi aynı anda sağlanamaz. Birini kaldırın "
                            "veya ay aralıklarını çakışmayacak şekilde ayırın."
                        ),
                    )
                )
    return out


# --------------------------------------------------------------------------
# genel giriş
# --------------------------------------------------------------------------
def forward_risks(
    students: list[Student],
    units: list[Unit],
    months: list[str],
    assignments: list[Assignment],
    custom_rules: list[CustomRule] | None = None,
    settings: dict | None = None,
) -> list[Risk]:
    """Kalan sezona dair bütün ucuz (aritmetik) riskler, tek listede.

    Yalnız AKTİF öğrenciler hesaba katılır: ayrılan öğrenci yeni aylara
    atanmaz, onun için risk üretmek gürültüdür.
    """
    active = [s for s in students if getattr(s, "active", True)]
    rules = [r for r in (custom_rules or []) if r.active]
    out: list[Risk] = []

    for f in season_capacity_findings(active, units, months, assignments):
        out.append(
            Risk(level=f.level, category=CAT_QUOTA, group=f.group,
                 message=f.message)
        )
    for f in season_requirement_findings(
        active, units, months, assignments, settings
    ):
        out.append(
            Risk(level=f.level, category=CAT_REQUIREMENT, group=f.group,
                 message=f.message)
        )
    out += _risk_total_quota(active, units, months, assignments)
    out += _risk_unit_runway(active, units, months, assignments)
    out += _risk_fixed_assignments(active, units, months, assignments, rules)
    out += _risk_together(active, units, months, assignments, rules)
    out += _risk_contradictions(active, months, rules)

    # hatalar önce, sonra kategori/grup — panelde okunur sıra
    out.sort(key=lambda r: (r.level != ERROR, r.category, r.group))
    return out


def risk_counts(risks: list[Risk]) -> tuple[int, int]:
    """(hata, uyarı) sayısı — Ana Sayfa rozeti için."""
    errors = sum(1 for r in risks if r.level == ERROR)
    return errors, len(risks) - errors


# --------------------------------------------------------------------------
# deneme çözümü (yavaş, butonla)
# --------------------------------------------------------------------------
def deep_feasibility(
    students: list[Student],
    units: list[Unit],
    months: list[str],
    assignments: list[Assignment],
    custom_rules: list[CustomRule] | None = None,
    settings: dict | None = None,
    groups: list[int] | None = None,
    on_group=None,
) -> list[DeepResult]:
    """Kalan ayları GERÇEKTEN çözmeyi dener; hiçbir şey kaydetmez.

    Aritmetik kontroller kesin çelişkileri bulur ama kombinatorik çıkmazları
    (ör. madde 20 peş peşe yoğun/hafif yasağı ile kontenjanların birlikte
    tıkanması) göremez. Bu deneme, çözücünün kendisini kullandığı için o
    sorulara kesin cevap verir.

    ortools burada, ilk çağrıda yüklenir (bkz. modül başlığı).
    """
    from .solver import solve_season  # tembel: panel ortools yüklemesin

    active = [s for s in students if getattr(s, "active", True)]
    rules = [r for r in (custom_rules or []) if r.active]
    hedef = groups or sorted({s.group for s in active})
    out: list[DeepResult] = []
    for idx, g in enumerate(hedef, 1):
        if on_group:
            on_group(idx, len(hedef), g)
        g_students = [s for s in active if s.group == g]
        if not g_students:
            continue
        g_ids = {s.id for s in g_students}
        dolu = {a.month for a in assignments if a.student_id in g_ids}
        kalan = [m for m in months if m not in dolu]
        if not kalan:
            out.append(
                DeepResult(group=g, months=[], status="ATLANDI",
                           reasons=["Bu grubun tüm ayları zaten üretilmiş."])
            )
            continue
        g_units = [u for u in units if u.group in (0, g)]
        res = solve_season(
            g_students, g_units, months, kalan, assignments,
            settings=settings, custom_rules=rules,
        )
        reasons = list(getattr(res, "infeasible_reasons", []) or [])
        suggestions: list[str] = []
        if res.status not in ("OPTIMAL", "FEASIBLE"):
            # "Çözülemiyor" yeterli değil: NEDEN ve NE YAPMALI söyle.
            reasons, suggestions = explain_infeasible_group(
                g, active, units, months, assignments, rules, settings,
                fallback=reasons,
            )
        out.append(
            DeepResult(
                group=g,
                months=kalan,
                status=res.status,
                reasons=reasons,
                suggestions=suggestions,
            )
        )
    return out


def _split_reason(message: str) -> tuple[str, str]:
    """Risk mesajını (sebep, öneri) olarak böler.

    forward_risks/capacity mesajları '... . Çözüm: ...' kalıbıyla yazılı.
    Kalıp yoksa tüm mesaj sebep, öneri boş.
    """
    for sep in (". Çözüm: ", " Çözüm: ", "Çözüm: "):
        if sep in message:
            sebep, oneri = message.split(sep, 1)
            return sebep.strip(" ."), oneri.strip()
    return message.strip(), ""


def explain_infeasible_group(
    group: int,
    students: list[Student],
    units: list[Unit],
    months: list[str],
    assignments: list[Assignment],
    custom_rules: list[CustomRule],
    settings: dict | None,
    fallback: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Bir grup neden çözülemiyor + ne yapmalı. Dönüş: (sebepler, öneriler).

    İki kaynak birleşir:
      1) forward_risks o gruba scope'landığında zaten somut aritmetik sebebi
         ("FTR.ÜNİT uygun 7 < gereken 10") ve "Çözüm: ..." önerisini üretir.
      2) Aritmetik sebep yoksa (saf kombinatorik çıkmaz) ilk çözülemeyen ay
         solve_month teşhis moduyla çözülür; hangi kural ailesinin tıkadığı
         (_REASON_LABELS) sebep olarak verilir.
    Hiçbiri sonuç vermezse `fallback` (solver'ın genel mesajı) kullanılır.
    """
    g_students = [
        s for s in students
        if s.group == group and getattr(s, "active", True)
    ]

    reasons: list[str] = []
    suggestions: list[str] = []

    # 1) aritmetik riskler — yalnız bu grubu ilgilendiren HATA'lar
    for r in forward_risks(
        g_students, units, months, assignments, custom_rules, settings
    ):
        if r.level != ERROR or r.group not in (0, group):
            continue
        sebep, oneri = _split_reason(r.message)
        if sebep not in reasons:
            reasons.append(sebep)
        if oneri and oneri not in suggestions:
            suggestions.append(oneri)

    if reasons:
        return reasons, suggestions

    # 2) kombinatorik çıkmaz — ilk çözülemeyen ayı teşhis et
    diag = _month_diagnosis(
        group, g_students, units, months, assignments, custom_rules, settings
    )
    if diag:
        return diag, []

    return list(fallback or []), []


def _month_diagnosis(
    group, g_students, units, months, assignments, custom_rules, settings
) -> list[str]:
    """İlk tıkanan ayı bulup solve_month teşhisiyle açıklar (ilerlemeli).

    Sezon çözücüsü çıkmazı aylar ARASINDA yaşanır (ör. madde 20 peş peşe
    yoğun yasağı); tek bir ayı yalıtık çözmek bunu göremez. Bu yüzden aylar
    sırayla çözülür ve her çözülen ay geçmişe eklenir — ilk INFEASIBLE ay,
    çıkmazın görünür olduğu aydır. solve_month INFEASIBLE olunca kendini
    _diagnostic=True ile yeniden çağırıp unsat core'dan kural-ailesi
    açıklaması döndürür (solver.py).

    Sezon INFEASIBLE ise tam atama yoktur, dolayısıyla ilerlemeli çözüm bir
    ayda mutlaka tıkanır.
    """
    from .models import Assignment as _A
    from .solver import solve_month

    g_ids = {s.id for s in g_students}
    dolu = {a.month for a in assignments if a.student_id in g_ids}
    g_units = [u for u in units if u.group in (0, group)]
    history = list(assignments)
    for m in months:
        if m in dolu:
            continue
        res = solve_month(
            g_students, g_units, m, history,
            settings=settings, custom_rules=custom_rules,
        )
        if res.status == "INFEASIBLE":
            sebepler = list(res.infeasible_reasons or [])
            return [f"{m} ayı çözülemiyor. " + s for s in sebepler] or [
                f"{m} ayı çözülemiyor: kurallar birlikte sağlanamıyor."
            ]
        if not res.ok:
            return []  # UNKNOWN: süre yetmedi, kesin çözümsüz demek değil
        # çözülen ayı geçmişe ekle ki sonraki aylar bu seçime göre denensin
        history = history + [
            _A(student_id=sid, month=m, unit_id=uid)
            for sid, uid in res.assignments.items()
        ]
    return []
