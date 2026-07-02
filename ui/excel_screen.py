"""Excel İçe/Dışa Aktarım ekranı."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from rotasyon.excel_io import (
    export_single_month_workbook,
    export_yearly_workbook,
    read_rotation_workbook,
)
from rotasyon.importer import build_dataset


def render(store) -> None:
    st.header("📊 Excel İçe/Dışa Aktarım")
    tab_import, tab_export = st.tabs(["📥 İçe Aktar", "📤 Dışa Aktar"])
    with tab_import:
        _import_tab(store)
    with tab_export:
        _export_tab(store)


def _import_tab(store) -> None:
    st.caption(
        "Mevcut formatınızdaki (ARDA_ROTASYON.xlsx benzeri) dosyayı yükleyin. "
        "Sınıf renkleri, cinsiyet kısıtları (kırmızı k/e), kontenjanlar ve "
        "atama geçmişi otomatik çözümlenir."
    )
    file = st.file_uploader("Excel dosyası seçin", type=["xlsx"])
    if file is None:
        return

    try:
        result = read_rotation_workbook(file)
        ds = build_dataset(result)
    except Exception as exc:  # bozuk dosya kullanıcıya anlaşılır raporlanır
        st.error(f"Dosya okunamadı: {exc}")
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
            "Bu hücreler kontenjan listesindeki birimlerle birebir eşleşmedi. "
            "Aşağıdaki adlarla PASİF birim olarak eklenirler; içe aktardıktan "
            "sonra Veri Yönetimi ekranından düzenleyebilirsiniz."
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
    st.error(
        "İçe aktarma mevcut TÜM veriyi (öğrenci, birim, sınıf, atama) bu "
        "dosyadakiyle DEĞİŞTİRİR. Eski verinin yedeği `data/*.json.bak` "
        "dosyalarında tutulur."
    )
    confirm = st.checkbox("Anladım, mevcut verinin değiştirilmesini onaylıyorum")
    if st.button("📥 İçe Aktar", type="primary", disabled=not confirm):
        store.save_students(ds.students)
        store.save_units(ds.units)
        store.save_classes(ds.classes)
        store.save_assignments(ds.assignments)
        st.success(
            f"{len(ds.students)} öğrenci, {len(ds.units)} birim ve "
            f"{len(ds.assignments)} atama içe aktarıldı. ✅"
        )
        st.balloons()


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
        data=export_yearly_workbook(students, units, classes, assignments, months),
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
