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
    _orphan_cleanup_panel(store, students, units, assignments, violations)
    # Bu ekran tümüyle kayıtlı (tamamlanmış) veriyi denetler; düzenleme kapsamı
    # yoktur → aya/öğrenciye bağlı her ihlal "geçmişe dönük" sayılır. Ayar
    # kapalıyken yalnız yapısal (aysız) ihlaller kalır, gerisi gizlenir.
    show_violations_scoped(
        violations, empty_message="Tüm atamalar kurallara uygun. ✅"
    )


def _orphan_cleanup_panel(store, students, units, assignments, violations) -> None:
    """Sahipsiz atamalar (kural 0) için tek tıkla temizlik.

    Silinmiş öğrenci/birime işaret eden atamalar normal akışta oluşmaz
    (silme akışları korunur) ama eski yedeğin kısmi geri yüklenmesi ya da
    elle düzenlenmiş JSON ile ortaya çıkabilir. Denetleyici bunları hata
    olarak gösterir; kullanıcı JSON'a giremeyeceği için düzeltme de burada
    sunulmalıdır.
    """
    if not any(v.rule_no == 0 for v in violations):
        return
    from rotasyon.maintenance import strip_orphan_assignments

    kept, n_orphans = strip_orphan_assignments(students, units, assignments)
    if not n_orphans:
        return
    st.warning(
        f"🧹 {n_orphans} atama, artık var olmayan bir öğrenci veya birime "
        "işaret ediyor (genelde eski bir yedekten kısmi geri yükleme sonucu). "
        "Bu kayıtlar hiçbir ekranda görünmez ve hiçbir işe yaramaz; güvenle "
        "temizlenebilir."
    )
    if st.button(f"🧹 {n_orphans} sahipsiz atamayı temizle", key="clean_orphans"):
        store.save_assignments(kept)
        st.toast(f"{n_orphans} sahipsiz atama temizlendi ✅", icon="🧹")
        st.rerun()
