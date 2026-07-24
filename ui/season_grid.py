"""Yıllık Tablo — sezonun tamamı tek, Excel benzeri düzenlenebilir ızgarada.

Satırlar öğrenci, sütunlar aylar, her hücre bir açılır menü (o ay gidilen
birim). Geçmiş aylar da yeni ay taslağı da AYNI tablonun içinde görünür;
kullanıcı herhangi bir hücreyi doğrudan değiştirir, tek "Kaydet" ile veriye
yansır.

Kaydırma/düzenleme kararlılığı: st.data_editor'a verilen TABAN veri bir
"nesil" (gen) boyunca SABİT tutulur (session'da önbelleğe alınır) ve kullanıcı
düzenlemeleri editörün DÖNÜŞ değerinden okunur — taban asla düzenlemeyle
yeniden yazılmaz. Böylece her düzenlemede tablo kimliği değişmez: kaydırma
konumu korunur ve seçim ilk denemede uygulanır. Taban yalnız programatik
değişimde (otomatik doldurma / kaydet / geri al) yenilenir (gen artar).
"""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from rotasyon.models import Assignment
from rotasyon.rules import blocking_errors, check_all
from rotasyon.solver import solve_month
from .common import (
    capacity_findings_panel,
    clear_stale_state,
    data_fingerprint,
    groups_in,
    partition_violations,
    replace_month_assignments,
    show_past_violations_enabled,
    unit_label,
    violations_dataframe,
)

