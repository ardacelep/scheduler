"""Rotasyon Oluştur — tek akışlı ekran.

Seçili grup+ay için TEK görünüm vardır ve üç durumdan birindedir:
  ⚪ oluşturulmadı → üretim seçenekleri (otomatik / sihirbaz)
  🟡 taslak       → incele, elle düzenle, farklı çözüm dene, kaydet
  🟢 kayıtlı      → incele, elle düzenle, yeniden oluştur (taslak üretir)

Üretim yöntemi ne olursa olsun sonuç aynı taslağa akar; "elle düzenleme"
ayrı bir mod değil, taslağın/kaydın üzerinde bir anahtardır. Böylece eski
üç-sekme yapısının "iki kopya bağımsız yaşıyor" karışıklığı oluşmaz.

Çözücü asla sayfa render'ında kendiliğinden koşmaz; yalnız butonla tetiklenir.
Alt bölümdeki "Toplu oluşturma" kalan ayları sırayla çözer (sezon başı veya
ortası fark etmez: dolu aylar geçmiş kabul edilir).
"""
from __future__ import annotations

import threading

import pandas as pd
import streamlit as st

from rotasyon.models import Assignment
from rotasyon.planner import plan_season, remaining_months
from rotasyon.rules import blocking_errors, check_all
from rotasyon.solver import solve_month, visited_unit_keys
from rotasyon.normalize import normalize_key
from .common import (
    capacity_findings_panel,
    clear_stale_state,
    data_fingerprint,
    gender_label,
    groups_in,
    replace_month_assignments,
    show_violations_scoped,
    unit_label,
)

# Taslak öneriler, sihirbaz adımları, düzenleyici durumu... — hepsi veriden
# türetilir; veri değişince clear_stale_state ile silinirler.
_DRAFT_PREFIXES = (
    "proposal_", "wizard_", "editor_", "edit_", "gen_", "reroll_",
    "force_", "bulk_",
)


def month_options(months: list[str], done: set[str]) -> tuple[list[str], str | None]:
    """Seçilebilir aylar: oluşturulmuş aylar + sıradaki İLK boş ay.

    Rotasyonlar EYLÜL'den başlayarak sırayla planlanır; ay atlanamaz.
    İçe aktarılan veride boşluk varsa (örn. EYLÜL ve KASIM dolu, EKİM boş)
    sıradaki ay boşluğu kapatır. Dönüş: (seçenekler, sıradaki boş ay).
    """
    next_month = next((m for m in months if m not in done), None)
    allowed = [m for m in months if m in done or m == next_month]
    return allowed, next_month


def render(store) -> None:
    st.header("🔄 Rotasyon Oluştur")
    if msg := st.session_state.pop("_rotation_flash", None):
        st.success(msg)
    all_students = store.load_students()
    # ayrılan (pasif) öğrenciler yeni aylara atanmaz; geçmişleri korunur
    students = [s for s in all_students if s.active]
    units = store.load_units()
    if not students or not units:
        st.info("Önce Veri Yönetimi ekranından öğrenci ve birim ekleyin.")
        return
    settings = store.load_settings()
    months = settings["months"]
    all_assignments = store.load_assignments()

    # Kapasite ön-denetimi: sezon 8. ayda duvara çarpmadan ÖNCE söyle.
    # (students zaten aktiflere süzülmüş — panel de aktifleri kullanır.)
    capacity_findings_panel(students, units, months, all_assignments)

    c1, c2 = st.columns(2)
    group = c1.selectbox(
        "Grup", groups_in(students), format_func=lambda g: f"{g}. Grup"
    )
    group_students = sorted(
        [s for s in students if s.group == group], key=lambda s: s.full_name
    )
    group_ids = {s.id for s in group_students}
    months_done = {
        a.month for a in all_assignments if a.student_id in group_ids
    }
    allowed_months, next_month = month_options(months, months_done)
    month = c2.selectbox(
        "Ay",
        allowed_months,
        index=allowed_months.index(next_month)
        if next_month in allowed_months
        else len(allowed_months) - 1,
        help="Rotasyonlar sezon başından itibaren SIRAYLA oluşturulur; "
        "ay atlanamaz. Oluşturulmuş ayları yeniden açabilirsiniz.",
    )
    if next_month:
        st.caption(f"📆 Bu grup için sıradaki ay: **{next_month}**")

    group_units = [u for u in units if u.group in (0, group)]
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
    _flow(ctx)

    st.divider()
    _bulk_section(
        dict(
            store=store,
            students=students,
            units=units,
            settings=settings,
            custom_rules=custom_rules,
            assignments=all_assignments,
        )
    )


