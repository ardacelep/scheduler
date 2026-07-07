"""Kural İhlali Kontrol Paneli — mevcut atama tablosunun tam denetimi."""
from __future__ import annotations

import streamlit as st

from rotasyon.rules import check_all
from .common import show_violations_scoped


def render(store) -> None:
    st.header("🛡️ Kural Kontrolü")
    st.caption(
        "Kayıtlı tüm atamalar 19 kurala karşı denetlenir. Elle değişikliklerden "
        "sonra da çalıştırabilirsiniz."
    )
    st.info(
        "ℹ️ Bu denetim **tüm ayları GÜNCEL veriyle** karşılaştırır: bir birimin "
        "kontenjanını düşürür ya da bir kısıt eklerseniz, geçmiş bir ay artık "
        "buna uymuyorsa burada hata olarak görünür. Bu yalnız **bilgilendirme** "
        "amaçlıdır — geçmiş rotasyonlar kendiliğinden değişmez ve bu eski "
        "hatalar yeni ay kaydetmenizi engellemez. Zamana bağlı kurallar "
        "(başlangıç/bitiş ayı olanlar) yalnız kendi aylarında denetlenir.",
        icon="ℹ️",
    )
    students = store.load_students()
    units = store.load_units()
    assignments = store.load_assignments()
    settings = store.load_settings()
    months = settings["months"]
    if not assignments:
        st.info("Henüz kayıtlı atama yok.")
        return
    custom_rules = store.load_custom_rules()
    violations = check_all(
        students, units, assignments, months,
        custom_rules=custom_rules, settings=settings,
    )
    # Bu ekran tümüyle kayıtlı (tamamlanmış) veriyi denetler; düzenleme kapsamı
    # yoktur → aya/öğrenciye bağlı her ihlal "geçmişe dönük" sayılır. Ayar
    # kapalıyken yalnız yapısal (aysız) ihlaller kalır, gerisi gizlenir.
    show_violations_scoped(
        violations, empty_message="Tüm atamalar kurallara uygun. ✅"
    )