_DRAFT_PREFIXES = (
    "grid_gen_", "grid_ed_", "grid_base_", "grid_ov_", "grid_force_",
    "grid_reroll_", "grid_last_auto_",
)
BLANK = "—"  # boş hücre (o ay atama yok)
_WIDTHS = {"Dar": "small", "Orta": "medium", "Geniş": "large"}


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

    # Rotasyon Oluştur ekranıyla aynı kapasite ön-denetimi (bu ekran da
    # rotasyon üretimi için kullanılır).
    capacity_findings_panel(
        students, units, months, assignments, settings, custom_rules
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
    """Grup için birim etiketleri (aktifler + geçmişte kullanılmış pasifler)."""
    labels: dict[str, str] = {}
    for u in units:
        if u.group in (0, group) and u.active and u.quota > 0:
            labels[unit_label(u)] = u.id
    by_id = {u.id: u for u in units}
    for a in assignments:
        if a.student_id in group_ids:
            u = by_id.get(a.unit_id)
            if u is not None:
                labels.setdefault(unit_label(u), u.id)
    return labels


def _bump_gen(group: int) -> None:
    """Nesli artırır ve eski nesle ait taban/editör durumunu temizler.

    Yalnız programatik değişimde (otomatik doldur/kaydet/geri al) çağrılır;
    kullanıcı düzenlemelerinde ÇAĞRILMAZ (taban sabit kalsın, kaydırma
    korunsun)."""
    g = f"grid_gen_{group}"
    old = st.session_state.get(g, 0)
    st.session_state.pop(f"grid_base_{group}_{old}", None)
    st.session_state.pop(f"grid_ed_{group}_{old}", None)
    st.session_state[g] = old + 1


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
            "KAYDEDİLMİŞ geçmişi kullanır. Bekleyen elle değişiklikleriniz "
            "korunur ama geçmiş olarak sayılmaz — gerekirse önce kaydedin."
        )

    labels = _labels_for_group(group, units, assignments, group_ids)
    label_to_id = dict(labels)
    id_to_label = {uid: lbl for lbl, uid in labels.items()}
    options = [BLANK] + sorted(labels)

    saved: dict[tuple[str, str], str] = {
        (a.student_id, a.month): id_to_label[a.unit_id]
        for a in assignments
        if a.student_id in group_ids and a.unit_id in id_to_label
    }

    gen = st.session_state.get(f"grid_gen_{group}", 0)
    ov = st.session_state.setdefault(f"grid_ov_{group}", {})  # otomatik doldurma
    edkey = f"grid_ed_{group}_{gen}"
    basekey = f"grid_base_{group}_{gen}"

    # ---- görünüm kontrolleri ----
    with st.popover("🔧 Görünüm"):
        col_w = _WIDTHS[
            st.select_slider(
                "Sütun genişliği", list(_WIDTHS), value="Orta",
                key=f"grid_w_{group}",
            )
        ]
        show_all = st.checkbox(
            "Tüm satırları göster (dikey kaydırma olmadan)",
            key=f"grid_all_{group}",
        )
        st.caption(
            "Sezonun tamamını tek bakışta görmek için aşağıdaki **renkli "
            "görünüm**i açıp yakınlaştırmayı küçültün."
        )

    # ---- SABİT taban (nesil boyunca değişmez → kaydırma korunur) ----
    if basekey not in st.session_state:
        st.session_state[basekey] = pd.DataFrame(
            [
                {"Öğrenci": s.full_name, "Sınıf": s.class_name,
                 **{m: ov.get((s.id, m), saved.get((s.id, m), BLANK))
                    for m in months}}
                for s in group_students
            ]
        )
    base_df = st.session_state[basekey]

    # ÖNEMLİ: sütun başlıkları/column_config SABİT olmalı. Başlığa düzenleme
    # durumuna göre 🟡 eklemek column_config'i değiştirir; st.data_editor bunu
    # "widget tanımı değişti" sayıp editörü sıfırlar (seçim ilk denemede
    # uygulanmaz + kaydırma başa döner). Bu yüzden değişiklik işareti tabloda
    # DEĞİL, tablonun ALTINDAKİ göstergede verilir.
    col_config = {
        "Öğrenci": st.column_config.TextColumn(disabled=True, pinned=True),
        "Sınıf": st.column_config.TextColumn(disabled=True, width="small"),
    }
    for m in months:
        col_config[m] = st.column_config.SelectboxColumn(
            m, options=options, required=True, width=col_w,
        )
    height = (
        40 + 35 * len(base_df) if show_all
        else min(640, 90 + 35 * len(base_df))
    )
    edited = st.data_editor(
        base_df, column_config=col_config, hide_index=True,
        width="stretch", height=height, key=edkey,
    )

    # ---- canlı durum yalnız DÖNÜŞ değerinden okunur (tabana geri yazılmaz) ----
    live: dict[tuple[str, str], str] = {}
    for s, (_, row) in zip(group_students, edited.iterrows()):
        for m in months:
            live[(s.id, m)] = row[m]
    changed = {k for k, v in live.items() if v != saved.get(k, BLANK)}
    changed_cells = len(changed)
    changed_month_set = {m for (_sid, m) in changed}

    if inactive:
        st.caption(
            f"ℹ️ {len(inactive)} ayrılmış (pasif) öğrenci düzenleme tablosunda "
            "gösterilmez; geçmişleri veride korunur ve renkli görünümde görünür."
        )

    # ---- otomatik doldurma (sıradaki boş ay) ----
    saved_done = {m for (_sid, m) in saved}
    next_empty = next((m for m in months if m not in saved_done), None)
    cbtns = st.columns([3, 2, 3])
    if next_empty:
        if cbtns[0].button(
            f"🚀 {next_empty} ayını otomatik doldur", type="primary",
            key=f"grid_gen_btn_{group}", disabled=bool(missing),
            help="Sıradaki boş ay için çözücü bir taslak üretir ve tabloya "
            "yerleştirir; kaydedene kadar taslaktır.",
        ):
            _autofill(
                settings, months, next_empty, group_students, group, units,
                assignments, custom_rules, id_to_label, ov, saved, live,
            )
    else:
        cbtns[0].caption("✅ Tüm aylar dolu.")

    # son otomatik doldurulan ay hâlâ kaydedilmemiş taslaksa → farklı çözüm dene
    last_auto = st.session_state.get(f"grid_last_auto_{group}")
    if last_auto and last_auto in changed_month_set:
        if cbtns[2].button(
            f"🎲 Farklı çözüm ({last_auto})", key=f"grid_reroll_btn_{group}",
            help="Aynı ay için çözücüden farklı bir taslak ister; "
            "elle değişikliklerinizi ve diğer ayları korur.",
        ):
            avoid = {
                s.id: label_to_id[ov[(s.id, last_auto)]]
                for s in group_students
                if (s.id, last_auto) in ov and ov[(s.id, last_auto)] in label_to_id
            }
            _autofill(
                settings, months, last_auto, group_students, group, units,
                assignments, custom_rules, id_to_label, ov, saved, live,
                reroll=True, avoid=avoid,
            )

    if changed_cells and cbtns[1].button(
        "↩️ Değişiklikleri geri al", key=f"grid_reset_{group}",
    ):
        st.session_state[f"grid_ov_{group}"] = {}
        _bump_gen(group)
        st.rerun(scope="fragment")

    # ---- kural denetimi (canlı durumun tamamı) ----
    proposed = [a for a in assignments if a.student_id not in group_ids]
    for (sid, m), lbl in live.items():
        if lbl in label_to_id:
            proposed.append(
                Assignment(student_id=sid, month=m, unit_id=label_to_id[lbl])
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
    # Kaydı YALNIZ kullanıcının değiştirdiği ay/öğrencilerle ilişkili hatalar
    # engeller; dokunulmayan geçmiş aylardaki eski hatalar (örn. sonradan
    # düşürülmüş kontenjan) yeni kaydı bloklamaz — geçmiş yeniden yazılmaz.
    changed_students = {sid for (sid, _m) in changed}
    blocking = blocking_errors(relevant, changed_month_set, changed_students)
    non_blocking = len(errors) - len(blocking)

    st.divider()
    if changed_cells:
        st.markdown(
            f"🟡 **{changed_cells} hücrede kaydedilmemiş değişiklik** "
            f"(aylar: {', '.join(m for m in months if m in changed_month_set)})."
        )
    else:
        st.caption("Kaydedilmemiş değişiklik yok.")

    # Ayar kapalıyken geçmişe dönük (değiştirmediğiniz ay/öğrenci) ihlaller
    # gösterimden gizlenir. Gizleme YALNIZ gösterimi etkiler; blocking/errors
    # yukarıda TAM 'relevant' kümesinden hesaplandı (kayıt kapısı değişmez).
    show_past = show_past_violations_enabled()
    current, past = partition_violations(relevant, changed_month_set, changed_students)
    shown = relevant if show_past else current
    if shown:
        shown_errs = [v for v in shown if v.severity == "hata"]
        (st.error if shown_errs else st.warning)(
            f"{len(shown_errs)} hata, {len(shown) - len(shown_errs)} uyarı."
            if shown_errs else f"{len(shown)} uyarı."
        )
        st.dataframe(
            violations_dataframe(shown), width="stretch",
            hide_index=True,
        )
        if show_past and non_blocking and not blocking:
            st.caption(
                f"ℹ️ Bu hataların {non_blocking} tanesi değiştirmediğiniz "
                "(geçmiş) aylarda; kaydı engellemez."
            )
    elif past:
        st.info("Güncel kapsamda ihlal yok.")
    else:
        st.success("Bu grup için kural ihlali yok. ✅")
    if not show_past and past:
        st.caption(
            f"🕘 {len(past)} geçmişe dönük uyarı gizli — kenar çubuğundaki "
            "“Geçmişe dönük uyarıları göster” ile açabilirsiniz."
        )

    force = False
    if blocking:
        force = st.checkbox("İhlallere rağmen kaydet", key=f"grid_force_{group}")
    if st.button(
        f"💾 Değişiklikleri kaydet ({changed_cells} hücre)",
        type="primary",
        disabled=changed_cells == 0 or (bool(blocking) and not force),
        key=f"grid_save_{group}",
    ):
        _save(store, months, group_ids, group_students, live, saved, label_to_id)
        st.session_state[f"grid_ov_{group}"] = {}
        _bump_gen(group)
        st.session_state["_grid_flash"] = f"{changed_cells} hücre kaydedildi. ✅"
        st.rerun(scope="app")

    # ---- renkli, salt-okunur, YAKINLAŞTIRILABİLİR önizleme ----
    with st.expander("🎨 Renkli görünüm (salt-okunur, Excel benzeri, yakınlaştırılabilir)"):
        zoom = st.slider(
            "Yakınlaştırma", min_value=40, max_value=120, value=100, step=10,
            format="%d%%", key=f"grid_zoom_{group}",
            help="Sezonun tamamını tek ekranda görmek için küçültün.",
        )
        _colored_preview(group_students, inactive, months, live, saved, classes, zoom)


def _autofill(
    settings, months, target, group_students, group, units, assignments,
    custom_rules, id_to_label, ov, saved, live, reroll=False, avoid=None,
):
    """Hedef ayı çözüp taslağa yerleştirir.

    reroll: farklı tohumla farklı bir çözüm dener. avoid: bu eşlemenin aynısı
    gelirse (eş-maliyetli çözümler) tohum ilerletilip bir kez daha denenir —
    'Farklı çözüm' boşa basılmış gibi olmasın (rotation._solve ile aynı desen).
    """
    group_units = [u for u in units if u.group in (0, group)]
    group_ids = {s.id for s in group_students}
    history = [
        a for a in assignments if a.student_id in group_ids and a.month != target
    ]

    def run(seed):
        return solve_month(
            group_students, group_units, target, history=history,
            settings=settings, custom_rules=custom_rules, random_seed=seed,
        )

    counter_key = f"grid_reroll_{group}_{target}"
    seed = None
    if reroll:
        st.session_state[counter_key] = st.session_state.get(counter_key, 0) + 1
        seed = st.session_state[counter_key]
    with st.spinner(f"{target} için çözücü çalışıyor..."):
        r = run(seed)
        if reroll and avoid is not None and r.ok and r.assignments == avoid:
            st.session_state[counter_key] += 1
            r = run(st.session_state[counter_key])
    if not r.ok:
        st.error(f"{target} için tüm kurallara uyan atama bulunamadı:")
        for reason in r.infeasible_reasons:
            st.markdown(f"- {reason}")
        return
    # bekleyen elle düzenlemeleri koru (yeni tabana taşı), sonra hedef ayı ekle
    for (sid, m), lbl in live.items():
        if lbl != saved.get((sid, m), BLANK):
            ov[(sid, m)] = lbl
    for sid, uid in r.assignments.items():
        if uid in id_to_label:
            ov[(sid, target)] = id_to_label[uid]
    st.session_state[f"grid_ov_{group}"] = ov
    # son otomatik doldurulan ayı hatırla → "Farklı çözüm" onu hedefler
    st.session_state[f"grid_last_auto_{group}"] = target
    if not reroll and any(live[k] != saved.get(k, BLANK) for k in live):
        st.session_state["_grid_autofill_note"] = target
    _bump_gen(group)
    st.rerun(scope="fragment")


def _save(store, months, group_ids, group_students, live, saved, label_to_id):
    """Yalnız DEĞİŞMİŞ ayları veriye yazar."""
    for m in months:
        edited_map = {
            s.id: label_to_id[live[(s.id, m)]]
            for s in group_students
            if live.get((s.id, m)) in label_to_id
        }
        saved_map = {
            s.id: label_to_id[saved[(s.id, m)]]
            for s in group_students
            if (s.id, m) in saved and saved[(s.id, m)] in label_to_id
        }
        if edited_map != saved_map:
            replace_month_assignments(store, group_ids, m, edited_map)


def _colored_preview(group_students, inactive, months, live, saved, classes, zoom):
    """Bütün öğrenciler (pasifler dahil) × aylar, sınıf renkli, HTML tablo.

    HTML tablo (glide canvas değil) olduğu için CSS zoom ile küçültülebilir ve
    tamamı tek ekrana sığdırılabilir; yazdırmaya da uygundur.
    """
    color_of = {c.name: c.color_hex for c in classes if c.color_hex}
    rows_html = []
    header = "".join(f"<th>{html.escape(m)}</th>" for m in months)
    rows_html.append(
        "<tr><th>Öğrenci</th><th>Sınıf</th>" + header + "</tr>"
    )
    all_rows = group_students + sorted(inactive, key=lambda s: s.full_name)
    for s in all_rows:
        bg = color_of.get(s.class_name, "")
        style = f' style="background:{bg};color:#000"' if bg else ""
        passive = " (ayrıldı)" if not s.active else ""
        cells = f"<td{style}>{html.escape(s.full_name)}{passive}</td>" \
                f"<td>{html.escape(s.class_name)}</td>"
        for m in months:
            val = live.get((s.id, m)) if s.active else saved.get((s.id, m), BLANK)
            val = val if val and val != BLANK else ""
            cells += f"<td>{html.escape(val)}</td>"
        rows_html.append(f"<tr>{cells}</tr>")
    table = (
        f'<div style="zoom:{zoom/100}; overflow-x:auto">'
        '<table style="border-collapse:collapse;font-size:13px" border="1">'
        + "".join(rows_html) + "</table></div>"
    )
    st.markdown(
        "<style>table td,table th{padding:2px 6px;border:1px solid #555}</style>"
        + table,
        unsafe_allow_html=True,
    )
