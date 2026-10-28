"""🆘 Destek — uzaktaki geliştiriciyle ortak çalışma ekranı.

Uygulama son kullanıcının bilgisayarında çalışır, bakımını uzaktaki bir
geliştirici yapar. Bu ekran ikisinin aynı şeyden söz edebilmesini ve gerektiğinde uzaktan bir
düzeltmenin **onaylanarak** uygulanmasını sağlar.

Gizlilik: dışarı yalnız KİMLİKSİZ görüntü gider — isimler ve okul numaraları
çıkarılır, her öğrenciye kalıcı bir destek kodu (Ö-07) verilir. Kod bu
ekranda ve Sezon Tablosu'nda adın yanında görünür; telefonda kodla
konuşulur. Ayrıntı: rotasyon/support.py.

Uzaktan gelen düzeltme ASLA sessizce uygulanmaz: ne yapacağı yazılı olarak
gösterilir, kullanıcı onaylar, uygulamadan önce otomatik yedek alınır ve o
yedek kullanıcıya indirtilir — geri dönüş yolu her zaman burada kalsın diye.
"""
from __future__ import annotations

import streamlit as st

from rotasyon.support import (
    FixError,
    apply_fix,
    assign_codes,
    build_snapshot,
    data_revision,
    describe_fix,
    find_by_code,
    label_with_code,
    validate_fix,
)
from rotasyon.support_sync import (
    SupportConfig,
    load_config,
    pending_fixes,
    push_snapshot,
    redact,
    save_config,
)
from .common import DATA_DIR, get_manager


def render(store) -> None:
    st.header("🆘 Destek")
    st.caption(
        "Uzaktaki yöneticiyle birlikte çalışmak için. Öğrenci adları "
        "**gönderilmez**: her öğrencinin bir destek kodu vardır, telefonda "
        "o kodla konuşulur."
    )

    students = store.load_students()
    if not students:
        st.info("Bu sezonda öğrenci yok.")
        return

    codes = _ensure_codes(store, students)
    season = get_manager().active_season() or ""

    _code_lookup(students, codes)
    st.divider()
    _fix_panel(store, season)
    st.divider()
    _channel_panel(store, season, students, codes)


def _ensure_codes(store, students) -> dict:
    """Kodları bir kez verir ve saklar; var olanlara asla dokunmaz."""
    mevcut = store.load_support_codes()
    kodlar = assign_codes(students, mevcut)
    if kodlar != mevcut:
        store.save_support_codes(kodlar)
    return kodlar


# --------------------------------------------------------------- kod arama

def _code_lookup(students, codes) -> None:
    st.subheader("🔎 Kod ↔ öğrenci")
    st.caption(
        "Yönetici size bir kod söylediyse soldaki kutuya yazın. Bir "
        "öğrenciden söz etmek istiyorsanız sağdan seçip kodunu okuyun."
    )
    c1, c2 = st.columns(2)

    with c1:
        sorgu = st.text_input(
            "Kodu yazın", placeholder="Ö-07 · 07 · 7", key="sup_code_q",
            help="Baştaki 'Ö-' ve sıfır önemli değil, yalnız sayıyı da "
            "yazabilirsiniz.",
        )
        if sorgu.strip():
            bulunan = find_by_code(students, codes, sorgu)
            if bulunan is None:
                st.warning("Bu kodda öğrenci yok. Kodu tekrar sorun.")
            else:
                st.success(
                    f"**{bulunan.full_name}** — {bulunan.class_name} sınıfı, "
                    f"{bulunan.group}. grup"
                    + ("" if bulunan.active else " · (ayrılmış)")
                )

    with c2:
        secim = st.selectbox(
            "Öğrenci seçin", sorted(students, key=lambda s: s.full_name),
            format_func=lambda s: s.full_name, index=None,
            placeholder="Ad yazarak arayın", key="sup_student_q",
        )
        if secim is not None:
            st.success(
                f"Yöneticiye şu kodu söyleyin: **{codes.get(secim.id, '—')}**"
            )

    with st.expander("📋 Tüm kodlar"):
        satirlar = [
            f"| {codes.get(s.id, '—')} | {s.full_name} | {s.class_name} | "
            f"{s.group} |"
            for s in sorted(students, key=lambda s: codes.get(s.id, ""))
        ]
        st.markdown(
            "| Kod | Ad Soyad | Sınıf | Grup |\n|---|---|---|--:|\n"
            + "\n".join(satirlar)
        )


# ----------------------------------------------------- gelen düzeltmeler

