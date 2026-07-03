"""Staj Rotasyonu uygulaması — Streamlit girişi.

Çalıştırma: streamlit run app.py

Navigasyon st.navigation/st.Page ile kurulur: eski radio tabanlı menünün
uzun süren çözücü koşularında bıraktığı "çift ekran / silik menü" artefaktı
bu yapıda oluşmaz.
"""
import streamlit as st

st.set_page_config(
    page_title="Staj Rotasyonu",
    page_icon="🏥",
    layout="wide",
)

from ui import dashboard, data_management, history, rotation, violations  # noqa: E402
from ui import excel_screen  # noqa: E402
from ui.common import (  # noqa: E402
    create_season_with_units,
    get_manager,
    unit_source_options,
)


def _page(render_fn, url_path: str):
    """Ekran fonksiyonunu st.Page'in beklediği çağrılabilire sarar."""

    def runner():
        manager = get_manager()
        active = manager.active_season()
        if active:
            st.caption(f"📅 Aktif sezon: **{active}**")
        render_fn(manager.store())

    runner.__name__ = url_path.replace("-", "_")
    return runner


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
            source = st.selectbox(
                "Birimler nereden gelsin?",
                unit_source_options(seasons),
                index=max(len(seasons) - 1, 0),  # varsayılan: en son sezon
                help="Birim tanımları genelde sezondan sezona aynı kalır; "
                "sezondan kopyalamak en pratiğidir. Hiç sezon yoksa "
                "varsayılan katalog hazır bir başlangıç sunar. Öğrenci ve "
                "atamalar asla kopyalanmaz.",
            )
            if st.form_submit_button("Oluştur") and name.strip():
                try:
                    create_season_with_units(manager, name.strip(), source)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    if seasons:
        with st.sidebar.expander("🗑️ Sezon sil"):
            victim = st.selectbox("Silinecek sezon", seasons, key="del_season_pick")
            st.caption(
                "Sezon kalıcı silinmez; `data/trash/` klasörüne taşınır, "
                "gerekirse oradan geri alınabilir."
            )
            sure = st.checkbox(
                f"'{victim}' sezonunu ve TÜM verilerini silmek istiyorum",
                key="del_season_confirm",
            )
            if st.button("🗑️ Sil", disabled=not sure, key="del_season_btn"):
                manager.delete(victim)
                st.rerun()
    st.sidebar.caption(
        "Veriler `data/` klasöründe sezon bazında saklanır; her kayıtta "
        "otomatik yedek alınır."
    )


def main() -> None:
    pages = {
        "Planlama": [
            st.Page(
                _page(dashboard.render, "ana-sayfa"),
                title="Ana Sayfa", icon="🏠", url_path="ana-sayfa", default=True,
            ),
            st.Page(
                _page(rotation.render, "rotasyon"),
                title="Rotasyon Oluştur", icon="🔄", url_path="rotasyon",
            ),
            st.Page(
                _page(violations.render, "kural-kontrolu"),
                title="Kural Kontrolü", icon="🛡️", url_path="kural-kontrolu",
            ),
        ],
        "Veri": [
            st.Page(
                _page(data_management.render, "veri-yonetimi"),
                title="Veri Yönetimi", icon="📋", url_path="veri-yonetimi",
            ),
            st.Page(
                _page(history.render, "ogrenci-gecmisi"),
                title="Öğrenci Geçmişi", icon="🕘", url_path="ogrenci-gecmisi",
            ),
            st.Page(
                _page(excel_screen.render, "excel"),
                title="Excel İçe/Dışa Aktarım", icon="📊", url_path="excel",
            ),
        ],
    }
    # Dashboard'daki hızlı erişim bağlantıları (st.page_link) için sayfa
    # nesneleri paylaşılır
    st.session_state["_pages"] = {
        p.url_path: p for section in pages.values() for p in section
    }
    nav = st.navigation(pages)
    _season_sidebar(get_manager())
    nav.run()


if __name__ == "__main__":
    main()
