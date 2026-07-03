"""Excel İçe/Dışa Aktarım ekranı.

İçe aktarım dosya türünü kendisi algılar:
- Rotasyon dosyası (ay sütunlu yıllık tablo) → tam veri aktarımı
- Öğrenci listesi (sezon başı, 'SML ÖĞRENCİ LİSTESİ' benzeri) → yeni sezon
  başlatma / öğrenci aktarımı
"""
from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from rotasyon.excel_io import (
    detect_workbook_kind,
    export_single_month_workbook,
    export_yearly_workbook,
    read_rotation_workbook,
    read_student_list_workbook,
)
from rotasyon.gender_guess import fill_missing_genders, guess_gender
from rotasyon.importer import build_dataset, build_roster_dataset
from rotasyon.models import GENDER_LABELS, PROGRAM_LABELS
from .common import create_season_with_units, get_manager, unit_source_options


def render(store) -> None:
    st.header("📊 Excel İçe/Dışa Aktarım")
    tab_import, tab_export = st.tabs(["📥 İçe Aktar", "📤 Dışa Aktar"])
    with tab_import:
        _import_tab(store)
    with tab_export:
        _export_tab(store)


# ======================= İÇE AKTARIM =======================

def _import_tab(store) -> None:
    st.caption(
        "İki tür dosya desteklenir ve tür otomatik algılanır: **rotasyon "
        "dosyası** (aylık sütunlu yıllık tablo) ve **öğrenci listesi** "
        "(sezon başında gelen 'SML ÖĞRENCİ LİSTESİ' benzeri)."
    )
    file = st.file_uploader("Excel dosyası seçin", type=["xlsx"])
    if file is None:
        return

    data = file.read()  # openpyxl her okuma için taze akış ister

    try:
        kind = detect_workbook_kind(BytesIO(data))
    except Exception as exc:
        st.error(f"Dosya okunamadı: {exc}")
        return

    if kind == "rotation":
        _rotation_import_flow(store, data)
    elif kind == "student_list":
        roster_import_flow(data)
    else:
        st.error(
            "Dosya türü anlaşılamadı: ne ay sütunlu bir rotasyon tablosu ne de "
            "ADI SOYADI / SINIF sütunlu bir öğrenci listesi bulundu."
        )


