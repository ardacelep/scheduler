"""Doldurma politikası — birimin bir aydaki rolü, tek seçim olarak.

Veri modelinde bir birimin doldurulma davranışı DÖRT ayrı boolean'a dağılmış
durumda (`must_fill`, `single_slot`, `pool`, `reserve`). Bunlar mantıken
birbirini dışlar — bir birim aynı anda hem "her ay tam dolmalı" hem "yalnız
gerekirse kullanılsın" olamaz — ama veri modeli bunu engellemiyor ve kullanıcı
dört kutucuğu tek tek işaretlemek zorunda kalıyor.

Bu modül aynı veri üzerinde **tek seçimlik** bir görünüm sunar: her birimin bir
politikası vardır, politikayı değiştirmek dört bayrağı tutarlı biçimde yazar.
Şema değişikliği YOK — v1 ekranları aynı bayrakları görmeye devam eder.

Politikaların motordaki karşılığı (bkz. solver.py):

* `tam`      — SERT kısıt: `doluluk == kontenjan` her ay (madde 17).
* `mumkunse` — YUMUŞAK: birim boş kalırsa `single_slot_fill` (50) cezası.
* `havuz`    — YUMUŞAK: havuz birimleri arasındaki doluluk farkı küçültülür
               (`pool_balance`, 5) — "kalanlar eşit dağılsın".
* `yedek`    — YUMUŞAK: her yerleştirme `reserve_use` (15) cezalı, yani
               yalnız başka çare kalmayınca kullanılır.
* `serbest`  — Hiçbir tercih yok; kontenjan sınırı dışında serbest.
"""
from __future__ import annotations

from dataclasses import dataclass, field

POLICY_MUST_FILL = "tam"
POLICY_PREFER_FILL = "mumkunse"
POLICY_POOL = "havuz"
POLICY_RESERVE = "yedek"
POLICY_FREE = "serbest"

# Ekranda gösterilecek sıra: en katıdan en gevşeğe
POLICIES = (
    POLICY_MUST_FILL,
    POLICY_PREFER_FILL,
    POLICY_POOL,
    POLICY_RESERVE,
    POLICY_FREE,
)

POLICY_LABELS = {
    POLICY_MUST_FILL: "Tam dolmalı",
    POLICY_PREFER_FILL: "Mümkünse dolsun",
    POLICY_POOL: "Havuz — kalanlar eşit dağılsın",
    POLICY_RESERVE: "Yedek — yalnız gerekirse",
    POLICY_FREE: "Serbest",
}

POLICY_HELP = {
    POLICY_MUST_FILL: "Her ay kontenjanı kadar öğrenci bulunmak ZORUNDA. "
    "Bulunamazsa o ay üretilemez. Kesin kişi sayısı isteyen birimler için.",
    POLICY_PREFER_FILL: "Boş kalmaması tercih edilir; çözücü önce buraları "
    "doldurur ama gerekirse boş bırakabilir.",
    POLICY_POOL: "Zorunluluklar karşılandıktan sonra KALAN öğrenciler bu "
    "birimlere olabildiğince eşit dağıtılır.",
    POLICY_RESERVE: "Normalde kullanılmaz; yalnız başka yer kalmadığında "
    "öğrenci verilir (elle tuttuğunuz tablodaki gri/yedek birimler).",
    POLICY_FREE: "Özel bir tercih yok. Kontenjanı aşılmaz, o kadar.",
}

POLICY_ICONS = {
    POLICY_MUST_FILL: "🔒",
    POLICY_PREFER_FILL: "🎯",
    POLICY_POOL: "⚖️",
    POLICY_RESERVE: "🅿️",
    POLICY_FREE: "○",
}


def policy_of(unit) -> str:
    """Birimin mevcut bayraklarından politikasını okur.

    Bayraklar çakışıyorsa (eski veride olabilir; örn. katalogdaki FTR.ÜNİT hem
    `must_fill` hem `single_slot`) en KATI olan kazanır — çözücüde de fiilen
    öyle davranır: `must_fill` zaten doluluğu kontenjana sabitlediği için
    `single_slot` cezası hiç devreye girmez.
    """
    if unit.must_fill:
        return POLICY_MUST_FILL
    if unit.reserve:
        return POLICY_RESERVE
    if unit.pool:
        return POLICY_POOL
    if unit.single_slot:
        return POLICY_PREFER_FILL
    return POLICY_FREE


def apply_policy(unit, policy: str) -> bool:
    """Politikayı birime yazar (dört bayrağı tutarlı hale getirir).

    Dönüş: bir şey değiştiyse True. Bilinmeyen politika sessizce yok sayılır.
    """
    if policy not in POLICIES:
        return False
    before = (unit.must_fill, unit.single_slot, unit.pool, unit.reserve)
    unit.must_fill = policy == POLICY_MUST_FILL
    unit.single_slot = policy == POLICY_PREFER_FILL
    unit.pool = policy == POLICY_POOL
    unit.reserve = policy == POLICY_RESERVE
    return before != (unit.must_fill, unit.single_slot, unit.pool, unit.reserve)


@dataclass
class PolicyBucket:
    """Bir politikadaki birimlerin özeti."""

    policy: str
    unit_count: int = 0
    quota_total: int = 0


