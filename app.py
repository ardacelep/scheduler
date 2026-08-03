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

from ui import dashboard, data_management, history, violations  # noqa: E402
from ui import excel_screen, help as help_screen  # noqa: E402
from ui import season_board, season_grid  # noqa: E402
from ui.v2 import (  # noqa: E402
    capacity_plan,
    custom_rules,
    requirements_screen,
    setup_wizard,
)
from ui.common import (  # noqa: E402
    UNITS_CATALOG,
    create_season_with_units,
    get_manager,
    unit_source_options,
)


def _page(render_fn, url_path: str):
    """Ekran fonksiyonunu st.Page'in beklediği çağrılabilire sarar.

    Aktif sezon burada YAZILMAZ: kenar çubuğundaki sezon seçici aynı bilgiyi
    zaten gösteriyor ve her sayfanın tepesinde tekrarlamak başlığı aşağı itip
    ekranı gürültülendiriyordu.
    """

    def runner():
        render_fn(get_manager().store())

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
            options = unit_source_options(seasons)
            default_idx = (
                options.index(UNITS_CATALOG) if UNITS_CATALOG in options else 0
            )
            source = st.selectbox(
                "Birimler nereden gelsin?",
                options,
                index=default_idx,  # varsayılan: hazır birim kataloğu
                help="Varsayılan olarak hazır birim kataloğu gelir. Dilerseniz "
                "önceki bir sezonun birimlerini de kopyalayabilirsiniz "
                "(öğrenci ve atamalar asla kopyalanmaz).",
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
    st.sidebar.divider()
    st.sidebar.checkbox(
        "🕘 Geçmişe dönük uyarıları göster",
        value=True,
        key="show_past_violations",
        help="Bir birimin kontenjanını düşürmek gibi sonradan yapılan "
        "değişiklikler, dokunmadığınız geçmiş ayları da ihlal gösterebilir. "
        "Bu ihlaller yeni kaydı engellemez; gürültü olmaması için buradan "
        "gizleyebilirsiniz. Tüm ekranlarda geçerlidir.",
    )


def main() -> None:
    # Menü üç bölüm: sezonu KURMA işleri bir arada, sezonu YÜRÜTME işleri bir
    # arada, ara sıra kullanılanlar en altta. (Eski yapıda "Rotasyon Oluştur"
    # Yıllık Tablo ile, "Grup Dağılımı" Kapasite Planı ile örtüşüyordu; ikisi
    # de kaldırıldı, işlevleri kalan ekranlara taşındı.)
    pages = {
        "Kurulum": [
            st.Page(
                _page(setup_wizard.render, "kurulum"),
                title="Kurulum Sihirbazı", icon="🧭", url_path="kurulum",
            ),
            st.Page(
                _page(data_management.render, "veri-yonetimi"),
                title="Veri Yönetimi", icon="📋", url_path="veri-yonetimi",
            ),
            st.Page(
                _page(capacity_plan.render, "kapasite-plani"),
                title="Kapasite Planı", icon="📦", url_path="kapasite-plani",
            ),
            st.Page(
                _page(requirements_screen.render, "gereksinimler"),
                title="Gereksinimler", icon="🎯", url_path="gereksinimler",
            ),
            # Gereksinimler'in hemen altında: ikisi de sezona özgü kural
            # tanımıdır. Gereksinimler bir öğrenci kümesine ("herkes bir
            # yoğun bakım görsün"), Özel Kurallar adı geçen kişilere
            # ("şu ikisi ayrı kalsın") uygulanır.
            st.Page(
                _page(custom_rules.render, "ozel-kurallar"),
                title="Özel Kurallar", icon="📏", url_path="ozel-kurallar",
            ),
        ],
        "Planlama": [
            st.Page(
                _page(dashboard.render, "ana-sayfa"),
                title="Ana Sayfa", icon="🏠", url_path="ana-sayfa", default=True,
            ),
            st.Page(
                _page(season_grid.render, "yillik-tablo"),
                title="Yıllık Tablo", icon="📅", url_path="yillik-tablo",
            ),
            # Yıllık Tablo düzenleme, Sezon Tablosu okuma/yazdırma. İkisi
            # aynı veriyi gösterir ama farklı iş yapar; bu yüzden Yıllık
            # Tablo'daki yarım kalmış "renkli görünüm" bölümü kaldırıldı.
            st.Page(
                _page(season_board.render, "sezon-tablosu"),
                title="Sezon Tablosu", icon="📖", url_path="sezon-tablosu",
            ),
            st.Page(
                _page(violations.render, "kural-kontrolu"),
                title="Kural Kontrolü", icon="🛡️", url_path="kural-kontrolu",
            ),
        ],
        "Araçlar": [
            st.Page(
                _page(excel_screen.render, "excel"),
                title="Excel", icon="📊", url_path="excel",
            ),
            st.Page(
                _page(history.render, "ogrenci-gecmisi"),
                title="Öğrenci Geçmişi", icon="🕘", url_path="ogrenci-gecmisi",
            ),
            st.Page(
                _page(help_screen.render, "yardim"),
                title="Yardım", icon="❓", url_path="yardim",
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