def _rotation_import_flow(store, data: bytes) -> None:
    st.subheader("Rotasyon dosyası algılandı")
    try:
        result = read_rotation_workbook(BytesIO(data))
        ds = build_dataset(result)
    except Exception as exc:
        st.error(f"Dosya çözümlenemedi: {exc}")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Öğrenci", len(ds.students))
    c2.metric("Birim", len(ds.units))
    c3.metric("Sınıf", len(ds.classes))
    c4.metric("Atama", len(ds.assignments))

    for w in ds.warnings:
        st.warning(w)

    if ds.unresolved:
        st.subheader("Tam eşleşmeyen birim adları")
        st.caption(
            "Bu hücreler kontenjan listesindeki birimlerle birebir eşleşmedi; "
            "PASİF birim olarak eklenir, sonra Veri Yönetimi'nden düzeltilebilir."
        )
        st.dataframe(
            pd.DataFrame(
                ds.unresolved,
                columns=["Öğrenci", "Ay", "Dosyadaki değer", "Eklenecek birim"],
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    active = get_manager().active_season()
    st.error(
        f"İçe aktarma **{active}** sezonundaki TÜM veriyi (öğrenci, birim, "
        "sınıf, atama) bu dosyadakiyle DEĞİŞTİRİR. Eski verinin yedeği "
        "`.json.bak` dosyalarında tutulur."
    )
    confirm = st.checkbox("Anladım, mevcut verinin değiştirilmesini onaylıyorum")
    if st.button("📥 İçe Aktar", type="primary", disabled=not confirm):
        # dosyadan çıkarılamayan cinsiyetler isimden tahminle tamamlanır
        filled, remaining = fill_missing_genders(ds.students)
        store.save_students(ds.students)
        store.save_units(ds.units)
        store.save_classes(ds.classes)
        store.save_assignments(ds.assignments)
        if result.day_labels:
            settings = store.load_settings()
            settings["day_labels"] = {
                str(g): label for g, label in result.day_labels.items()
            }
            store.save_settings(settings)
        st.success(
            f"{len(ds.students)} öğrenci, {len(ds.units)} birim ve "
            f"{len(ds.assignments)} atama '{active}' sezonuna aktarıldı. "
            f"{len(filled)} öğrencinin cinsiyeti isimden dolduruldu"
            + (
                f"; {len(remaining)} öğrenci Veri Yönetimi ekranında "
                "onayınızı bekliyor. ✅"
                if remaining
                else ". ✅"
            )
        )
        st.balloons()


def roster_import_flow(data: bytes) -> None:
    st.subheader("Öğrenci listesi algılandı (sezon başı)")
    try:
        roster, warns = read_student_list_workbook(BytesIO(data))
        ds = build_roster_dataset(roster)
    except Exception as exc:
        st.error(f"Dosya çözümlenemedi: {exc}")
        return
    for w in warns + ds.warnings:
        st.warning(w)
    if not ds.students:
        return

    students_by_id = {s.id: s for s in ds.students}
    guesses = {s.id: guess_gender(s.full_name) for s in ds.students}
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Ad Soyad": s.full_name,
                    "Sınıf": s.class_name,
                    "Bölüm": PROGRAM_LABELS.get(s.program, s.program),
                    "Okul No": s.student_no,
                    "Önerilen Grup": f"{s.group}. grup",
                    "Cinsiyet (tahmin)": GENDER_LABELS.get(
                        guesses[s.id].gender, "?"
                    ),
                    "Kesinlik": guesses[s.id].percent,
                }
                for s in students_by_id.values()
            ]
        ),
        use_container_width=True,
        hide_index=True,
        height=320,
    )
    sure = sum(1 for g in guesses.values() if g.gender and g.confidence >= 0.8)
    st.caption(
        f"🔮 Cinsiyet, listede olmadığı için isimden tahmin edilir: "
        f"{sure} öğrenci yüksek kesinlikle (≥%80) otomatik doldurulacak, "
        f"kalan {len(ds.students) - sure} öğrenci içe aktarımdan sonra "
        "Veri Yönetimi ekranında onayınızı bekleyecek."
    )

    st.divider()
    manager = get_manager()
    seasons = manager.list_seasons()
    active = manager.active_season()

    target = st.radio(
        "Nereye aktarılsın?",
        ["Yeni sezon oluştur", f"Aktif sezona aktar ({active})"],
        help="Sezon başı listesi genelde yeni bir dönemin başlangıcıdır.",
    )
    if target == "Yeni sezon oluştur":
        season_name = st.text_input("Yeni sezon adı", value="", placeholder="örn. 2025-2026")
        source = st.selectbox(
            "Birimler nereden gelsin?",
            unit_source_options(seasons),
            index=max(len(seasons) - 1, 0),  # varsayılan: en son sezon
            help="Birimler genelde sezondan sezona aynı kalır; önceki sezondan "
            "kopyalamak en hızlısıdır. Hiç sezon yoksa varsayılan katalog "
            "hazır bir başlangıç sunar. Öğrenci ve atamalar kopyalanmaz.",
        )
        if st.button(
            "🚀 Sezonu oluştur ve öğrencileri aktar",
            type="primary",
            disabled=not season_name.strip(),
        ):
            try:
                new_store = create_season_with_units(
                    manager, season_name.strip(), source
                )
            except ValueError as exc:
                st.error(str(exc))
                return
            filled, remaining = fill_missing_genders(ds.students)
            new_store.save_students(ds.students)
            # sınıflar: kopyalanan sezondan gelenler varsa öğrenci listesindekilerle birleştir
            existing = {c.name for c in new_store.load_classes()}
            merged = new_store.load_classes() + [
                c for c in ds.classes if c.name not in existing
            ]
            new_store.save_classes(merged)
            st.success(
                f"'{season_name.strip()}' sezonu oluşturuldu, "
                f"{len(ds.students)} öğrenci aktarıldı. {len(filled)} "
                "öğrencinin cinsiyeti isimden dolduruldu"
                + (
                    f"; {len(remaining)} öğrenci için Veri Yönetimi "
                    "ekranında onayınız gerekiyor."
                    if remaining
                    else "."
                )
                + " Grupları kontrol edin, sonra Rotasyon Oluştur "
                "ekranından ilk ayı planlayabilirsiniz. ✅"
            )
            st.balloons()
    else:
        st.error(
            f"Bu işlem **{active}** sezonundaki öğrenci ve sınıf listesini "
            "değiştirir, o sezonun TÜM atamalarını siler. Birimler korunur."
        )
        confirm = st.checkbox("Anladım, onaylıyorum")
        if st.button("📥 Aktif sezona aktar", type="primary", disabled=not confirm):
            store = manager.store()
            filled, remaining = fill_missing_genders(ds.students)
            store.save_students(ds.students)
            existing = {c.name for c in store.load_classes()}
            store.save_classes(
                store.load_classes()
                + [c for c in ds.classes if c.name not in existing]
            )
            store.save_assignments([])
            st.success(
                f"{len(ds.students)} öğrenci '{active}' sezonuna aktarıldı; "
                f"{len(filled)} öğrencinin cinsiyeti isimden dolduruldu. "
                + (
                    f"Kalan {len(remaining)} öğrenciyi Veri Yönetimi "
                    "ekranından tamamlayın. ✅"
                    if remaining
                    else "✅"
                )
            )


# ======================= DIŞA AKTARIM =======================

def _export_tab(store) -> None:
    students = store.load_students()
    units = store.load_units()
    classes = store.load_classes()
    assignments = store.load_assignments()
    settings = store.load_settings()
    months = settings["months"]

    if not students:
        st.info("Dışa aktarılacak veri yok.")
        return

    st.subheader("Yıllık grup görünümü (renkli)")
    st.caption(
        "Her grup ayrı sayfada; öğrenci adları sınıf renginde (madde 14), "
        "cinsiyet kısıtlı birimler kırmızı k/e ekli."
    )
    st.download_button(
        "📤 Yıllık görünümü indir",
        data=export_yearly_workbook(
            students, units, classes, assignments, months,
            settings.get("day_labels"),
        ),
        file_name="rotasyon_yillik.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )

    st.divider()
    st.subheader("Tek ay görünümü (renksiz)")
    st.caption("Gruplar yan yana, sade tablo (madde 15).")
    months_with_data = [
        m for m in months if any(a.month == m for a in assignments)
    ]
    if not months_with_data:
        st.info("Henüz atama yapılmış ay yok.")
        return
    month = st.selectbox("Ay seçin", months_with_data)
    st.download_button(
        f"📤 {month} görünümünü indir",
        data=export_single_month_workbook(
            students, units, assignments, month, settings.get("day_labels")
        ),
        file_name=f"rotasyon_{month}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
