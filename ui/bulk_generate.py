"""Toplu oluşturma — kalan bütün ayları tek seferde üretir.

Yıllık Tablo'nun altında yaşar: tablonun tamamını dolduran bir işlem oraya
aittir. (Önceden ayrı bir "Rotasyon Oluştur" ekranındaydı; o ekranın tek-ay
akışı Yıllık Tablo'nun hücre düzenlemesiyle örtüştüğü için kaldırıldı.)

Çözüm ARKA PLAN thread'inde koşar ve sonucu diske yazar: Streamlit her
etkileşimde script'i baştan koşar ve sayfa değişiminde koşan script'i keser,
dolayısıyla uzun süren çözüm ana akışta yapılırsa sayfa değiştiren kullanıcı
emeği kaybeder. Thread HİÇBİR st.* çağrısı yapmaz.
"""
from __future__ import annotations

import threading

import pandas as pd
import streamlit as st

from rotasyon.models import Assignment
from rotasyon.planner import plan_season, remaining_months
from rotasyon.rules import check_all
from .common import (
    data_fingerprint,
    group_label,
    groups_in,
    show_violations_scoped,
    unit_label,
)


def render(store, students, units, settings, custom_rules, assignments,
           requirements=None) -> None:
    """Yıllık Tablo'nun altındaki toplu üretim bölümü."""
    _bulk_section(
        dict(
            store=store,
            students=[s for s in students if s.active],
            units=units,
            settings=settings,
            custom_rules=custom_rules,
            assignments=assignments,
            requirements=requirements,
        )
    )


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
    # Gereksinimler de parmak izine girer: kullanıcı bir zorunluluk
    # ekleyip/çıkardığında diskteki taslak artık o kurallara göre üretilmiş
    # değildir, bayat sayılmalı.
    return data_fingerprint(
        bctx["students"], bctx["units"], bctx["assignments"],
        bctx["custom_rules"], [bctx["settings"]],
        bctx.get("requirements") or [],
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
            requirements=bctx.get("requirements"),
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
        st.caption(
            f"**{group_label(students, g, settings)}** için kalan "
            f"{len(ms)} ay: {', '.join(ms)}"
        )
    picks = st.multiselect(
        "Hangi gruplar için?",
        list(todo),
        default=list(todo),
        format_func=lambda g: group_label(students, g, settings),
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
        requirements=bctx.get("requirements"),
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
