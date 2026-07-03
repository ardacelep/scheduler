"""Rotasyon Oluşturma ekranı — 3 mod: Tam Otomatik, Yarı Otomatik, Sihirbaz."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from rotasyon.models import Assignment
from rotasyon.rules import check_all
from rotasyon.solver import solve_month, visited_unit_keys
from rotasyon.normalize import normalize_key
from .common import (
    clear_stale_state,
    data_fingerprint,
    gender_label,
    groups_in,
    replace_month_assignments,
    show_violations,
    unit_label,
)

# Taslak öneriler, sihirbaz adımları, düzenleyici durumu... — hepsi veriden
# türetilir; veri değişince clear_stale_state ile silinirler.
_DRAFT_PREFIXES = ("proposal_", "wizard_", "semi_editor_", "reroll_", "semi_force")


def render(store) -> None:
    st.header("🔄 Rotasyon Oluştur")
    students = store.load_students()
    units = store.load_units()
    if not students or not units:
        st.info("Önce Veri Yönetimi ekranından öğrenci ve birim ekleyin.")
        return
    settings = store.load_settings()
    months = settings["months"]

    c1, c2 = st.columns(2)
    group = c1.selectbox(
        "Grup", groups_in(students), format_func=lambda g: f"{g}. Grup"
    )
    month = c2.selectbox("Ay", months)

    group_students = sorted(
        [s for s in students if s.group == group], key=lambda s: s.full_name
    )
    group_units = [u for u in units if u.group in (0, group)]
    all_assignments = store.load_assignments()
    group_ids = {s.id for s in group_students}
    history = [
        a
        for a in all_assignments
        if a.student_id in group_ids and a.month != month
    ]
    existing = {
        a.student_id: a.unit_id
        for a in all_assignments
        if a.student_id in group_ids and a.month == month
    }
    if existing:
        st.info(
            f"{month} ayı için {len(existing)} kayıtlı atama var. "
            "Yeniden oluşturursanız üzerine yazılır."
        )
    missing_gender = [s.full_name for s in group_students if not s.gender]
    if missing_gender:
        st.error(
            "Şu öğrencilerin cinsiyeti girilmemiş (kurallar için gerekli): "
            + ", ".join(missing_gender)
        )
        return

    # Veri (öğrenci/birim/atama/kural/ayar) başka bir ekranda değiştiyse
    # buradaki taslak çözümler ve uyarılar bayattır: temizle ki kullanıcı
    # her zaman güncel duruma göre sonuç görsün.
    custom_rules = [r for r in store.load_custom_rules() if r.active]
    clear_stale_state(
        "_rotation_fp",
        data_fingerprint(
            students, units, all_assignments, custom_rules, [settings]
        ),
        _DRAFT_PREFIXES,
    )
    month_pins = [
        r for r in custom_rules
        if r.type == "sabit_atama" and r.month == month
        and any(sid in group_ids for sid in r.student_ids)
    ]
    if month_pins:
        st.info(
            f"📏 Bu ay için {len(month_pins)} sabit atama kuralı uygulanacak "
            "(Veri Yönetimi → Kurallar)."
        )

    tab_auto, tab_semi, tab_wizard = st.tabs(
        ["⚡ Tam Otomatik", "✏️ Yarı Otomatik", "🧭 Adım Adım Sihirbaz"]
    )
    ctx = dict(
        store=store,
        settings=settings,
        months=months,
        group=group,
        month=month,
        students=group_students,
        units=group_units,
        history=history,
        existing=existing,
        group_ids=group_ids,
        custom_rules=custom_rules,
    )
    with tab_auto:
        _auto_mode(ctx)
    with tab_semi:
        _semi_mode(ctx)
    with tab_wizard:
        _wizard_mode(ctx)


# ---------- yardımcılar ----------

def _proposal_key(ctx) -> str:
    return f"proposal_{ctx['group']}_{ctx['month']}"


def _solve(ctx, locked=None, reroll=False):
    seed = None
    if reroll:
        counter_key = f"reroll_{ctx['group']}_{ctx['month']}"
        st.session_state[counter_key] = st.session_state.get(counter_key, 0) + 1
        seed = st.session_state[counter_key]
    with st.spinner("Çözücü çalışıyor..."):
        return solve_month(
            ctx["students"],
            ctx["units"],
            ctx["month"],
            history=ctx["history"],
            settings=ctx["settings"],
            locked=locked,
            random_seed=seed,
            custom_rules=ctx["custom_rules"],
        )


def _proposal_df(ctx, mapping: dict[str, str]) -> pd.DataFrame:
    units_by_id = {u.id: u for u in ctx["units"]}
    return pd.DataFrame(
        [
            {
                "Öğrenci": s.full_name,
                "Sınıf": s.class_name,
                "Cinsiyet": gender_label(s.gender),
                "Birim": unit_label(units_by_id[mapping[s.id]])
                if mapping.get(s.id) in units_by_id
                else "—",
            }
            for s in ctx["students"]
        ]
    )


def _check_proposal(ctx, mapping: dict[str, str]):
    proposed = [
        Assignment(student_id=sid, month=ctx["month"], unit_id=uid)
        for sid, uid in mapping.items()
    ]
    return check_all(
        ctx["students"],
        ctx["units"],
        ctx["history"] + proposed,
        ctx["months"],
        custom_rules=ctx["custom_rules"],
    )


def _save(ctx, mapping: dict[str, str]) -> None:
    replace_month_assignments(
        ctx["store"], ctx["group_ids"], ctx["month"], mapping
    )
    st.session_state.pop(_proposal_key(ctx), None)
    st.success(f"{ctx['month']} ayı ataması kaydedildi. ✅")


def _show_infeasible(result) -> None:
    st.error("Bu ay için tüm kurallara uyan bir atama bulunamadı.")
    st.markdown("**Olası nedenler:**")
    for reason in result.infeasible_reasons:
        st.markdown(f"- {reason}")


# ---------- Tam Otomatik ----------
#
# Mod fonksiyonları st.fragment: buton tıklamaları (özellikle uzun süren
# çözücü koşuları) yalnız kendi sekme içeriğini yeniden çizer; sayfanın
# kalanı soluklaşıp yeniden çizilmez. Veri değiştiren kayıtlarda
# st.rerun(scope="app") ile tüm sayfa tazelenir.

@st.fragment
def _auto_mode(ctx) -> None:
    key = _proposal_key(ctx)
    c1, c2 = st.columns(2)
    result = None
    if c1.button("🚀 Rotasyonu Oluştur", type="primary", key="auto_solve"):
        result = _solve(ctx)
    if c2.button("🎲 Yeniden Oluştur (farklı çözüm)", key="auto_reroll"):
        result = _solve(ctx, reroll=True)
    if result is not None:
        if result.ok:
            st.session_state[key] = result.assignments
        else:
            st.session_state.pop(key, None)
            # Uyarı kalıcı saklanmaz: yalnız bu koşuda gösterilir. Kullanıcı
            # veriyi düzeltince (örn. kontenjan artırınca) bayat uyarı kalmaz.
            _show_infeasible(result)
            return

    mapping = st.session_state.get(key)
    if not mapping:
        if ctx["existing"]:
            st.caption("Kayıtlı atama aşağıda gösteriliyor.")
            st.dataframe(
                _proposal_df(ctx, ctx["existing"]),
                use_container_width=True,
                hide_index=True,
            )
        return

    st.subheader("Önerilen Atama")
    st.dataframe(
        _proposal_df(ctx, mapping), use_container_width=True, hide_index=True
    )
    show_violations(_check_proposal(ctx, mapping))
    if st.button("✅ Onayla ve Kaydet", type="primary", key="auto_save"):
        _save(ctx, mapping)
        st.rerun(scope="app")


# ---------- Yarı Otomatik ----------

@st.fragment
def _semi_mode(ctx) -> None:
    key = _proposal_key(ctx)
    st.caption(
        "Sistem öneri üretir; hücreleri elle değiştirebilirsiniz. Her "
        "değişiklikte kural denetimi çalışır, ihlaller anında görünür."
    )
    if st.button("Öneri üret / yenile", key="semi_solve"):
        result = _solve(ctx, reroll=True)
        if result.ok:
            st.session_state[key] = result.assignments
        else:
            _show_infeasible(result)

    mapping = dict(st.session_state.get(key) or ctx["existing"])
    if not mapping:
        st.info("Önce öneri üretin veya Tam Otomatik moddan bir atama kaydedin.")
        return

    units_by_label = {unit_label(u): u for u in ctx["units"] if u.active and u.quota > 0}
    units_by_id = {u.id: u for u in ctx["units"]}
    df = pd.DataFrame(
        [
            {
                "Öğrenci": s.full_name,
                "Sınıf": s.class_name,
                "Cinsiyet": gender_label(s.gender),
                "Birim": unit_label(units_by_id[mapping[s.id]])
                if s.id in mapping and mapping[s.id] in units_by_id
                else None,
            }
            for s in ctx["students"]
        ]
    )
    edited = st.data_editor(
        df,
        column_config={
            "Öğrenci": st.column_config.TextColumn(disabled=True),
            "Sınıf": st.column_config.TextColumn(disabled=True),
            "Cinsiyet": st.column_config.TextColumn(disabled=True),
            "Birim": st.column_config.SelectboxColumn(
                "Birim", options=sorted(units_by_label), required=True
            ),
        },
        use_container_width=True,
        hide_index=True,
        key=f"semi_editor_{ctx['group']}_{ctx['month']}",
    )
    new_mapping: dict[str, str] = {}
    for s, (_, row) in zip(ctx["students"], edited.iterrows()):
        label = row["Birim"]
        if label in units_by_label:
            new_mapping[s.id] = units_by_label[label].id
    st.session_state[key] = new_mapping

    violations = _check_proposal(ctx, new_mapping)
    show_violations(violations)
    errors = [v for v in violations if v.severity == "hata"]
    force = False
    if errors:
        force = st.checkbox(
            "İhlallere rağmen kaydetmek istiyorum", key="semi_force"
        )
    if st.button(
        "💾 Kaydet", type="primary", disabled=bool(errors) and not force,
        key="semi_save",
    ):
        _save(ctx, new_mapping)
        st.rerun(scope="app")


# ---------- Adım Adım Sihirbaz ----------

@st.fragment
def _wizard_mode(ctx) -> None:
    """Önce tekli birimler, sonra cinsiyet kısıtlı/tam dolan birimler,
    en son kalan öğrenciler havuza otomatik dağıtılır."""
    wkey = f"wizard_{ctx['group']}_{ctx['month']}"
    state = st.session_state.setdefault(wkey, {"step": 1, "locks": {}})
    units_by_id = {u.id: u for u in ctx["units"]}
    active_units = [u for u in ctx["units"] if u.active and u.quota > 0]

    steps = {
        1: ("Tekli birimler", [u for u in active_units if u.single_slot]),
        2: (
            "Cinsiyet kısıtlı / tam dolan birimler",
            [
                u
                for u in active_units
                if (u.gender_restriction or u.must_fill) and not u.single_slot
            ],
        ),
    }
    st.progress((state["step"] - 1) / 3, text=f"Adım {state['step']} / 3")

    if state["step"] in steps:
        title, step_units = steps[state["step"]]
        st.subheader(f"Adım {state['step']}: {title}")
        st.caption(
            "Her birim için önerilen öğrenciyi onaylayın veya değiştirin. "
            "Boş bırakılan birimler son adımda otomatik doldurulur."
        )
        # öneri: mevcut kilitlerle tam çözüm alıp bu adımın birimlerini oku
        suggestion_key = f"{wkey}_suggest_{state['step']}"
        if suggestion_key not in st.session_state:
            result = _solve(ctx, locked=state["locks"])
            st.session_state[suggestion_key] = (
                {uid: sid for sid, uid in result.assignments.items()}
                if result.ok
                else {}
            )
            if not result.ok:
                _show_infeasible(result)
        unit_to_sid = st.session_state[suggestion_key]

        locked_sids = set(state["locks"])
        for u in step_units:
            eligible = [
                s
                for s in ctx["students"]
                if (not u.gender_restriction or s.gender == u.gender_restriction)
                and u.id not in s.banned_unit_ids
                and not (s.dis_exempt and "DİŞ" in normalize_key(u.name))
                and normalize_key(u.name)
                not in visited_unit_keys(s.id, ctx["history"], units_by_id)
            ]
            options = ["(boş bırak)"] + [s.full_name for s in eligible]
            suggested = unit_to_sid.get(u.id)
            suggested_name = next(
                (s.full_name for s in eligible if s.id == suggested), None
            )
            pick = st.selectbox(
                f"{unit_label(u)} (kontenjan {u.quota})",
                options,
                index=options.index(suggested_name) if suggested_name else 0,
                key=f"{wkey}_pick_{u.id}",
            )
            state["locks"] = {
                sid: uid for sid, uid in state["locks"].items() if uid != u.id
            }
            if pick != "(boş bırak)":
                sid = next(s.id for s in eligible if s.full_name == pick)
                if sid in state["locks"] and state["locks"][sid] != u.id:
                    st.warning(f"{pick} zaten başka bir birime seçildi.")
                else:
                    state["locks"][sid] = u.id
        _ = locked_sids

        c1, c2 = st.columns(2)
        if c1.button("İleri ➡️", type="primary", key=f"{wkey}_next"):
            state["step"] += 1
            st.rerun(scope="fragment")
        if state["step"] > 1 and c2.button("⬅️ Geri", key=f"{wkey}_back"):
            st.session_state.pop(f"{wkey}_suggest_{state['step']}", None)
            state["step"] -= 1
            st.rerun(scope="fragment")
        return

    # Adım 3: kalanları otomatik dağıt
    st.subheader("Adım 3: Kalan öğrenciler havuz birimlerine dağıtılıyor")
    st.caption(
        f"{len(state['locks'])} öğrenci ilk iki adımda sabitlendi; kalan "
        f"{len(ctx['students']) - len(state['locks'])} öğrenci kurallara göre "
        "otomatik yerleştirilir."
    )
    result = _solve(ctx, locked=state["locks"])
    if not result.ok:
        _show_infeasible(result)
        if st.button("⬅️ Geri dön ve seçimleri değiştir", key=f"{wkey}_back3"):
            state["step"] = 2
            st.rerun(scope="fragment")
        return
    st.dataframe(
        _proposal_df(ctx, result.assignments),
        use_container_width=True,
        hide_index=True,
    )
    show_violations(_check_proposal(ctx, result.assignments))
    c1, c2 = st.columns(2)
    if c1.button("✅ Onayla ve Kaydet", type="primary", key=f"{wkey}_save"):
        _save(ctx, result.assignments)
        st.session_state.pop(wkey, None)
        for k in list(st.session_state):
            if k.startswith(f"{wkey}_suggest"):
                st.session_state.pop(k)
        st.rerun(scope="app")
    if c2.button("⬅️ Geri", key=f"{wkey}_back_final"):
        state["step"] = 2
        st.rerun(scope="fragment")
