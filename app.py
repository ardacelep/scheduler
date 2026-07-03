"""Staj Rotasyonu uygulaması — Streamlit girişi.

Çalıştırma: streamlit run app.py
"""
import streamlit as st

st.set_page_config(
    page_title="Staj Rotasyonu",
    page_icon="🏥",
    layout="wide",
)

from ui import dashboard, data_management, history, rotation, violations  # noqa: E402
from ui import excel_screen  # noqa: E402
from ui.common import get_manager  # noqa: E402

SCREENS = {
    "🏠 Ana Sayfa": dashboard.render,
    "📋 Veri Yönetimi": data_management.render,
    "🔄 Rotasyon Oluştur": rotation.render,
    "🕘 Öğrenci Geçmişi": history.render,
    "📊 Excel İçe/Dışa Aktarım": excel_screen.render,
    "🛡️ Kural Kontrolü": violations.render,
}


def _season_sidebar(manager) -> None:
    """Sezon seçici + yeni sezon oluşturma."""
    st.sidebar.divider()
    st.sidebar.subheader("📅 Sezon")
    seasons = manager.list_seasons()
    active = manager.active_season()
    if seasons:
        pick = st.sidebar.selectbox(
            "Aktif sezon",
            seasons,
            index=seasons.index(active) if active in seasons else 0,
        )
        if pick != active:
            manager.set_active(pick)
            st.rerun()
    with st.sidebar.expander("➕ Yeni sezon oluştur"):
        with st.form("new_season", clear_on_submit=True):
            name = st.text_input("Sezon adı", placeholder="örn. 2025-2026")
            copy_from = st.selectbox(
                "Birim ve sınıfları kopyala",
                ["(kopyalama)"] + seasons,
                help="Birim tanımları genelde sezondan sezona aynı kalır; "
                "öğrenci ve atamalar asla kopyalanmaz.",
            )
            if st.form_submit_button("Oluştur") and name.strip():
                try:
                    manager.create(
                        name.strip(),
                        copy_units_from=None
                        if copy_from == "(kopyalama)"
                        else copy_from,
                    )
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))


def main() -> None:
    st.sidebar.title("🏥 Staj Rotasyonu")
    choice = st.sidebar.radio("Ekranlar", list(SCREENS), label_visibility="collapsed")
    manager = get_manager()
    _season_sidebar(manager)
    st.sidebar.caption(
        "Hemşirelik öğrenci staj rotasyonlarını kurallara uygun ve otomatik "
        "planlar. Veriler `data/` klasöründe sezon bazında saklanır."
    )
    active = manager.active_season()
    if active:
        st.caption(f"📅 Aktif sezon: **{active}**")
    SCREENS[choice](manager.store())


if __name__ == "__main__":
    main()
