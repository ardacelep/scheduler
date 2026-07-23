"""Öğrenci Geçmişi ekranı (madde 16)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from rotasyon.queries import student_history
from .common import gender_label


def render(store) -> None:
    st.header("🕘 Öğrenci Geçmişi")
    students = store.load_students()
    if not students:
        st.info("Henüz öğrenci yok.")
        return
    units = store.load_units()
    assignments = store.load_assignments()
    months = store.load_settings()["months"]

    options = {
        f"{s.full_name} ({s.group}. grup, {s.class_name})": s
        for s in sorted(students, key=lambda s: (s.group, s.full_name))
    }
    pick = st.selectbox("Öğrenci", list(options))
    s = options[pick]

    c1, c2, c3 = st.columns(3)
    c1.metric("Cinsiyet", gender_label(s.gender))
    c2.metric("Sınıf", s.class_name or "-")
    c3.metric("Grup", f"{s.group}. grup")
    if s.note:
        st.warning(f"📌 Özel not: {s.note}")
    if s.dis_exempt:
        st.caption("🦷 Diş Poliklinik muafiyeti var (madde 9).")

    hist = student_history(s.id, assignments, months, {u.id: u for u in units})
    if not hist:
        st.info("Bu öğrenciye ait atama yok.")
        return
    df = pd.DataFrame(hist, columns=["Ay", "Birim", "Gün Notu"])
    st.dataframe(df, width="stretch", hide_index=True)
    st.caption(f"Toplam {len(hist)} ay atanmış.")
