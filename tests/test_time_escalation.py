"""Süre yetmediğinde kademeli otomatik deneme.

Kullanıcıya "çözüm süresini artırın" demek teknik bilgi ister: ne kadar
artıracağını, hangi ayarın hangisi olduğunu bilemez. Bunun yerine uygulama
sonuç alamadığında süreyi kendiliğinden büyütüp yeniden dener ve bunu
kullanıcıya "daha uzun deniyor" diye gösterir.

Kritik ayrım: **INFEASIBLE'da asla tekrar denenmez.** Çözümsüzlük matematiksel
bir kanıttır, daha uzun beklemek sonucu değiştirmez — yalnız kullanıcıyı
bekletir.
"""
from rotasyon.models import (
    DEFAULT_SETTINGS,
    Requirement,
    SCOPE_ALL,
    Student,
    Unit,
    BRANCH_DIGER,
)
from rotasyon.solver import solve_month, solve_season

MONTHS = ["EYLÜL", "EKİM"]


def _settings(ay=1, sezon=1):
    return {
        "months": MONTHS,
        "season_requirements": [],
        "solver": {
            "time_limit_seconds": ay,
            "season_time_limit_seconds": sezon,
            "num_workers": 1,
            "weights": dict(DEFAULT_SETTINGS["solver"]["weights"]),
        },
    }


def U(name, quota=5, **kw):
    return Unit(name=name, group=1, quota=quota,
                branch_category=BRANCH_DIGER, **kw)


def S(i):
    return Student(full_name=f"Ö{i}", gender="K", group=1, class_name="A")


# ---- varsayılanlar ----

def test_defaults_are_generous_enough_for_an_old_machine():
    """Başlangıç süreleri ölçülen değerin belirgin üstünde olmalı.

    Ölçüm bu makinede en iyi çözümün 1-2 sn'de bulunduğunu gösterdi; uygulama
    ESKİ bir bilgisayarda koşacak ve CP-SAT'ın limiti duvar saatiyle işliyor
    (yavaş makine aynı sürede daha az arama yapar).
    """
    s = DEFAULT_SETTINGS["solver"]
    assert s["time_limit_seconds"] >= 8
    assert s["season_time_limit_seconds"] >= 90


# ---- INFEASIBLE'da tekrar denenmemeli ----

def test_infeasible_season_is_not_retried():
    """Çözümsüzlük kanıtlıysa uzatmak boşuna — hemen dönmeli.

    Kontenjan öğrenci sayısının altında: matematiksel olarak çözümsüz.
    Kademeli deneme çalışıyor olsaydı bu çağrı 1+2+4 = 7 sn sürerdi.
    """
    import time

    units = [U("A", quota=1)]
    students = [S(i) for i in range(5)]
    t = time.perf_counter()
    res = solve_season(students, units, MONTHS, MONTHS, [], _settings(sezon=1))
    gecen = time.perf_counter() - t
    assert res.status == "INFEASIBLE"
    assert gecen < 1.5, f"çözümsüzlükte tekrar denenmiş ({gecen:.1f}s)"


def test_infeasible_month_is_not_retried():
    import time

    units = [U("A", quota=1)]
    students = [S(i) for i in range(5)]
    t = time.perf_counter()
    res = solve_month(students, units, "EYLÜL", [], _settings(ay=1))
    gecen = time.perf_counter() - t
    assert res.status == "INFEASIBLE"
    assert gecen < 1.5, f"çözümsüzlükte tekrar denenmiş ({gecen:.1f}s)"


# ---- kolay durumda uzatma tetiklenmemeli ----

def test_easy_season_does_not_escalate():
    """Çözüm hemen bulunuyorsa on_retry HİÇ çağrılmamalı."""
    cagrildi = []
    units = [U("A"), U("B"), U("C")]
    students = [S(i) for i in range(3)]
    res = solve_season(
        students, units, MONTHS, MONTHS, [], _settings(sezon=30),
        on_retry=lambda *a: cagrildi.append(a),
    )
    assert res.status in ("OPTIMAL", "FEASIBLE"), res.infeasible_reasons
    assert cagrildi == [], "kolay sezonda gereksiz uzatma yapıldı"


def test_on_retry_signature_is_usable():
    """on_retry(kademe, toplam, yeni_limit) — arayüz bunu metne çeviriyor."""
    import inspect

    from rotasyon.risk import deep_feasibility

    # deep_feasibility solve_season'a on_retry geçiriyor mu?
    src = inspect.getsource(deep_feasibility)
    assert "on_retry" in src


# ---- mesajlar teknik ayara YÖNLENDİRMEMELİ ----