# ---------- ortak yardımcılar ----------

def _pkey(ctx) -> str:
    return f"proposal_{ctx['group']}_{ctx['month']}"


def _bump_gen(g, m) -> None:
    """Düzenleyici neslini artırır: data_editor taze anahtar alır, eski
    hücre düzenlemeleri yeni taslağın üzerine binmez."""
    k = f"gen_{g}_{m}"
    st.session_state[k] = st.session_state.get(k, 0) + 1


def _solve(ctx, locked=None, reroll=False, avoid=None):
    """Ayı çözer. reroll: farklı tohumla; avoid: bu eşlemenin aynısı
    gelirse (eş-maliyetli çözümlerde olabilir) tohum ilerletilip bir kez
    daha denenir — 'Farklı çözüm' butonu boşa basılmış gibi olmasın."""

    def run(seed):
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

    counter_key = f"reroll_{ctx['group']}_{ctx['month']}"
    seed = None
    if reroll:
        st.session_state[counter_key] = st.session_state.get(counter_key, 0) + 1
        seed = st.session_state[counter_key]
    with st.spinner("Çözücü çalışıyor..."):
        result = run(seed)
        if (
            reroll
            and avoid is not None
            and result.ok
            and result.assignments == avoid
        ):
            st.session_state[counter_key] += 1
            result = run(st.session_state[counter_key])
    return result


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
        settings=ctx["settings"],
    )


def _save(ctx, mapping: dict[str, str]) -> None:
    replace_month_assignments(
        ctx["store"], ctx["group_ids"], ctx["month"], mapping
    )
    st.session_state.pop(_pkey(ctx), None)
    st.session_state["_rotation_flash"] = (
        f"{ctx['month']} ayı ataması kaydedildi. ✅"
    )


def _show_infeasible(result) -> None:
    st.error("Bu ay için tüm kurallara uyan bir atama bulunamadı.")
    st.markdown("**Olası nedenler:**")
    for reason in result.infeasible_reasons:
        st.markdown(f"- {reason}")