def _fix_panel(store, season: str) -> None:
    st.subheader("🔧 Yöneticiden gelen düzeltme")
    cfg = load_config(DATA_DIR)
    if not cfg.ready:
        st.caption("Destek kanalı kapalı — aşağıdan açabilirsiniz.")
        return

    if st.button("🔄 Yeni düzeltme var mı, bak", key="sup_check"):
        st.session_state["_sup_fixes"] = pending_fixes(
            DATA_DIR, season, set(store.load_support_applied())
        )
        st.rerun()

    res = st.session_state.get("_sup_fixes")
    if res is None:
        return
    if res.status == "hata":
        st.error(f"Bakılamadı: {res.message}")
        return
    if not res.fixes:
        st.success("Bekleyen düzeltme yok. ✅")
        return

    guncel = data_revision(store.raw_season_payload())
    for fix in res.fixes:
        with st.container(border=True):
            st.markdown(f"**{fix.get('summary', '(açıklama yok)')}**")
            st.caption(
                f"Gönderim: {fix.get('created', '—')} · "
                f"Kod: `{fix.get('id', '?')}`"
            )
            try:
                uyarilar = validate_fix(fix, season, guncel)
            except FixError as exc:
                st.error(f"Bu paket uygulanamaz: {exc}")
                continue
            st.markdown("**Neyi değiştirecek:**")
            for satir in describe_fix(fix):
                st.markdown(f"- {satir}")
            for u in uyarilar:
                st.warning(f"⚠️ {u}")
            st.caption(
                "Uygulanmadan önce mevcut hâlin yedeği alınır ve size "
                "indirilir; istemezseniz o yedekle geri dönebilirsiniz."
            )
            if st.button(
                "✅ Uygula", type="primary", key=f"sup_apply_{fix.get('id')}"
            ):
                _apply(store, fix, season)


def _apply(store, fix, season) -> None:
    try:
        sonuc = apply_fix(store, fix, season)
    except FixError as exc:
        st.error(f"Uygulanamadı: {exc}")
        return
    store.mark_support_applied(fix.get("id", ""))
    st.session_state["_sup_backup"] = sonuc["backup"]
    st.session_state["_sup_backup_name"] = f"duzeltme-oncesi-{season}.zip"
    st.session_state.pop("_sup_fixes", None)
    st.success("Düzeltme uygulandı. ✅")
    st.rerun()


# ------------------------------------------------------------- kanal / kurulum

def _channel_panel(store, season, students, codes) -> None:
    st.subheader("📡 Destek kanalı")
    cfg = load_config(DATA_DIR)

    if yedek := st.session_state.pop("_sup_backup", None):
        st.download_button(
            "📥 Düzeltmeden önceki yedeği indir",
            data=yedek,
            file_name=st.session_state.pop("_sup_backup_name", "yedek.zip"),
            mime="application/zip",
        )

    if cfg.ready:
        st.caption(f"Açık · depo: `{redact(cfg.repo)}`")
        if st.button("📤 Durumu şimdi gönder", key="sup_push"):
            _push(store, season, students, codes)
    else:
        st.caption("Kapalı. Veriniz hiçbir yere gönderilmiyor.")

    with st.expander("⚙️ Kanal ayarları (yönetici kurar)"):
        st.caption(
            "Buraya yalnız **kimliksiz** görüntü gönderilir: öğrenci adları "
            "ve okul numaraları çıkarılır, yerine destek kodları yazılır. "
            "Adres yöneticiden gelir."
        )
        repo = st.text_input(
            "Destek deposu adresi", value=cfg.repo, type="password",
            key="sup_repo",
            help="Yöneticinin verdiği https://... adresi. Gizli bir anahtar "
            "içerdiği için gizli gösterilir.",
        )
        makine = st.text_input(
            "Bu bilgisayarın adı", value=cfg.machine or "hastane",
            key="sup_machine",
        )
        acik = st.checkbox("Kanal açık", value=cfg.enabled, key="sup_enabled")
        if st.button("💾 Kaydet", key="sup_save_cfg"):
            save_config(
                DATA_DIR,
                SupportConfig(repo=repo.strip(), enabled=acik,
                              machine=makine.strip()),
            )
            st.toast("Destek ayarları kaydedildi", icon="📡")
            st.rerun()


def _push(store, season, students, codes) -> None:
    snap = build_snapshot(
        season, students, store.load_units(), store.load_requirements(),
        store.load_custom_rules(), store.load_assignments(),
        store.load_settings(), store.load_classes(), codes,
        revision=data_revision(store.raw_season_payload()),
    )
    with st.spinner("Gönderiliyor…"):
        res = push_snapshot(DATA_DIR, season, snap, students=students)
    if res.status == "gonderildi":
        st.success("Gönderildi. ✅ Yönetici artık güncel durumu görüyor.")
    elif res.status == "degisiklik-yok":
        st.info("Zaten güncel — son gönderimden beri bir şey değişmemiş.")
    else:
        st.error(res.message)


def student_labels(store, students) -> dict:
    """öğrenci_id -> "AD SOYAD · Ö-07" (destek kanalı açıksa).

    Kod yalnız kanal açıkken gösterilir: kullanmayan kurulumda ekranı
    gereksiz yere kalabalıklaştırmasın.
    """
    if not load_config(DATA_DIR).ready:
        return {}
    codes = store.load_support_codes()
    return {s.id: label_with_code(s, codes) for s in students}
