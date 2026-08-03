"""Ayarlar sekmesi — sayısal "ağırlık" kutularının kaldırılması.

Sekiz ağırlık kutusu iki bakımdan yanlıştı: üçü Kapasite Planı'ndaki
politika seçiminin, biri Gereksinimler'in gücünden başka bir şey değildi
(aynı şeyi iki ekrandan ayarlatmak), ve adları hâlâ v1'in sabit branş
listesinden söz ediyordu.

Sayılar veride ve çözücüde DURUYOR — kaldırılan yalnız düzenleme arayüzü.
Bu dosya ikisini birden bekçiliyor.
"""
import ast
import inspect

from rotasyon.models import DEFAULT_SETTINGS


def _string_constants(fn) -> str:
    """Fonksiyonun KULLANICIYA giden metinleri.

    Yorumlar ve DOCSTRING hariç: docstring geliştiriciye yazılır ve burada
    tam da kaldırılan eski ifadeden söz ediyor olabilir.
    """
    govde = ast.parse(inspect.getsource(fn).lstrip()).body[0].body
    if (govde and isinstance(govde[0], ast.Expr)
            and isinstance(govde[0].value, ast.Constant)):
        govde = govde[1:]
    return " ".join(
        n.value
        for st in govde for n in ast.walk(st)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ).lower()


# ---- arayüz: sayısal kutular gitmeli ----

def test_settings_tab_has_no_weight_number_inputs():
    """Ağırlık kutuları geri gelmesin."""
    from ui import data_management

    src = inspect.getsource(data_management._settings_tab)
    assert "number_input" not in src
    assert "set_w_" not in src


def test_weight_editor_labels_are_gone():
    """Eski _WEIGHT_LABELS sözlüğü kaldırılmış olmalı."""
    from ui import data_management

    assert not hasattr(data_management, "_WEIGHT_LABELS")


def test_stale_v1_wording_is_gone():
    """"Zorunlu branşları erken karşılama" v1 diliydi; motor gereksinimlere
    geçtiği hâlde ekran hâlâ sabit branş listesinden söz ediyordu."""
    from ui.data_management import _solver_preferences

    metin = _string_constants(_solver_preferences)
    assert "zorunlu branş" not in metin
    assert "cerrahi/dahili" not in metin


def test_preferences_point_at_the_real_screens():
    """Her tercih, gerçekte nereden ayarlandığını söylemeli."""
    from ui.data_management import _SOLVER_PREFERENCES

    sayfalar = {p for _, _, p, _ in _SOLVER_PREFERENCES}
    assert {"kapasite-plani", "gereksinimler", "veri-yonetimi"} <= sayfalar


def test_every_preference_row_is_complete():
    from ui.data_management import _SOLVER_PREFERENCES

    assert len(_SOLVER_PREFERENCES) >= 6
    for simge, aciklama, sayfa, etiket in _SOLVER_PREFERENCES:
        assert simge and aciklama and sayfa and etiket
        assert len(aciklama) > 20


# ---- motor: ağırlıklar YAŞAMAYA devam etmeli ----

def test_engine_still_reads_every_weight():
    """Arayüz kalktı diye motordan da düşmediğinin kanıtı.

    Ağırlıklardan biri sessizce ölürse çözücü o tercihi hiç gözetmez ve
    bunu kimse fark etmez — bu test o yüzden var.
    """
    from rotasyon import solver

    src = inspect.getsource(solver)
    for key in DEFAULT_SETTINGS["solver"]["weights"]:
        assert f'"{key}"' in src, key


def test_defaults_keep_intensive_surplus_below_pool_balance():
    """Eski ekranın uyardığı tuzak: bu sıra bozulursa çözücü eşit dağılımı
    bozup öğrencileri yoğun birimlere yığar. Kutular kalktığına göre
    varsayılanların doğruluğu artık tek güvence."""
    w = DEFAULT_SETTINGS["solver"]["weights"]
    assert w["intensive_surplus"] < w["pool_balance"]


def test_solver_tolerates_a_season_without_saved_weights():
    """Kullanıcının sezonlarında settings.json bile yok — varsayılana düşmeli."""
    from rotasyon.models import Student, Unit, BRANCH_DIGER
    from rotasyon.solver import solve_month

    units = [
        Unit(name=n, group=1, quota=3, branch_category=BRANCH_DIGER, pool=True)
        for n in ("ACİL", "EKG")
    ]
    students = [
        Student(full_name=f"Ö{i}", gender="K", group=1, class_name="A")
        for i in range(3)
    ]
    ayarlar = {
        "months": ["EYLÜL"],
        "season_requirements": [],
        "solver": {"time_limit_seconds": 5, "num_workers": 1, "weights": {}},
    }
    r = solve_month(students, units, "EYLÜL", [], ayarlar)
    assert r.ok, r.infeasible_reasons
