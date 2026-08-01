"""Kapasite Planı / Gereksinimler ekranlarında bayat widget durumu.

Bu iki ekranın widget'ları veriyi DOĞRUDAN yansıtır (politika seçici,
kontenjan, bekleyen form seçimleri). Streamlit, bir widget'ın `key`'i
session_state'te varsa o değeri `index=`/`value=`/`default=`'a TERCİH eder —
yani bayat bir oturum değeri:

  * Kapasite Planı'nda diske GERİ YAZILABİLİR (sessiz veri bozulması),
  * Gereksinimler formunda ölü öğrenci id'lerine / kaybolan birim adlarına
    işaret edebilir.

Tetikleyici gerçek: `SeasonManager.create(copy_units_from=...)` birimleri
AYNI id'lerle kopyalar, dolayısıyla `cap_pol_{grup}_{birim_id}` anahtarları
sezonlar arasında çakışır.
"""
import streamlit as st

from rotasyon.models import Student, Unit
from rotasyon.store import SeasonManager
from ui.common import clear_stale_state, data_fingerprint


def U(name="ACİL", quota=3, **flags):
    return Unit(name=name, group=1, quota=quota, **flags)


def S(i=0, group=1):
    return Student(full_name=f"Ö{i}", gender="K", group=group)


# ---- tetikleyici gerçek: kopyalanan sezonlar id paylaşır ----

def test_copied_season_shares_unit_ids(tmp_path):
    """Bu doğru olduğu için widget anahtarları sezonlar arası çakışabiliyor."""
    m = SeasonManager(tmp_path)
    a = m.create("A")
    a.save_units([U(pool=True)])
    b = m.create("B", copy_units_from="A")
    assert a.load_units()[0].id == b.load_units()[0].id


# ---- parmak izi iki sezonu ayırt ediyor mu? ----

def test_fingerprint_differs_when_policy_differs():
    """Aynı id, farklı politika → parmak izi FARKLI olmalı ki temizlik tetiklensin."""
    a = [U(pool=True)]
    b = [U(pool=True)]
    b[0].id = a[0].id          # kopyalanan sezon: aynı id
    b[0].pool, b[0].must_fill = False, True  # ama farklı politika
    assert data_fingerprint(a, []) != data_fingerprint(b, [])


def test_fingerprint_differs_when_quota_differs():
    a, b = [U(quota=3)], [U(quota=4)]
    b[0].id = a[0].id
    assert data_fingerprint(a, []) != data_fingerprint(b, [])


def test_fingerprint_differs_when_students_differ():
    units = [U()]
    assert (
        data_fingerprint(units, [S(0)]) != data_fingerprint(units, [S(0), S(1)])
    )


# ---- clear_stale_state gerçekten siliyor mu? ----

def _reset():
    for k in list(st.session_state):
        del st.session_state[k]


def test_capacity_widgets_cleared_when_data_changes():
    _reset()
    st.session_state["cap_pol_1_abc"] = "tam"
    st.session_state["cap_q_1_abc"] = 9
    st.session_state["baska_sey"] = "korunmali"

    clear_stale_state("_cap_fp", "fp1", ("cap_",))   # ilk kurulum
    assert st.session_state.get("cap_pol_1_abc") is None, "ilk çağrı temizler"

    st.session_state["cap_pol_1_abc"] = "havuz"
    assert clear_stale_state("_cap_fp", "fp1", ("cap_",)) is False
    assert st.session_state["cap_pol_1_abc"] == "havuz", "değişmediyse korunur"

    assert clear_stale_state("_cap_fp", "fp2", ("cap_",)) is True
    assert "cap_pol_1_abc" not in st.session_state, "veri değişti → atıldı"
    assert st.session_state["baska_sey"] == "korunmali", "ilgisiz anahtar kalır"


def test_requirement_form_state_cleared_but_list_buttons_kept():
    """Form durumu temizlenir; gereksinim listesi düğmeleri etkilenmez.

    Parmak izi bilerek yalnız öğrenci+birim üzerinden alınır — gereksinim
    eklemek/silmek yarı dolu formu silmesin.
    """
    _reset()
    clear_stale_state("_req_fp", "fp1", ("req_new_", "req_branch_"))
    st.session_state["req_new_name"] = "yarim ad"
    st.session_state["req_new_students"] = ["olu-id"]
    st.session_state["req_branch_pick"] = ["YOK OLAN BİRİM"]
    st.session_state["req_toggle_xyz"] = True  # liste düğmesi

    clear_stale_state("_req_fp", "fp2", ("req_new_", "req_branch_"))
    assert "req_new_name" not in st.session_state
    assert "req_new_students" not in st.session_state
    assert "req_branch_pick" not in st.session_state
    assert st.session_state["req_toggle_xyz"] is True


# ---- ekranlar temizliği GERÇEKTEN çağırıyor mu? ----

def test_both_v2_editors_call_clear_stale_state():
    """Kaynakta çağrı varsa regresyon fark edilir (import zinciri kırılmasın)."""
    import inspect

    from ui.v2 import capacity_plan, requirements_screen

    for mod, fp_key in (
        (capacity_plan, "_cap_fp"),
        (requirements_screen, "_req_fp"),
    ):
        src = inspect.getsource(mod)
        assert "clear_stale_state(" in src, mod.__name__
        assert fp_key in src, f"{mod.__name__}: {fp_key} yok"


def test_setup_wizard_holds_no_widget_state():
    """Sihirbaz salt-okunur: hiç widget anahtarı tutmaz, bayatlayamaz."""
    import inspect

    from ui.v2 import setup_wizard

    src = inspect.getsource(setup_wizard)
    assert "key=" not in src, "sihirbaz widget durumu tutmaya başlamış"
    assert "session_state" in src  # yalnız _pages okur
