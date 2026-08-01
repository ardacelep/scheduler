"""Kapasite Planı — "hangi birime kaç kişi, kalanlar nereye?"

Gereksinimler ekranı *kimin neyi görmesi gerektiğini* belirler. Bu ekran ise
kapasiteyi kurar: her birimin bir **doldurma politikası** ve kontenjanı vardır,
ve ekran bu seçimlerin aritmetiğini canlı gösterir — kullanıcının elle
tutturmaya çalıştığı "tam dolanlar 20 kişi, kalan 44 kişi şu birimlere eşit"
hesabı.

v1'de bu bilgi dört ayrı kutucuğa (`must_fill`, `single_slot`, `pool`,
`reserve`) dağılmıştı ve toplamı hiçbir yerde görünmüyordu. Burada tek seçim +
tek tablo. Aynı veriyi yazar (şema değişmez), v1 ekranları etkilenmez.
"""
from __future__ import annotations

import streamlit as st

from rotasyon.fill_policy import (
    POLICIES,
    POLICY_HELP,
    POLICY_ICONS,
    POLICY_LABELS,
    POLICY_MUST_FILL,
    POLICY_POOL,
    POLICY_PREFER_FILL,
    POLICY_RESERVE,
    apply_policy,
    group_capacity_plan,
    policy_of,
)
from ..common import groups_in


def render(store) -> None:
    st.header("📦 Kapasite Planı")
    st.caption(
        "Her birimin **kaç kişi alacağını** ve **nasıl doldurulacağını** "
        "burada belirlersiniz. Ekran, seçimlerinizin toplamını canlı hesaplar: "
        "zorunlu dolan birimler kaç kişi çekiyor, geriye kaç öğrenci kalıyor, "
        "kalanlar birim başına kaça düşüyor."
    )

    units = store.load_units()
    students = store.load_students()
    if not units:
        st.info("Önce Veri Yönetimi'nden birim ekleyin.")
        return
    if not students:
        st.info(
            "Henüz öğrenci yok. Kapasite matematiği öğrenci sayısına göre "
            "hesaplandığı için önce öğrencileri içe aktarın."
        )

    _legend()
    for g in groups_in(students):
        st.divider()
        _group_section(store, units, students, g)


def _legend() -> None:
    with st.expander("ℹ️ Politikalar ne anlama geliyor?"):
        for p in POLICIES:
            st.markdown(
                f"{POLICY_ICONS[p]} **{POLICY_LABELS[p]}** — {POLICY_HELP[p]}"
            )


def _group_section(store, units, students, group) -> None:
    plan = group_capacity_plan(units, students, group)
    st.subheader(f"{group}. Grup — {plan.student_count} öğrenci")

    _summary(plan)
    for w in plan.warnings:
        st.warning(f"⚠️ {w}")

    _breakdown(plan)
    with st.expander(f"✏️ Grup {group} birimlerini düzenle", expanded=False):
        _unit_editor(store, units, group)
    _repeated_list(units, group)


def _repeated_list(units, group) -> None:
    """Elle tutulan tablonun birebir hâli: her birim kontenjanı kadar tekrar.

    Eğitim hemşiresi rotasyonu elle yaparken birim adını kaç kişi gidecekse o
    kadar yazıyor ("kes-yapıştır yapıyorum ki kaç kişi verdim saymayayım").
    Kendi belgesine yapıştırabilsin diye kopyalanabilir metin olarak sunulur.
    """
    with st.expander("📋 Tekrarlı liste (kes-yapıştır için)"):
        satirlar = [
            u.name_with_gender
            for u in sorted(
                (x for x in units if x.group in (0, group) and x.active),
                key=lambda x: x.name,
            )
            for _ in range(u.quota)
        ]
        st.caption(
            f"{len(satirlar)} satır — her birim kontenjanı kadar tekrar yazılı."
        )
        st.code("\n".join(satirlar) or "(aktif birim yok)", language=None)


