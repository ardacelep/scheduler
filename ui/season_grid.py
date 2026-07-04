"""Yıllık Tablo — sezonun tamamı tek, Excel benzeri düzenlenebilir ızgarada.

Satırlar öğrenci, sütunlar aylar, her hücre o ay gidilen birim (açılır menü).
Geçmiş aylar da yeni ay taslağı da AYNI tablonun içinde görünür; kullanıcı
herhangi bir hücreyi doğrudan değiştirir, tek "Kaydet" ile veriye yansır.

Taslak/kaydedilmemiş değişiklik işareti: ilgili ay sütunu başlığında 🟡 +
"N hücre kaydedilmedi" göstergesi (Streamlit'in düzenlenebilir tablosu tek
tek hücre renklendiremediğinden; renkli Excel görünümü ayrıca salt-okunur
önizleme olarak sunulur). Kaydettikten sonra tüm sezon kurallara karşı
denetlenir.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from rotasyon.models import Assignment
from rotasyon.rules import check_all
from rotasyon.solver import solve_month
from .common import (
    clear_stale_state,
    data_fingerprint,
    groups_in,
    replace_month_assignments,
    unit_label,
    violations_dataframe,
)

_DRAFT_PREFIXES = ("grid_work_", "grid_gen_", "grid_ed_", "grid_force_")
BLANK = "—"  # boş hücre (öğrenci o ay hiçbir birime atanmamış)


def render(store) -> None:
    st.header("📅 Yıllık Tablo")
    if msg := st.session_state.pop("_grid_flash", None):
        st.success(msg)

    students = store.load_students()
    units = store.load_units()
    if not students or not units:
        st.info("Önce Veri Yönetimi ekranından öğrenci ve birim ekleyin.")
        return
    settings = store.load_settings()
    months = settings["months"]
    assignments = store.load_assignments()
    custom_rules = [r for r in store.load_custom_rules() if r.active]
    classes = store.load_classes()

    clear_stale_state(
        "_grid_fp",
        data_fingerprint(students, units, assignments, custom_rules, [settings]),
        _DRAFT_PREFIXES,
    )

    group = st.selectbox(
        "Grup", groups_in(students), format_func=lambda g: f"{g}. Grup",
        key="grid_group",
    )
    st.caption(
        "Tablo doğrudan düzenlenebilir (Excel gibi): bir hücreye tıklayıp "
        "birimi değiştirin. Her öğrencinin önceki aylarda gittiği birimler "
        "aynı satırda görünür. Değişiklikler **Kaydet**'e basana kadar veriye "
        "yazılmaz."
    )
    _grid(
        store, settings, months, group, students, units, assignments,
        custom_rules, classes,
    )


def _labels_for_group(group, units, assignments, group_ids):
    """Grup için birim etiketleri (aktifler) + geçmişte kullanılmış birimler.

    Pasifleştirilmiş/eski birimler de listeye girer ki geçmiş hücreler
    boş görünmesin ve seçilebilsin.
    """
    labels: dict[str, str] = {}  # etiket -> unit_id
    for u in units:
        if u.group in (0, group) and u.active and u.quota > 0:
            labels[unit_label(u)] = u.id
    used_ids = {
        a.unit_id for a in assignments if a.student_id in group_ids
    }
    by_id = {u.id: u for u in units}
    for uid in used_ids:
        u = by_id.get(uid)
        if u is not None:
            labels.setdefault(unit_label(u), u.id)
    return labels


@st.fragment
def _grid(
    store, settings, months, group, students, units, assignments,
    custom_rules, classes,
):
    group_students = sorted(
        [s for s in students if s.group == group and s.active],
        key=lambda s: (s.class_name, s.full_name),
    )
    inactive = [s for s in students if s.group == group and not s.active]
    group_ids = {s.id for s in group_students}
    units_by_id = {u.id: u for u in units}

    missing = [s.full_name for s in group_students if not s.gender]
    if missing:
        st.error(
            "Şu öğrencilerin cinsiyeti eksik (kurallar için gerekli): "
            + ", ".join(missing) + " — Veri Yönetimi'nden tamamlayın."
        )
    if note := st.session_state.pop("_grid_autofill_note", None):
        st.info(
            f"ℹ️ **{note}** otomatik dolduruldu; otomatik doldurma yalnız "
            "KAYDEDİLMİŞ geçmişi kullanır, o sırada bekleyen kaydedilmemiş "
            "değişiklikleriniz dikkate alınmadı. Gerekirse önce kaydedip "
            "yeniden doldurun."
        )

    labels = _labels_for_group(group, units, assignments, group_ids)
    label_to_id = dict(labels)
    id_to_label = {uid: lbl for lbl, uid in labels.items()}
    options = [BLANK] + sorted(labels)

    # kaydedilmiş durum: (sid, ay) -> etiket
    saved: dict[tuple[str, str], str] = {}
    for a in assignments:
        if a.student_id in group_ids and a.unit_id in id_to_label:
            saved[(a.student_id, a.month)] = id_to_label[a.unit_id]

    # çalışma durumu (kullanıcının o ana kadarki düzenlemeleri) — session'da yaşar
    wkey = f"grid_work_{group}"
    if wkey not in st.session_state:
        st.session_state[wkey] = {
            (s.id, m): saved.get((s.id, m), BLANK)
            for s in group_students for m in months
        }
    work = st.session_state[wkey]
    # yeni öğrenci/ay eklenmişse boş doldur
    for s in group_students:
        for m in months:
            work.setdefault((s.id, m), saved.get((s.id, m), BLANK))

    # değişmiş aylar (başlıkta 🟡 ve gösterge için) — çalışma vs kaydedilmiş
    changed_cells = 0
    changed_months = set()
    for s in group_students:
        for m in months:
            if work[(s.id, m)] != saved.get((s.id, m), BLANK):
                changed_cells += 1
                changed_months.add(m)

    # ---- düzenlenebilir ızgara ----
    gen = st.session_state.get(f"grid_gen_{group}", 0)
    df = pd.DataFrame(
        [
            {"Öğrenci": s.full_name, "Sınıf": s.class_name,
             **{m: work[(s.id, m)] for m in months}}
            for s in group_students
        ]
    )
    col_config = {
        "Öğrenci": st.column_config.TextColumn(disabled=True, pinned=True),
        "Sınıf": st.column_config.TextColumn(disabled=True, width="small"),
    }
    for m in months:
        col_config[m] = st.column_config.SelectboxColumn(
            f"{m} 🟡" if m in changed_months else m,
            options=options, required=True, width="medium",
        )
    edited = st.data_editor(
        df, column_config=col_config, hide_index=True,
        use_container_width=True, height=min(640, 90 + 35 * len(df)),
        key=f"grid_ed_{group}_{gen}",
    )
    # kullanıcının düzenlemelerini çalışma durumuna işle
    for s, (_, row) in zip(group_students, edited.iterrows()):
        for m in months:
            work[(s.id, m)] = row[m]
    st.session_state[wkey] = work

    if inactive:
        st.caption(
            f"ℹ️ {len(inactive)} ayrılmış (pasif) öğrenci tabloda gösterilmez; "
            "geçmişleri veride korunur."
        )

    # ---- otomatik doldurma (sıradaki boş ay) ----
    saved_months_done = {m for (_sid, m), lbl in saved.items()}
    next_empty = next((m for m in months if m not in saved_months_done), None)
    cbtns = st.columns([2, 2, 3])
    if next_empty:
        if cbtns[0].button(
            f"🚀 {next_empty} ayını otomatik doldur", type="primary",
            key=f"grid_gen_btn_{group}", disabled=bool(missing),
            help="Sıradaki boş ay için çözücü bir taslak üretir ve tabloya "
            "yerleştirir; kaydedene kadar taslaktır.",
        ):
            _autofill(
                store, settings, months, next_empty, group_students,
                group, units, assignments, custom_rules, id_to_label, work,
                saved,
            )
    else:
        cbtns[0].caption("✅ Tüm aylar dolu.")

    if changed_cells and cbtns[1].button(
        "↩️ Değişiklikleri geri al", key=f"grid_reset_{group}",
    ):
        del st.session_state[wkey]
        st.session_state[f"grid_gen_{group}"] = gen + 1
        st.rerun(scope="fragment")

    # ---- kural denetimi (çalışma durumunun tamamı) ----
    proposed = [
        a for a in assignments if a.student_id not in group_ids
    ]
    for s in group_students:
        for m in months:
            lbl = work[(s.id, m)]
            if lbl in label_to_id:
                proposed.append(
                    Assignment(student_id=s.id, month=m, unit_id=label_to_id[lbl])
                )
    violations = check_all(
        students, units, proposed, months,
        custom_rules=custom_rules, settings=settings,
    )
    group_unit_ids = {u.id for u in units if u.group in (0, group)}
    relevant = [
        v for v in violations
        if (not v.student_id and not v.unit_id)
        or v.student_id in group_ids
        or v.unit_id in group_unit_ids
    ]
    errors = [v for v in relevant if v.severity == "hata"]

    st.divider()
    if changed_cells:
        st.markdown(
            f"🟡 **{changed_cells} hücrede kaydedilmemiş değişiklik** "
            f"(aylar: {', '.join(m for m in months if m in changed_months)})."
        )
    else:
        st.caption("Kaydedilmemiş değişiklik yok.")

    if relevant:
        (st.error if errors else st.warning)(
            f"{len(errors)} hata, {len(relevant) - len(errors)} uyarı."
            if errors else f"{len(relevant)} uyarı."
        )
        st.dataframe(
            violations_dataframe(relevant), use_container_width=True,
            hide_index=True,
        )
    else:
        st.success("Bu grup için kural ihlali yok. ✅")

    force = False
    if errors:
        force = st.checkbox(
            "İhlallere rağmen kaydet", key=f"grid_force_{group}"
        )
    if st.button(
        f"💾 Değişiklikleri kaydet ({changed_cells} hücre)",
        type="primary",
        disabled=changed_cells == 0 or (bool(errors) and not force),
        key=f"grid_save_{group}",
    ):
        _save(store, months, group_ids, group_students, work, saved, label_to_id)
        del st.session_state[wkey]
        st.session_state[f"grid_gen_{group}"] = gen + 1
        st.session_state["_grid_flash"] = (
            f"{changed_cells} hücre kaydedildi. ✅"
        )
        st.rerun(scope="app")

    # ---- renkli, salt-okunur önizleme (Excel görünümü) ----
    with st.expander("🎨 Renkli görünüm (salt-okunur, Excel benzeri)"):
        _colored_preview(group_students, months, work, classes)


def _autofill(
    store, settings, months, target, group_students, group, units,
    assignments, custom_rules, id_to_label, work, saved,
):
    # otomatik doldurma KAYDEDİLMİŞ geçmişe göre çalışır
    has_unsaved = any(
        work[(s.id, m)] != saved.get((s.id, m), BLANK)
        for s in group_students for m in months
    )
    group_units = [u for u in units if u.group in (0, group)]
    group_ids = {s.id for s in group_students}
    history = [
        a for a in assignments
        if a.student_id in group_ids and a.month != target
    ]
    with st.spinner(f"{target} için çözücü çalışıyor..."):
        r = solve_month(
            group_students, group_units, target, history=history,
            settings=settings, custom_rules=custom_rules,
        )
    if not r.ok:
        st.error(f"{target} için tüm kurallara uyan atama bulunamadı:")
        for reason in r.infeasible_reasons:
            st.markdown(f"- {reason}")
        return
    for sid, uid in r.assignments.items():
        if uid in id_to_label:
            work[(sid, target)] = id_to_label[uid]
    st.session_state[f"grid_work_{group}"] = work
    st.session_state[f"grid_gen_{group}"] = (
        st.session_state.get(f"grid_gen_{group}", 0) + 1
    )
    if has_unsaved:
        st.session_state["_grid_autofill_note"] = target
    st.rerun(scope="fragment")


def _save(store, months, group_ids, group_students, work, saved, label_to_id):
    """Yalnız DEĞİŞMİŞ ayları veriye yazar (gereksiz yedek/churn olmasın)."""
    for m in months:
        edited_map = {
            s.id: label_to_id[work[(s.id, m)]]
            for s in group_students
            if work[(s.id, m)] in label_to_id
        }
        saved_map = {
            s.id: label_to_id[saved[(s.id, m)]]
            for s in group_students
            if (s.id, m) in saved and saved[(s.id, m)] in label_to_id
        }
        if edited_map != saved_map:
            replace_month_assignments(store, group_ids, m, edited_map)


def _colored_preview(group_students, months, work, classes):
    color_of = {c.name: c.color_hex for c in classes if c.color_hex}
    df = pd.DataFrame(
        [
            {"Öğrenci": s.full_name, "Sınıf": s.class_name,
             **{m: work[(s.id, m)] for m in months}}
            for s in group_students
        ]
    )
    name_colors = [color_of.get(s.class_name, "") for s in group_students]

    def _style(_):
        style = pd.DataFrame("", index=df.index, columns=df.columns)
        loc = df.columns.get_loc("Öğrenci")
        for i, hexc in enumerate(name_colors):
            if hexc:
                style.iloc[i, loc] = f"background-color: {hexc}; color: #000"
        return style

    st.dataframe(
        df.style.apply(_style, axis=None), use_container_width=True,
        hide_index=True, height=min(600, 90 + 35 * len(df)),
    )