@dataclass
class CapacityPlan:
    """Bir grubun aylık kapasite tablosu — "kim nereye sığıyor" matematiği."""

    group: int
    student_count: int
    buckets: dict[str, PolicyBucket] = field(default_factory=dict)
    active_quota_total: int = 0
    warnings: list[str] = field(default_factory=list)
    # Uyarı DEĞİL, durum bildirimi: kurulumda bir yanlış yok ama kullanıcının
    # bilmesi gereken bir sonuç var. Ayrı tutulur çünkü uyarılar kurulum
    # sihirbazının adım durumunu "sorun var"a çeviriyor.
    notes: list[str] = field(default_factory=list)

    @property
    def must_fill_total(self) -> int:
        """Her ay KESİN olarak dolacak kişi sayısı."""
        return self.buckets[POLICY_MUST_FILL].quota_total

    @property
    def remaining(self) -> int:
        """Zorunlu dolan birimlerden sonra dağıtılacak öğrenci sayısı."""
        return self.student_count - self.must_fill_total

    @property
    def balance(self) -> int:
        """Aktif kontenjan − öğrenci sayısı (0 = tam oturur)."""
        return self.active_quota_total - self.student_count

    @property
    def pool_per_unit(self) -> float | None:
        """Havuz birimi başına ortalama öğrenci (yaklaşık).

        "Mümkünse dolsun" birimleri de kalandan pay alır; bu yüzden önce
        onların her birine birer kişi ayrılmış varsayılır (çözücünün fiilen
        yaptığı da budur: single_slot cezası 50, havuz dengesi 5).
        """
        pool = self.buckets[POLICY_POOL]
        if not pool.unit_count:
            return None
        prefer = self.buckets[POLICY_PREFER_FILL]
        kalan = self.remaining - min(prefer.unit_count, prefer.quota_total)
        return max(0.0, kalan) / pool.unit_count


def group_capacity_plan(units, students, group) -> CapacityPlan:
    """Bir grubun kapasite planını hesaplar (aktif birim + aktif öğrenci)."""
    g_units = [u for u in units if u.group in (0, group) and u.active]
    n_students = sum(
        1
        for s in students
        if s.group == group and getattr(s, "active", True)
    )
    buckets = {p: PolicyBucket(policy=p) for p in POLICIES}
    for u in g_units:
        b = buckets[policy_of(u)]
        b.unit_count += 1
        b.quota_total += u.quota

    plan = CapacityPlan(
        group=group,
        student_count=n_students,
        buckets=buckets,
        active_quota_total=sum(u.quota for u in g_units),
    )
    plan.warnings = _warnings(plan)
    plan.notes = _notes(plan)
    return plan


def _notes(plan: CapacityPlan) -> list[str]:
    """Sorun değil ama sonucu olan durumlar.

    "Toplam kontenjan = öğrenci sayısı" bir zamanlar UYARIYDI: uygulama
    birimleri sabit alıp öğrencileri onlara yerleştirdiği için sıfır boşluk
    riskli görünüyordu. Yeni modelde kontenjanlar zaten öğrenci sayısına göre
    belirleniyor — tam oturmak HEDEF, kusur değil. (Kullanıcının elle
    hazırladığı rotasyonlar da böyle: 36 öğrenci, 36 yer.)

    Sıfır boşluğun gerçek sonucu her birimin her ay dolmak zorunda kalması.
    Bunun bir yeri tıkayıp tıkamadığı tahminle değil, birim birim
    hesaplanarak söylenir (capacity.season_capacity_findings): "bu birim
    kalan 8 ayda 8 farklı uygun öğrenci ister, uygun 5 kişi var".
    """
    out: list[str] = []
    if not plan.student_count:
        return out
    if plan.balance == 0:
        out.append(
            f"Toplam kontenjan öğrenci sayısına tam eşit ({plan.student_count})"
            " — her birim her ay dolacak, boş yer kalmayacak. Cinsiyet "
            "kısıtlı birimler de her ay dolmak zorunda kalır; bir yeri "
            "tıkıyorsa Kural Kontrolü birimi adıyla söyler."
        )
    return out


def _warnings(plan: CapacityPlan) -> list[str]:
    """Kullanıcının kurulumu kaydetmeden önce görmesi gereken çelişkiler."""
    out: list[str] = []
    n = plan.student_count
    if not n:
        return out
    tam = plan.must_fill_total

    if tam > n:
        out.append(
            f"“Tam dolmalı” birimler her ay {tam} öğrenci istiyor ama grupta "
            f"{n} öğrenci var. Bu haliyle hiçbir ay üretilemez — kontenjanları "
            "düşürün ya da bazı birimleri “Mümkünse dolsun” yapın."
        )
    elif tam == n and n:
        out.append(
            f"“Tam dolmalı” birimler grubun tamamını ({n} öğrenci) tüketiyor; "
            "diğer birimlere kimse kalmıyor. Muhtemelen istediğiniz bu değil."
        )

    if plan.balance < 0:
        out.append(
            f"Toplam aktif kontenjan ({plan.active_quota_total}) öğrenci "
            f"sayısının ({n}) altında — {-plan.balance} öğrenciye yer yok. "
            "Kontenjan artırın veya birim aktifleştirin."
        )

    if plan.remaining > 0 and not plan.buckets[POLICY_POOL].unit_count:
        out.append(
            f"Dağıtılacak {plan.remaining} öğrenci var ama hiç “Havuz” birimi "
            "yok. Kalanların eşit dağılması için en az birkaç birimi havuz "
            "yapın."
        )
    return out
