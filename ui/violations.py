"""Kural İhlali Kontrol Paneli — mevcut atama tablosunun tam denetimi."""
from __future__ import annotations

import streamlit as st

from rotasyon.rules import check_all
from .common import show_violations


def render(store) -> None:
    st.header("🛡️ Kural Kontrolü")
    st.caption(
        "Kayıtlı tüm atamalar 19 kurala karşı denetlenir. Elle değişikliklerden "
        "sonra da çalıştırabilirsiniz."
    )
    students = store.load_students()
    units = store.load_units()
    assignments = store.load_assignments()
    months = store.load_settings()["months"]
    if not assignments:
        st.info("Henüz kayıtlı atama yok.")
        return
    custom_rules = store.load_custom_rules()
    violations = check_all(
        students, units, assignments, months, custom_rules=custom_rules
    )
    show_violations(violations, empty_message="Tüm atamalar kurallara uygun. ✅")
