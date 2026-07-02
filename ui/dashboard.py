"""Ana Sayfa / Dashboard: dönem özeti ve hızlı başlangıç."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .common import groups_in, has_data, load_seed, seed_available


def render(store) -> None:
    st.header("🏥 Staj Rotasyonu — Ana Sayfa")

    if not has_data(store):
        st.info(
            "Hoş geldiniz! Başlamak için Veri Yönetimi ekranından öğrenci ve "
            "birimleri girin, Excel ekranından mevcut dosyanızı içe aktarın "
            "veya örnek veriyle deneyin."
        )
        if seed_available() and st.button(
            "📥 Örnek veriyle başla (referans Excel'den)", type="primary"
        ):
            load_seed(store)
            st.rerun()
        return

    students = store.load_students()
    units = store.load_units()
    assignments = store.load_assignments()
    months = store.load_settings()["months"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Öğrenci", len(students))
    c2.metric("Aktif Birim", sum(1 for u in units if u.active))
    c3.metric("Sınıf", len(store.load_classes()))
    c4.metric("Kayıtlı Atama", len(assignments))

    st.subheader("Ay bazında ilerleme")
    rows = []
    for g in groups_in(students):
        gids = {s.id for s in students if s.group == g}
        row = {"Grup": f"{g}. Grup"}
        for m in months:
            done = sum(1 for a in assignments if a.month == m and a.student_id in gids)
            row[m] = f"{done}/{len(gids)}" if done else "—"
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(
        "Yeni ay ataması için soldan **Rotasyon Oluştur** ekranını, mevcut "
        "atamaları denetlemek için **Kural Kontrolü** ekranını kullanın."
    )
