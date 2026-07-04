"""Yıllık Tablo — sezonun tamamını tek ekranda gör, oluştur ve düzenle.

Dışa aktarılan yıllık Excel görünümünün uygulama içi, canlı ve düzenlenebilir
hâli: satırlar öğrenci, sütunlar aylar, hücreler o ay gidilen birim. Öğrenci
adı sınıf rengiyle boyanır (Excel'deki gibi). Aynı ekrandan:

- boş (sıradaki) ayın rotasyonu OLUŞTURULUR,
- herhangi bir planlanmış ay ELLE DÜZELTİLİR,

ve düzeltme yapılırken her öğrencinin diğer aylardaki geçmişi hem üstteki
tabloda hem düzenleme satırında ("şimdiye dek gittiği birimler") görünür;
böylece elle karar tüm sezon bağlamıyla verilir. Hiçbir şey onaylanmadan
kaydedilmez; kaydettikten sonra tüm sezon kurallara karşı denetlenir.
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
    gender_label,
    groups_in,
    replace_month_assignments,
    show_violations,
    unit_label,
    violations_dataframe,
)

_DRAFT_PREFIXES = ("grid_draft_", "grid_editor_", "grid_reroll_")
_EMPTY = "—"


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

    # başka ekranda veri değiştiyse bekleyen taslak/düzenleyici bayattır
    clear_stale_state(
        "_grid_fp",
        data_fingerprint(students, units, assignments, custom_rules, [settings]),
        _DRAFT_PREFIXES,
    )

    group = st.selectbox(
        "Grup", groups_in(students), format_func=lambda g: f"{g}. Grup",
        key="grid_group",
    )
    group_students = sorted(
        [s for s in students if s.group == group],
        key=lambda s: (s.class_name, s.full_name),
    )
    group_ids = {s.id for s in group_students}
    group_units = [u for u in units if u.group in (0, group)]
    units_by_id = {u.id: u for u in units}

    st.caption(
        "Bu tablo, dışa aktarılan yıllık görünümün canlı hâlidir: her "
        "öğrencinin sezon boyunca gittiği birimler bir arada görünür. "
        "Aşağıdan bir ayı oluşturabilir veya elle düzeltebilirsiniz."
    )
    _yearly_grid(group_students, months, assignments, units_by_id, classes)

    st.divider()
    _edit_section(
        store, settings, months, group, group_students, group_ids,
        group_units, units_by_id, assignments, custom_rules, students,
    )


# ---------------- yıllık tablo (salt görünüm) ----------------

def _yearly_grid(group_students, months, assignments, units_by_id, classes):
    cell = {
        (a.student_id, a.month): a
        for a in assignments
        if a.student_id in {s.id for s in group_students}
    }
    color_of = {c.name: c.color_hex for c in classes if c.color_hex}

    rows = []
    for s in group_students:
        name = s.full_name + ("  (ayrıldı)" if not s.active else "")
        row = {"Öğrenci": name, "Sınıf": s.class_name}
        for m in months:
            a = cell.get((s.id, m))
            row[m] = (
                units_by_id[a.unit_id].display_name
                if a and a.unit_id in units_by_id
                else _EMPTY
            )
        rows.append(row)
    df = pd.DataFrame(rows)

    # öğrenci adı hücresini sınıf rengiyle boya (Excel görünümüne benzer)
    name_colors = [color_of.get(s.class_name, "") for s in group_students]

    def _style(_):
        style = pd.DataFrame("", index=df.index, columns=df.columns)
        for i, hexc in enumerate(name_colors):
            if hexc:
                style.iloc[i, df.columns.get_loc("Öğrenci")] = (
                    f"background-color: {hexc}; color: #000"
                )
        return style

    st.dataframe(
        df.style.apply(_style, axis=None),
        use_container_width=True,
        hide_index=True,
        height=min(600, 90 + 35 * len(df)),
    )
    done = sum(1 for m in months if any(cell.get((s.id, m)) for s in group_students))
    st.caption(f"Bu grupta {len(group_students)} öğrenci · {done}/{len(months)} ay dolu.")


# ---------------- oluştur / düzenle ----------------

def _history_string(sid, month, months, assignments, units_by_id) -> str:
    """Öğrencinin SEÇİLİ AY DIŞINDAKI aylarda gittiği birimler, ay sırasıyla."""
    order = {m: i for i, m in enumerate(months)}
    items = sorted(
        (
            a for a in assignments
            if a.student_id == sid and a.month != month and a.month in order
        ),
        key=lambda a: order[a.month],
    )
    parts = [
        units_by_id[a.unit_id].display_name
        for a in items
        if a.unit_id in units_by_id
    ]
    return ", ".join(parts) if parts else "—"


def _edit_section(
    store, settings, months, group, group_students, group_ids,
    group_units, units_by_id, assignments, custom_rules, all_students,
):
    st.subheader("✏️ Ay oluştur / düzenle")

    active_students = [s for s in group_students if s.active]
    missing = [s.full_name for s in active_students if not s.gender]
    if missing:
        st.error(
            "Şu öğrencilerin cinsiyeti eksik (kurallar için gerekli): "
            + ", ".join(missing)
            + " — Veri Yönetimi'nden tamamlayın."
        )
        return

    months_done = {
        a.month for a in assignments
        if a.student_id in group_ids
    }
    next_month = next((m for m in months if m not in months_done), None)

    month = st.selectbox(
        "Ay", months,
        index=months.index(next_month) if next_month else len(months) - 1,
        key="grid_month",
    )
    is_planned = month in months_done
    dkey = f"grid_draft_{group}_{month}"

    existing = {
        a.student_id: a.unit_id
        for a in assignments
        if a.student_id in group_ids and a.month == month
    }

    # ---- boş ay: sıradaki değilse oluşturma engellenir (sıra korunur) ----
    if not is_planned and dkey not in st.session_state:
        if month != next_month:
            st.info(
                f"**{month}** henüz boş. Aylar sırayla planlanır; önce "
                f"**{next_month}** ayını oluşturun."
            )
            return
        st.caption(
            f"**{month}** için henüz rotasyon yok. Otomatik oluşturun, sonra "
            "gerekirse elle düzeltip kaydedin."
        )
        if st.button("🚀 Bu ayı otomatik oluştur", type="primary", key=f"gen_{group}_{month}"):
            _generate(store, settings, month, active_students, group_units, assignments, custom_rules, dkey)
            st.rerun()
        return

    # ---- düzenlenecek başlangıç eşlemesi: taslak > kayıt ----
    draft = st.session_state.get(dkey)
    base = draft if draft is not None else existing
    if draft is not None:
        st.markdown(f"🟡 **{month}: kaydedilmemiş taslak** — düzeltip kaydedin.")
    else:
        st.markdown(f"🟢 **{month}: kayıtlı** — hücreleri değiştirip kaydedebilirsiniz.")

    mapping = _month_editor(
        group, month, active_students, group_units, units_by_id, base,
        months, assignments,
    )

    # tüm sezon denetimi (bu ay değiştirilmiş hâliyle), gruba göre süzülür
    proposed = [
        a for a in assignments
        if not (a.student_id in group_ids and a.month == month)
    ] + [
        Assignment(student_id=sid, month=month, unit_id=uid)
        for sid, uid in mapping.items()
    ]
    violations = check_all(
        all_students, list(units_by_id.values()), proposed, months,
        custom_rules=custom_rules, settings=settings,
    )
    group_unit_ids = {u.id for u in group_units}
    relevant = [
        v for v in violations
        if (not v.student_id and not v.unit_id)
        or v.student_id in group_ids
        or v.unit_id in group_unit_ids
        or v.month == month
    ]
    _show_scoped_violations(relevant, month)
    errors = [v for v in relevant if v.severity == "hata"]

    force = False
    if errors:
        force = st.checkbox(
            "İhlallere rağmen kaydet", key=f"grid_force_{group}_{month}"
        )
    c1, c2, c3 = st.columns(3)
    if c1.button(
        "💾 Kaydet", type="primary",
        disabled=bool(errors) and not force, key=f"grid_save_{group}_{month}",
    ):
        replace_month_assignments(store, group_ids, month, mapping)
        st.session_state.pop(dkey, None)
        st.session_state["_grid_flash"] = f"{month} ayı kaydedildi. ✅"
        st.rerun()
    if c2.button(
        "🎲 Yeniden oluştur", key=f"grid_regen_{group}_{month}",
        help="Aynı kurallarla farklı bir dağılım üretir (taslak olarak).",
    ):
        _generate(
            store, settings, month, active_students, group_units, assignments,
            custom_rules, dkey, reroll=True,
        )
        st.rerun()
    if draft is not None and c3.button(
        "↩️ Taslağı bırak", key=f"grid_discard_{group}_{month}",
        help="Taslağı at; kayıtlı hâline dön.",
    ):
        st.session_state.pop(dkey, None)
        st.rerun()


def _month_editor(
    group, month, active_students, group_units, units_by_id, base,
    months, assignments,
):
    """Seçili ayın düzenleme tablosu; her satırda öğrencinin geçmişi görünür."""
    labels = {
        unit_label(u): u.id for u in group_units if u.active and u.quota > 0
    }
    rows = []
    for s in active_students:
        uid = base.get(s.id)
        rows.append(
            {
                "Öğrenci": s.full_name,
                "Sınıf": s.class_name,
                "Şimdiye dek gittiği birimler": _history_string(
                    s.id, month, months, assignments, units_by_id
                ),
                "Birim": unit_label(units_by_id[uid])
                if uid in units_by_id else None,
            }
        )
    edited = st.data_editor(
        pd.DataFrame(rows),
        column_config={
            "Öğrenci": st.column_config.TextColumn(disabled=True),
            "Sınıf": st.column_config.TextColumn(disabled=True, width="small"),
            "Şimdiye dek gittiği birimler": st.column_config.TextColumn(
                disabled=True, width="large",
                help="Bu öğrencinin diğer aylarda gittiği birimler — elle "
                "seçim yaparken tekrar olmaması için buna bakın.",
            ),
            "Birim": st.column_config.SelectboxColumn(
                "Birim", options=sorted(labels), required=True
            ),
        },
        use_container_width=True,
        hide_index=True,
        height=min(560, 90 + 35 * len(rows)),
        key=f"grid_editor_{group}_{month}",
    )
    mapping = {}
    for s, (_, row) in zip(active_students, edited.iterrows()):
        lbl = row["Birim"]
        if lbl in labels:
            mapping[s.id] = labels[lbl]
    return mapping


def _generate(
    store, settings, month, active_students, group_units, assignments,
    custom_rules, dkey, reroll=False,
):
    history = [
        a for a in assignments
        if a.student_id in {s.id for s in active_students} and a.month != month
    ]
    seed = None
    if reroll:
        rk = f"grid_reroll_{dkey}"
        st.session_state[rk] = st.session_state.get(rk, 0) + 1
        seed = st.session_state[rk]
    with st.spinner("Çözücü çalışıyor..."):
        r = solve_month(
            active_students, group_units, month, history=history,
            settings=settings, random_seed=seed, custom_rules=custom_rules,
        )
    if r.ok:
        st.session_state[dkey] = dict(r.assignments)
    else:
        st.error("Bu ay için tüm kurallara uyan atama bulunamadı:")
        for reason in r.infeasible_reasons:
            st.markdown(f"- {reason}")


def _show_scoped_violations(violations, month):
    errors = [v for v in violations if v.severity == "hata"]
    warnings = [v for v in violations if v.severity == "uyarı"]
    if not violations:
        st.success("Bu grup için kural ihlali yok. ✅")
        return
    if errors:
        st.error(f"{len(errors)} kural ihlali (hata).")
    if warnings:
        st.warning(f"{len(warnings)} uyarı.")
    st.dataframe(
        violations_dataframe(violations),
        use_container_width=True,
        hide_index=True,
    )
