"""Kurulum Sihirbazı — "sezonu kurmak için sırayla ne yapmalıyım?"

Kurulum işleri beş ayrı ekrana dağılmış durumda; kullanıcı hangisini yaptığını
kendi takip etmek zorundaydı. Bu ekran adımları sırayla listeler, her birinin
durumunu VERİDEN okur (kullanıcının işaretlemesine gerek yok) ve ilgili ekrana
yönlendirir.

Bilerek işi kendisi yapmaz — her adım kendi ekranında yapılır. Sihirbaz
yalnız yol gösterir; aksi halde aynı düzenleyiciler iki yerde yaşar ve
kaçınılmaz olarak birbirinden ayrışırlar.
"""
from __future__ import annotations

import streamlit as st

from rotasyon.setup_status import (
    STATE_BLOCKED,
    STATE_DONE,
    STATE_WARN,
    first_actionable,
    progress,
    setup_steps,
)


def render(store) -> None:
    st.header("🧭 Kurulum Sihirbazı")
    st.caption(
        "Yeni bir sezonu kurarken sırayla yapılacaklar. Her adımın durumu "
        "verinizden okunur — siz bir şey işaretlemezsiniz, “tamam” gerçekten "
        "tamam demektir."
    )

    steps = setup_steps(
        store.load_students(),
        store.load_units(),
        store.load_classes(),
        store.load_requirements(),
        store.load_assignments(),
        store.load_settings(),
    )
    done, total = progress(steps)
    st.progress(done / total, text=f"{done}/{total} adım tamam")

    sirada = first_actionable(steps)
    if sirada is None:
        st.success(
            "🎉 Kurulum tamam. Sezonu Yıllık Tablo'dan yönetebilir, "
            "Kural Kontrolü'nden denetleyebilirsiniz."
        )
    else:
        st.info(f"**Sıradaki adım:** {sirada.title} — {sirada.detail}")

    st.divider()
    for i, step in enumerate(steps, 1):
        _step_card(step, i, vurgula=step is sirada)


def _step_card(step, sira: int, vurgula: bool) -> None:
    with st.container(border=True):
        c1, c2 = st.columns([5, 2])
        baslik = f"{step.icon} **{sira}. {step.title}**"
        if step.state == STATE_BLOCKED:
            # kilitli adımın başlığı da soluk olsun — sırası gelmedi
            baslik = (
                f"{step.icon} <span style='color:#999'>{sira}. "
                f"{step.title}</span>"
            )
            c1.markdown(baslik, unsafe_allow_html=True)
        else:
            c1.markdown(baslik)
        c1.caption(step.detail)

        if step.state == STATE_BLOCKED:
            return
        etiket = ("➡️ " if vurgula else "") + step.action
        _link(c2, step.page, etiket)


def _link(col, url_path: str, label: str) -> None:
    """st.navigation sayfasına bağlantı (dashboard'daki desenle aynı)."""
    pages = st.session_state.get("_pages", {})
    if url_path in pages:
        col.page_link(pages[url_path], label=label)