def _editor(ctx, mapping: dict[str, str]) -> dict[str, str]:
    """Taslağı/kaydı hücre hücre düzenleme tablosu; yeni eşlemeyi döndürür."""
    g, m = ctx["group"], ctx["month"]
    gen = st.session_state.get(f"gen_{g}_{m}", 0)
    units_by_label = {
        unit_label(u): u for u in ctx["units"] if u.active and u.quota > 0
    }
    units_by_id = {u.id: u for u in ctx["units"]}
    df = pd.DataFrame(
        [
            {
                "Öğrenci": s.full_name,
                "Sınıf": s.class_name,
                "Cinsiyet": gender_label(s.gender),
                "Birim": unit_label(units_by_id[mapping[s.id]])
                if mapping.get(s.id) in units_by_id
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
        width="stretch",
        hide_index=True,
        key=f"editor_{g}_{m}_{gen}",
    )
    new_mapping: dict[str, str] = {}
    for s, (_, row) in zip(ctx["students"], edited.iterrows()):
        label = row["Birim"]
        if label in units_by_label:
            new_mapping[s.id] = units_by_label[label].id
    return new_mapping


# ---------- durum temizleme callback'leri ----------
# (widget durumu ancak callback'te — widget'lar kurulmadan önce —
#  güvenle değiştirilebilir)

def _cb_discard_draft(g, m) -> None:
    st.session_state.pop(f"proposal_{g}_{m}", None)
    st.session_state[f"edit_{g}_{m}"] = False
    _bump_gen(g, m)


def _cb_cancel_edit(g, m) -> None:
    st.session_state[f"edit_{g}_{m}"] = False
    _bump_gen(g, m)


def _cb_close_wizard(g, m) -> None:
    for k in list(st.session_state):
        if isinstance(k, str) and k.startswith(f"wizard_{g}_{m}"):
            del st.session_state[k]


# ---------- ana akış ----------

@st.fragment
def _flow(ctx) -> None:
    g, m = ctx["group"], ctx["month"]
    wizard_on = st.session_state.get(f"wizard_{g}_{m}", {}).get("step", 0) > 0
    draft = st.session_state.get(_pkey(ctx))
    existing = ctx["existing"]

    if wizard_on:
        _wizard(ctx)
        return
    if draft is not None:
        note = " — kaydedene kadar mevcut kayıt korunur" if existing else ""
        st.markdown(f"🟡 **{m}: kaydedilmemiş taslak**{note}")
        _draft_view(ctx, draft)
        return
    if existing:
        st.markdown(f"🟢 **{m}: kayıtlı rotasyon** ({len(existing)} öğrenci)")
        _saved_view(ctx)
        return
    st.markdown(f"⚪ **{m}: henüz rotasyon oluşturulmadı**")
    _generate_view(ctx)


def _generate_view(ctx) -> None:
    g, m = ctx["group"], ctx["month"]
    st.caption(
        "Sonuç önce **taslak** olarak gösterilir; siz onaylayıp "
        "kaydetmeden hiçbir şey değişmez."
    )
    c1, c2 = st.columns(2)
    if c1.button("🚀 Otomatik oluştur", type="primary", key=f"go_auto_{g}_{m}"):
        result = _solve(ctx)
        if result.ok:
            st.session_state[_pkey(ctx)] = result.assignments
            _bump_gen(g, m)
            st.rerun(scope="fragment")
        else:
            _show_infeasible(result)
    if c2.button(
        "🧭 Sihirbazla adım adım", key=f"go_wiz_{g}_{m}",
        help="Önce tekli ve kısıtlı birimleri siz onaylarsınız, "
        "kalanı otomatik dağıtılır.",
    ):
        st.session_state[f"wizard_{g}_{m}"] = {"step": 1, "locks": {}}
        st.rerun(scope="fragment")


def _draft_view(ctx, draft: dict[str, str]) -> None:
    g, m = ctx["group"], ctx["month"]
    edit = st.toggle(
        "✏️ Elle düzenle", key=f"edit_{g}_{m}",
        help="Hücrelere tıklayıp birimi değiştirin; her değişiklikte "
        "kural denetimi çalışır.",
    )
    if edit:
        # Not: düzenlemeler editörün DÖNÜŞ değerinden okunur; taslağa
        # (_pkey) geri YAZILMAZ. Geri yazmak, data_editor'ın taban verisini
        # her turda değiştirip kaydırma konumunu sıfırlıyor ve seçimin ilk
        # denemede uygulanmamasına yol açıyordu. Taban sabit → sorun çözülür.
        mapping = _editor(ctx, draft)
    else:
        mapping = draft
        st.dataframe(
            _proposal_df(ctx, mapping),
            width="stretch",
            hide_index=True,
        )
    violations = _check_proposal(ctx, mapping)
    show_violations_scoped(violations, {m}, ctx["group_ids"])
    # Kaydı yalnız BU AY / bu grubun öğrencilerine dokunan hatalar engeller;
    # değiştirilmeyen geçmiş aylardaki eski hatalar yeni kaydı bloklamaz.
    blocking = blocking_errors(violations, {m}, ctx["group_ids"])
    force = False
    if blocking:
        force = st.checkbox(
            "İhlallere rağmen kaydetmek istiyorum", key=f"force_{g}_{m}"
        )
    c1, c2, c3 = st.columns(3)
    if c1.button(
        "✅ Onayla ve Kaydet", type="primary",
        disabled=bool(blocking) and not force, key=f"dsave_{g}_{m}",
    ):
        _save(ctx, mapping)
        st.rerun(scope="app")
    if c2.button(
        "🎲 Farklı çözüm", key=f"dreroll_{g}_{m}",
        help="Aynı kurallarla eş değerde başka bir dağılım üretir.",
    ):
        result = _solve(ctx, reroll=True, avoid=mapping)
        if result.ok:
            st.session_state[_pkey(ctx)] = result.assignments
            _bump_gen(g, m)
            st.rerun(scope="fragment")
        else:
            _show_infeasible(result)
    c3.button(
        "🗑️ Taslağı sil", key=f"ddiscard_{g}_{m}",
        on_click=_cb_discard_draft, args=(g, m),
    )


def _saved_view(ctx) -> None:
    g, m = ctx["group"], ctx["month"]
    edit = st.toggle(
        "✏️ Elle düzenle", key=f"edit_{g}_{m}",
        help="Kayıtlı atamayı hücre hücre değiştirin; kaydedince güncellenir.",
    )
    if edit:
        mapping = _editor(ctx, dict(ctx["existing"]))
        violations = _check_proposal(ctx, mapping)
        show_violations_scoped(violations, {m}, ctx["group_ids"])
        blocking = blocking_errors(violations, {m}, ctx["group_ids"])
        force = False
        if blocking:
            force = st.checkbox(
                "İhlallere rağmen kaydetmek istiyorum", key=f"force_{g}_{m}"
            )
        c1, c2 = st.columns(2)
        if c1.button(
            "💾 Değişiklikleri kaydet", type="primary",
            disabled=bool(blocking) and not force, key=f"esave_{g}_{m}",
        ):
            _save(ctx, mapping)
            st.rerun(scope="app")
        c2.button(
            "❌ Vazgeç", key=f"ecancel_{g}_{m}",
            on_click=_cb_cancel_edit, args=(g, m),
        )
        return
    st.dataframe(
        _proposal_df(ctx, ctx["existing"]),
        width="stretch",
        hide_index=True,
    )
    show_violations_scoped(
        _check_proposal(ctx, ctx["existing"]), {m}, ctx["group_ids"]
    )
    if st.button(
        "🔄 Yeniden oluştur (yeni taslak)", key=f"regen_{g}_{m}",
        help="Mevcut kayıt bozulmaz; yeni öneri taslak olarak gelir, "
        "siz kaydedince yerine geçer.",
    ):
        result = _solve(ctx, reroll=True, avoid=dict(ctx["existing"]))
        if result.ok:
            st.session_state[_pkey(ctx)] = result.assignments
            _bump_gen(g, m)
            st.rerun(scope="fragment")
        else:
            _show_infeasible(result)


# ---------- sihirbaz ----------

def _wizard(ctx) -> None:
    """Adım adım üretim: tekli birimler → kısıtlı birimler → otomatik kalan.

    Sonuç kaydedilmez; 'Taslağa aktar' ile ana akıştaki taslağa düşer.
    """
    g, m = ctx["group"], ctx["month"]
    wkey = f"wizard_{g}_{m}"
    state = st.session_state[wkey]
    units_by_id = {u.id: u for u in ctx["units"]}
    active_units = [u for u in ctx["units"] if u.active and u.quota > 0]

    top1, top2 = st.columns([4, 1])
    top1.markdown(f"🧭 **Sihirbaz — {m}** (bitince sonuç taslağa aktarılır)")
    top2.button(
        "❌ Kapat", key=f"{wkey}_close",
        on_click=_cb_close_wizard, args=(g, m),
    )

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

        c1, c2 = st.columns(2)
        if c1.button("İleri ➡️", type="primary", key=f"{wkey}_next"):
            state["step"] += 1
            st.rerun(scope="fragment")
        if state["step"] > 1 and c2.button("⬅️ Geri", key=f"{wkey}_back"):
            st.session_state.pop(f"{wkey}_suggest_{state['step']}", None)
            state["step"] -= 1
            st.rerun(scope="fragment")
        return

    # Adım 3: kalanları otomatik dağıt, sonucu taslağa aktar
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
        width="stretch",
        hide_index=True,
    )
    show_violations_scoped(
        _check_proposal(ctx, result.assignments), {m}, ctx["group_ids"]
    )
    c1, c2 = st.columns(2)
    if c1.button("📝 Taslağa aktar", type="primary", key=f"{wkey}_finish"):
        st.session_state[_pkey(ctx)] = result.assignments
        _bump_gen(g, m)
        # adım 3'te seçim widget'ları kurulu değildir; temizlik güvenli
        for k in list(st.session_state):
            if isinstance(k, str) and k.startswith(wkey):
                del st.session_state[k]
        st.rerun(scope="fragment")
    if c2.button("⬅️ Geri", key=f"{wkey}_back_final"):
        state["step"] = 2
        st.rerun(scope="fragment")


# ---------- toplu oluşturma ----------

# ---- arka plan toplu iş kaydı ----
# Streamlit her etkileşimde script'i baştan koşar ve sayfa değişiminde
# koşan script'i keser: uzun süren toplu çözüm ana akışta yapılırsa sayfa
# değiştiren kullanıcı emeği kaybeder. Çözüm işi daemon thread'e taşımak:
# modül düzeyindeki bu kayıt yeniden koşularda yaşar, iş sayfadan bağımsız
# sürer; thread HİÇBİR st.* çağrısı yapmaz, sonucu diske (kalıcı taslak)
# yazar. Anahtar: sezon klasörü yolu (sezon değişse de karışmaz).
_BULK_JOBS: dict[str, dict] = {}


def _job_key(store) -> str:
    return str(store.data_dir)


def _draft_to_payload(draft: dict, fingerprint: str) -> dict:
    return {
        "fingerprint": fingerprint,
        "new": [a.to_dict() for a in draft["new"]],
        "solved": {str(g): ms for g, ms in draft["solved"].items()},
        "failed": {
            str(g): [m, reasons] for g, (m, reasons) in draft["failed"].items()
        },
    }


def _payload_to_draft(payload: dict) -> dict:
    return {
        "new": [Assignment.from_dict(d) for d in payload.get("new", [])],
        "solved": {int(g): ms for g, ms in payload.get("solved", {}).items()},
        "failed": {
            int(g): (v[0], list(v[1]))
            for g, v in payload.get("failed", {}).items()
        },
    }


def _bulk_fingerprint(bctx) -> str:
    return data_fingerprint(
        bctx["students"], bctx["units"], bctx["assignments"],
        bctx["custom_rules"], [bctx["settings"]],
    )


def _run_bulk_job(job: dict, bctx, picks, fingerprint: str) -> None:
    """Arka plan iş parçacığı: çözer, taslağı DİSKE yazar. st.* çağrısı yok."""
    try:
        def on_group(g, phase):
            job["progress"] = (
                f"Grup {g}: aylar çözülüyor…"
                if phase == "cozum"
                else f"Grup {g}: emniyet ağı — bütün sezon tek modelde…"
            )

        def on_month(g, m, attempt=1):
            extra = f" ({attempt}. deneme)" if attempt > 1 else ""
            job["progress"] = f"Grup {g} — {m}{extra}"

        new, solved, failed = plan_season(
            bctx["students"],
            bctx["units"],
            bctx["settings"]["months"],
            bctx["assignments"],
            settings=bctx["settings"],
            custom_rules=bctx["custom_rules"],
            groups=picks,
            on_group=on_group,
            on_month=on_month,
        )
        bctx["store"].save_bulk_draft(
            _draft_to_payload(
                {"new": new, "solved": solved, "failed": failed}, fingerprint
            )
        )
    except Exception as exc:  # kullanıcıya gösterilir, sessiz yutulmaz
        job["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        job["done"] = True


@st.fragment(run_every=2.0)
def _bulk_job_watch(key: str) -> None:
    """Süren işi 2 sn'de bir yoklar; bitince tam sayfayı tazeler."""
    job = _BULK_JOBS.get(key)
    if job is None or job.get("done"):
        st.rerun(scope="app")
        return
    st.info(
        "🔄 Toplu çözüm **arka planda** sürüyor — şu an: "
        f"{job.get('progress', 'başlıyor…')}\n\n"
        "Başka sayfalara geçebilir, hatta uygulamayı kapatıp açabilirsiniz; "
        "biten taslak kaybolmaz."
    )


def _cb_discard_bulk(store) -> None:
    st.session_state.pop("bulk_draft", None)
    store.clear_bulk_draft()


def _load_persisted_draft(bctx) -> dict | None:
    """Diskteki kalıcı taslağı yükler; veri değiştiyse bayattır, atılır."""
    payload = bctx["store"].load_bulk_draft()
    if payload is None:
        return None
    if payload.get("fingerprint") != _bulk_fingerprint(bctx):
        bctx["store"].clear_bulk_draft()
        return None
    return _payload_to_draft(payload)


@st.fragment
def _bulk_section(bctx) -> None:
    st.subheader("📅 Toplu oluşturma")
    if report := st.session_state.pop("_bulk_report", None):
        (st.warning if report["failed"] else st.success)(report["text"])

    key = _job_key(bctx["store"])
    job = _BULK_JOBS.get(key)
    if job is not None:
        if not job.get("done"):
            _bulk_job_watch(key)
            return
        _BULK_JOBS.pop(key, None)
        if job.get("error"):
            st.error(f"Toplu çözüm başarısız oldu: {job['error']}")

    draft = st.session_state.get("bulk_draft")
    if draft is None and (draft := _load_persisted_draft(bctx)) is not None:
        st.session_state["bulk_draft"] = draft
    if draft is not None:
        _bulk_preview(bctx, draft)
        return
    st.caption(
        "Kalan ayları tek seferde üretir. Bir ay diğerini çıkmaza sokarsa "
        "**bütün sezonu tek modelde birlikte** çözen emniyet ağı devreye "
        "girer: geçerli bir sezon varsa bulunması garanti edilir, yoksa "
        "nedeni net söylenir. Sonuç önce **taslak** gösterilir, siz "
        "onaylamadan hiçbir şey kaydedilmez. Sezon ortasından da çalışır: "
        "dolu aylar geçmiş kabul edilir."
    )
    students = bctx["students"]
    settings = bctx["settings"]
    months = settings["months"]
    groups = groups_in(students)
    remaining = {
        g: remaining_months(
            months, bctx["assignments"], {s.id for s in students if s.group == g}
        )
        for g in groups
    }
    todo = {g: ms for g, ms in remaining.items() if ms}
    if not todo:
        st.success("🎉 Tüm gruplar için sezonun bütün ayları oluşturulmuş.")
        return
    for g, ms in todo.items():
        st.caption(f"**{g}. grup** için kalan {len(ms)} ay: {', '.join(ms)}")
    picks = st.multiselect(
        "Hangi gruplar için?",
        list(todo),
        default=list(todo),
        format_func=lambda g: f"{g}. Grup",
        key="bulk_groups",
    )
    total = sum(len(todo[g]) for g in picks)
    st.caption(
        "🛈 Çözüm **arka planda** çalışır: bu sırada başka sayfalara "
        "geçebilirsiniz, biten taslak onaylayana kadar diskte saklanır."
    )
    if st.button(
        f"🚀 Kalan {total} ayı tek seferde oluştur",
        type="primary",
        disabled=not picks,
        key="bulk_run",
    ):
        job = {"done": False, "progress": "başlıyor…"}
        _BULK_JOBS[key] = job
        threading.Thread(
            target=_run_bulk_job,
            args=(job, bctx, list(picks), _bulk_fingerprint(bctx)),
            daemon=True,
        ).start()
        st.rerun(scope="fragment")


def _bulk_preview(bctx, draft: dict) -> None:
    """Toplu çözüm taslağı: incele → onayla ve kaydet / vazgeç."""
    new, solved, failed = draft["new"], draft["solved"], draft["failed"]
    settings = bctx["settings"]
    months = settings["months"]
    for g, (m, reasons) in failed.items():
        st.error(
            f"Grup {g} — {m} ayında durdu: "
            + (reasons[0] if reasons else "neden bilinmiyor")
            + " Önceki aylar taslakta korunur."
        )
    if not new:
        st.warning("Hiçbir ay çözülemedi; kaydedilecek bir şey yok.")
        st.button(
            "↩️ Kapat", key="bulk_discard",
            on_click=_cb_discard_bulk, args=(bctx["store"],),
        )
        return

    parts = [
        f"Grup {g}: {', '.join(ms)}" for g, ms in solved.items() if ms
    ]
    st.markdown(
        f"🟡 **Toplu taslak — henüz kaydedilmedi** ({'; '.join(parts)})"
    )
    students_by_id = {s.id: s for s in bctx["students"]}
    units_by_id = {u.id: u for u in bctx["units"]}
    order = {m: i for i, m in enumerate(months)}
    for g, ms in solved.items():
        if not ms:
            continue
        ms = sorted(ms, key=lambda m: order.get(m, 99))
        g_students = sorted(
            (s for s in bctx["students"] if s.group == g),
            key=lambda s: s.full_name,
        )
        cell = {
            (a.student_id, a.month): unit_label(units_by_id[a.unit_id])
            for a in new
            if a.unit_id in units_by_id
            and students_by_id.get(a.student_id, None) is not None
            and students_by_id[a.student_id].group == g
        }
        with st.expander(
            f"👀 Grup {g} önizleme ({len(ms)} ay)", expanded=len(solved) == 1
        ):
            st.dataframe(
                pd.DataFrame(
                    [
                        {"Öğrenci": s.full_name}
                        | {m: cell.get((s.id, m), "—") for m in ms}
                        for s in g_students
                    ]
                ),
                width="stretch",
                hide_index=True,
            )

    violations = check_all(
        bctx["students"],
        bctx["units"],
        bctx["assignments"] + new,
        months,
        custom_rules=bctx["custom_rules"],
        settings=settings,
    )
    show_violations_scoped(
        violations,
        {a.month for a in new},
        {a.student_id for a in new},
    )
    errors = [v for v in violations if v.severity == "hata"]
    force = False
    if errors:
        force = st.checkbox(
            "İhlallere rağmen kaydetmek istiyorum", key="bulk_force"
        )
    c1, c2 = st.columns(2)
    if c1.button(
        "✅ Onayla ve Kaydet",
        type="primary",
        disabled=bool(errors) and not force,
        key="bulk_save",
    ):
        store = bctx["store"]
        store.save_assignments(store.load_assignments() + new)
        st.session_state.pop("bulk_draft", None)
        store.clear_bulk_draft()
        report = [
            f"Grup {g}: {len(ms)} ay kaydedildi ✅"
            for g, ms in solved.items()
            if ms
        ]
        for g, (m, reasons) in failed.items():
            report.append(
                f"Grup {g}: {m} ayında durmuştu — "
                + (reasons[0] if reasons else "neden bilinmiyor")
            )
        st.session_state["_bulk_report"] = {
            "failed": bool(failed),
            "text": " • ".join(report),
        }
        st.rerun(scope="app")
    c2.button(
        "🗑️ Taslağı sil", key="bulk_discard",
        on_click=_cb_discard_bulk, args=(bctx["store"],),
    )