def _metinler(modul):
    """Modüldeki KULLANICIYA GİDEN metinler (yorumlar hariç).

    Kaynağı düz metin olarak taramak yanıltıcı: "süreyi artırın DEMEmek için"
    diye açıklayan bir yorum da eşleşir. Yalnız string sabitlerine bakılır.
    """
    import ast
    import inspect

    agac = ast.parse(inspect.getsource(modul))
    return [
        n.value.lower()
        for n in ast.walk(agac)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


def test_unknown_message_does_not_tell_user_to_change_a_setting():
    """Kullanıcıya "süreyi artırın" denmemeli.

    Teknik bilgi ister: ne kadar artıracağını, hangi ayarın hangisi olduğunu
    bilemez. Mesaj bunun yerine YAPILABİLİR şeyleri söylemeli (kontenjana pay
    bırak, gereksinimi tercihe çevir).
    """
    from rotasyon import solver

    for m in _metinler(solver):
        assert "süreyi artır" not in m, m


def test_ui_unknown_branch_does_not_point_at_settings():
    from ui import violations

    for m in _metinler(violations):
        assert "çözüm süresini artır" not in m, m


def test_unknown_message_offers_concrete_actions():
    """Mesaj hem "çözümsüz değil" demeli hem ne yapılacağını söylemeli."""
    from rotasyon import solver

    hepsi = " ".join(_metinler(solver))
    assert "anlamına" in hepsi and "gelmez" in hepsi
    assert "tercih" in hepsi  # gereksinimi tercihe çevirme önerisi
    assert "pay" in hepsi     # kontenjana pay bırakma önerisi


def test_balanced_preset_matches_defaults():
    """Taze bir sezon "Dengeli" seçili görünmeli, "Kendi ayarım" değil.

    Hazır kademelerden biri varsayılanlarla birebir tutmazsa kullanıcı hiç
    dokunmadığı halde "kendi ayarım" görür ve kafası karışır.
    """
    from ui.data_management import _SABIR_SECENEKLERI

    v = DEFAULT_SETTINGS["solver"]
    beklenen = (v["time_limit_seconds"], v["season_time_limit_seconds"])
    assert _SABIR_SECENEKLERI["⚖️ Dengeli"] == beklenen


def test_presets_are_ordered_and_sane():
    from ui.data_management import _SABIR_SECENEKLERI

    ay = [v[0] for v in _SABIR_SECENEKLERI.values()]
    sezon = [v[1] for v in _SABIR_SECENEKLERI.values()]
    assert ay == sorted(ay), "kademeler artan sırada olmalı"
    assert sezon == sorted(sezon)
    # sezon limiti her zaman ay limitinden belirgin büyük (model çok daha büyük)
    assert all(s > a * 3 for a, s in _SABIR_SECENEKLERI.values())


def test_diagnosis_loop_does_not_escalate():
    """Sebep teşhisi kademeli beklememeli — yoksa analiz dakikalara çıkar.

    _month_diagnosis ayları tek tek çözerek döngü kurar. Her zor ayda 4× ve 8×
    beklemek (8 → 32 → 64 sn) analizi kullanılamaz hale getirir; teşhis zaten
    çözüm değil hangi kuralın tıkadığını arıyor.
    """
    import inspect

    from rotasyon.risk import _month_diagnosis

    src = inspect.getsource(_month_diagnosis)
    assert "escalate=False" in src


def test_escalate_flag_defaults_to_on_for_normal_generation():
    """Normal üretimde sabır AÇIK olmalı (eski makine sigortası)."""
    import inspect

    from rotasyon.solver import solve_month

    p = inspect.signature(solve_month).parameters["escalate"]
    assert p.default is True


def test_escalate_false_returns_quickly_on_unknown():
    """escalate=False verildiğinde tek denemeyle dönmeli."""
    import time

    # çözümsüz kurulum: INFEASIBLE zaten hızlı döner, burada asıl kontrol
    # imzanın kabul edilmesi ve davranışın bozulmaması
    units = [U("A", quota=1)]
    students = [S(i) for i in range(5)]
    t = time.perf_counter()
    res = solve_month(
        students, units, "EYLÜL", [], _settings(ay=1), escalate=False
    )
    assert res.status == "INFEASIBLE"
    assert time.perf_counter() - t < 1.5


def test_saved_time_outside_widget_range_does_not_crash_settings():
    """Aralık dışı kayıtlı süre Veri Yönetimi ekranını ÇÖKERTMEMELİ.

    Gerçek olay: bir sezonun settings.json'ında sezon limiti 2 sn kalmıştı;
    st.number_input min 10 olduğu için istisna fırlatıyor ve st.tabs tüm
    panelleri çalıştırdığından Veri Yönetimi'nin TAMAMI açılmıyordu —
    kullanıcı sayıyı düzeltmek için de oraya giremiyordu.
    """
    from ui.data_management import clamp

    assert clamp(2, 10, 600) == 10        # altta kalan kayıt
    assert clamp(9999, 10, 600) == 600    # üstte kalan kayıt
    assert clamp(90, 10, 600) == 90       # geçerli değer dokunulmaz
    assert clamp(0, 1, 120) == 1