def _summary(plan) -> None:
    """Kullanıcının elle tuttuğu üç sayı: kesin, kalan, birim başına."""
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Öğrenci", plan.student_count)
    c2.metric(
        "🔒 Tam dolanlar", plan.must_fill_total,
        help="Her ay KESİN olarak bu kadar öğrenci bu birimlerde olacak.",
    )
    c3.metric(
        "Dağıtılacak kalan", max(0, plan.remaining),
        help="Zorunlu dolan birimlerden sonra diğer birimlere yerleşecek "
        "öğrenci sayısı.",
    )
    per = plan.pool_per_unit
    c4.metric(
        "⚖️ Havuz birimi başına", "—" if per is None else f"~{per:.1f}",
        help="Kalan öğrencilerin havuz birimlerine yaklaşık dağılımı "
        "(“Mümkünse dolsun” birimlerine birer kişi ayrıldıktan sonra).",
    )

    b = plan.balance
    if not plan.student_count:
        return
    if b > 0:
        st.caption(
            f"Toplam aktif kontenjan **{plan.active_quota_total}** · "
            f"öğrenci **{plan.student_count}** · **+{b} pay** "
            "(çözücünün hareket alanı — bir miktar fazla olması iyidir)."
        )
    elif b == 0:
        st.caption(
            f"Toplam aktif kontenjan **{plan.active_quota_total}** — öğrenci "
            "sayısına tam eşit."
        )
    else:
        st.caption(
            f"Toplam aktif kontenjan **{plan.active_quota_total}** · "
            f"öğrenci **{plan.student_count}** · **{b} açık**."
        )


def _breakdown(plan) -> None:
    """Politika bazında birim/kontenjan dökümü.

    Markdown tablo — st.dataframe canvas'a çizdiği için metni seçilemez ve
    ekran okuyucu/otomatik doğrulama görmez; beş satırlık bir özet için de
    gereksiz ağır.
    """
    satirlar = [
        f"| {POLICY_ICONS[p]} {POLICY_LABELS[p]} | {b.unit_count} | "
        f"{b.quota_total} |"
        for p in POLICIES
        if (b := plan.buckets[p]).unit_count
    ]
    if not satirlar:
        return
    st.markdown(
        "| Politika | Birim | Toplam kontenjan |\n|---|--:|--:|\n"
        + "\n".join(satirlar)
    )


def _unit_editor(store, units, group) -> None:
    """Grup birimlerinin politika + kontenjan + aktiflik düzenleyicisi."""
    g_units = sorted(
        (u for u in units if u.group in (0, group)),
        key=lambda u: u.name,
    )
    st.caption(
        "Politikayı değiştirdiğinizde diğer bayraklar otomatik temizlenir — "
        "bir birim aynı anda hem “tam dolmalı” hem “yedek” olamaz."
    )
    for u in g_units:
        c1, c2, c3, c4 = st.columns([4, 3, 2, 2])
        ad = u.name_with_gender
        if u.active:
            c1.markdown(f"{ad} **×{u.quota}**")
        else:
            c1.markdown(
                f"<span style='color:#999;text-decoration:line-through'>"
                f"{ad} ×{u.quota}</span>",
                unsafe_allow_html=True,
            )

        mevcut = policy_of(u)
        secilen = c2.selectbox(
            "Politika", POLICIES, index=POLICIES.index(mevcut),
            format_func=lambda p: f"{POLICY_ICONS[p]} {POLICY_LABELS[p]}",
            key=f"cap_pol_{group}_{u.id}", label_visibility="collapsed",
            disabled=not u.active,
        )
        if secilen != mevcut:
            _save_policy(store, u.id, secilen)

        yeni_kota = c3.number_input(
            "Kontenjan", min_value=0, max_value=99, value=int(u.quota),
            key=f"cap_q_{group}_{u.id}", label_visibility="collapsed",
            disabled=not u.active,
        )
        if int(yeni_kota) != int(u.quota):
            _save_quota(store, u.id, int(yeni_kota))

        etiket = "↩️ Geri aç" if not u.active else "🚫 İptal"
        if c4.button(etiket, key=f"cap_act_{group}_{u.id}"):
            _save_active(store, u.id, not u.active)


def _find(units, unit_id):
    return next((u for u in units if u.id == unit_id), None)


def _save_policy(store, unit_id, policy) -> None:
    units = store.load_units()
    u = _find(units, unit_id)
    if u is not None and apply_policy(u, policy):
        store.save_units(units)
        st.toast(f"{u.name}: {POLICY_LABELS[policy]} ✅", icon="📦")
    st.rerun()


def _save_quota(store, unit_id, value) -> None:
    units = store.load_units()
    u = _find(units, unit_id)
    if u is not None and u.quota != value:
        u.quota = value
        store.save_units(units)
    st.rerun()


def _save_active(store, unit_id, value) -> None:
    units = store.load_units()
    u = _find(units, unit_id)
    if u is not None and u.active != value:
        u.active = value
        store.save_units(units)
        st.toast(
            f"{u.name} {'geri açıldı' if value else 'iptal edildi'} ✅",
            icon="📦",
        )
    st.rerun()
