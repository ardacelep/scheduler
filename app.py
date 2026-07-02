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
from ui.common import get_store  # noqa: E402

SCREENS = {
    "🏠 Ana Sayfa": dashboard.render,
    "📋 Veri Yönetimi": data_management.render,
    "🔄 Rotasyon Oluştur": rotation.render,
    "🕘 Öğrenci Geçmişi": history.render,
    "📊 Excel İçe/Dışa Aktarım": excel_screen.render,
    "🛡️ Kural Kontrolü": violations.render,
}


def main() -> None:
    st.sidebar.title("🏥 Staj Rotasyonu")
    choice = st.sidebar.radio("Ekranlar", list(SCREENS), label_visibility="collapsed")
    st.sidebar.caption(
        "Hemşirelik öğrenci staj rotasyonlarını kurallara uygun ve otomatik "
        "planlar. Veriler `data/` klasöründe saklanır."
    )
    SCREENS[choice](get_store())


if __name__ == "__main__":
    main()
