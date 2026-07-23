"""Ana Sayfa / Dashboard: dönem özeti, hızlı erişim, eksik veri uyarıları."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .common import groups_in, has_data, load_seed, seed_available


def _link(url_path: str, label: str, icon: str) -> None:
    """st.navigation sayfasına hızlı erişim bağlantısı."""
    pages = st.session_state.get("_pages", {})
    if url_path in pages:
        st.page_link(pages[url_path], label=label, icon=icon)


def render(store) -> None:
    st.header("🏥 Staj Rotasyonu")

    if not has_data(store):
        st.info(
            "Hoş geldiniz! Bu sezon henüz boş. Üç şekilde başlayabilirsiniz:"
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**📥 Öğrenci listesinden**")
            st.caption(
                "Sezon başında gelen SML öğrenci listesini yükleyin; "
                "sınıflar ve bölümler otomatik çözülür."
            )
            _link("excel", "Excel'den içe aktar", "📥")
        with c2:
            st.markdown("**✍️ Elle girerek**")
            st.caption("Öğrenci, birim ve sınıfları tek tek tanımlayın.")
            _link("veri-yonetimi", "Veri Yönetimi'ne git", "📋")
        with c3:
            st.markdown("**🧪 Örnek veriyle**")
            st.caption("Uygulamayı örnek dönem verisiyle deneyin.")
            if seed_available() and st.button("Örnek veriyle başla"):
                load_seed(store)
                st.rerun()
        st.divider()
        st.caption("İlk kez mi kullanıyorsunuz? Adım adım anlatım burada:")
        _link("yardim", "Yardım sayfasını aç", "❓")
        return

    students = store.load_students()
    units = store.load_units()
    assignments = store.load_assignments()
    months = store.load_settings()["months"]

    inactive = sum(1 for s in students if not s.active)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Öğrenci",
        len(students) - inactive,
        delta=f"-{inactive} ayrıldı" if inactive else None,
        delta_color="off",
    )
    c2.metric("Aktif Birim", sum(1 for u in units if u.active))
    c3.metric("Sınıf", len(store.load_classes()))
    c4.metric("Kayıtlı Atama", len(assignments))

    # Eksik veri uyarıları — kullanıcıyı doğru ekrana yönlendir
    missing_gender = [s.full_name for s in students if not s.gender and s.active]
    if missing_gender:
        st.warning(
            f"⚠️ {len(missing_gender)} öğrencinin cinsiyeti eksik; rotasyon "
            "oluşturmadan önce tamamlanmalı: "
            + ", ".join(missing_gender[:5])
            + ("..." if len(missing_gender) > 5 else "")
        )
        _link("veri-yonetimi", "Veri Yönetimi'nde tamamla", "📋")

    st.subheader("Ay bazında ilerleme")
    rows = []
    next_month = None
    for g in groups_in(students):
        # ayrılan (pasif) öğrenciler ilerleme paydasına girmez
        gids = {s.id for s in students if s.group == g and s.active}
        row = {"Grup": f"{g}. Grup"}
        for m in months:
            done = sum(
                1 for a in assignments if a.month == m and a.student_id in gids
            )
            row[m] = f"{done}/{len(gids)}" if done else "—"
            if done == 0 and next_month is None:
                next_month = m
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    st.subheader("Hızlı erişim")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _link(
            "rotasyon",
            f"Rotasyon oluştur{f' ({next_month})' if next_month else ''}",
            "🔄",
        )
    with c2:
        _link("kural-kontrolu", "Kural denetimi çalıştır", "🛡️")
    with c3:
        _link("excel", "Excel'e aktar", "📤")
    with c4:
        _link("yardim", "Yardım", "❓")
