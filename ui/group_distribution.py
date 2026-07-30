"""Grup Dağılımı — kullanıcının elle yaptığı "BÖLÜMLER VE SAYILAR" tablosunun
canlı hâli.

Eğitim hemşiresi rotasyonu elle yaparken her grup için bir birim listesi
tutuyor: birim adı kontenjanı kadar tekrar yazılıyor (kaç kişi gittiğini
saymamak için) ve o gruba verilmeyen birimler griye boyanıyor. Bu ekran aynı
şeyi gösterir ve düzenletir — mevcut ekranlara dokunmadan, aynı sezon verisi
üzerinde.

"İptal" = o birimin O GRUPTAKİ satırını pasifleştirmek (active=False).
Birimler katalogda gruba özel tutulduğundan (her ad grup-1 ve grup-2 olarak
ayrı) bir grubu iptal etmek diğerini etkilemez. Çözücü ve denetleyici pasif
birime yeni atama yapmaz — yani iptal gerçek bir yapılandırma kararıdır.
"""
from __future__ import annotations

import streamlit as st

from rotasyon.queries import group_unit_distribution
from .common import groups_in


def render(store) -> None:
    st.header("📊 Grup Dağılımı")
    st.caption(
        "Her grup için hangi birime kaç kişi (kontenjan) gideceğini burada "
        "görür ve ayarlarsınız. Bir birimi bir grup için **iptal** ederseniz "
        "o gruptan kimse oraya verilmez (elle yaparken griye boyadığınız "
        "birimler). Kontenjan toplamı grubun öğrenci sayısına oturmalı."
    )

    students = store.load_students()
    units = store.load_units()
    if not units:
        st.info("Henüz birim yok. Önce Veri Yönetimi'nden birim ekleyin.")
        return
    if not students:
        st.info("Henüz öğrenci yok. Dağılım için önce öğrenci ekleyin.")

    groups = groups_in(students)
    cols = st.columns(len(groups)) if len(groups) > 1 else [st.container()]
    for col, g in zip(cols, groups):
        with col:
            _group_panel(store, units, students, g)


def _balance_indicator(dist) -> None:
    """Kontenjan toplamı öğrenci sayısına oturuyor mu — renkli özet."""
    b = dist.balance
    st.metric(
        "Aktif kontenjan",
        f"{dist.active_quota_total}",
        delta=f"{b:+d} (öğrenci: {dist.student_count})",
        delta_color="off",
    )
    if dist.student_count == 0:
        return
    if b == 0:
        st.success("✅ Kontenjan öğrenci sayısına tam oturuyor.")
    elif b > 0:
        st.info(
            f"ℹ️ {b} fazla kontenjan var — bu pay, havuz birimlerine eşit "
            "dağıtılacak öğrencilerin esnekliğidir. Sıfıra yaklaştırmak için "
            "birim iptal edebilir ya da kontenjan azaltabilirsiniz."
        )
    else:
        st.error(
            f"❌ {-b} eksik kontenjan — bu haliyle {-b} öğrenciye yer "
            "bulunamaz. Birim ekleyin/aktifleştirin ya da kontenjan artırın."
        )


def _group_panel(store, units, students, group) -> None:
    dist = group_unit_distribution(units, students, group)
    st.subheader(f"{group}. Grup — {dist.student_count} öğrenci")
    _balance_indicator(dist)

    aktif = [r for r in dist.rows if r.active]
    pasif = [r for r in dist.rows if not r.active]
    st.caption(f"{len(aktif)} aktif birim · {len(pasif)} iptal")

    for row in dist.rows:
        c1, c2, c3, c4 = st.columns([5, 1, 1, 2])
        if row.active:
            c1.markdown(f"{row.name} **×{row.quota}**")
        else:
            # iptal: gri + üstü çizili (listede kalır — "atlamayayım diye")
            c1.markdown(
                f"<span style='color:#999;text-decoration:line-through'>"
                f"{row.name} ×{row.quota}</span> &nbsp;<span style='color:#c00;"
                f"font-size:0.8em'>iptal</span>",
                unsafe_allow_html=True,
            )
        # kontenjan +/- yalnız aktif birimlerde
        if row.active:
            if c2.button("➖", key=f"q-_{group}_{row.unit_id}",
                         disabled=row.quota <= 1, help="Kontenjanı azalt"):
                _set_quota(store, row.unit_id, row.quota - 1)
            if c3.button("➕", key=f"q+_{group}_{row.unit_id}",
                         help="Kontenjanı artır"):
                _set_quota(store, row.unit_id, row.quota + 1)
        # iptal / geri aç
        if row.active:
            if c4.button("🚫 İptal", key=f"off_{group}_{row.unit_id}",
                         help="Bu gruba bu birimden öğrenci verilmesin"):
                _set_active(store, row.unit_id, False)
        else:
            if c4.button("↩️ Geri aç", key=f"on_{group}_{row.unit_id}"):
                _set_active(store, row.unit_id, True)

    with st.expander("📋 Tekrarlı liste (kes-yapıştır için)"):
        st.caption(
            "Elle yaptığınız tablo gibi: her birim kontenjanı kadar tekrar "
            "yazılı. Kopyalayıp kendi belgenize yapıştırabilirsiniz."
        )
        satirlar = [
            r.name for r in dist.rows if r.active for _ in range(r.quota)
        ]
        st.code("\n".join(satirlar) or "(aktif birim yok)", language=None)


def _find(units, unit_id):
    return next((u for u in units if u.id == unit_id), None)


def _set_active(store, unit_id, value) -> None:
    units = store.load_units()
    u = _find(units, unit_id)
    if u is not None and u.active != value:
        u.active = value
        store.save_units(units)
        durum = "geri açıldı" if value else "iptal edildi"
        st.toast(f"{u.name} {durum} ✅", icon="📊")
    st.rerun()


def _set_quota(store, unit_id, value) -> None:
    units = store.load_units()
    u = _find(units, unit_id)
    if u is not None and value >= 0 and u.quota != value:
        u.quota = value
        store.save_units(units)
    st.rerun()
