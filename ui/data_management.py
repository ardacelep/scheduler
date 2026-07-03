"""Veri Yönetimi ekranı: öğrenci / birim / sınıf CRUD."""
from __future__ import annotations

import streamlit as st

from rotasyon.models import (
    BRANCH_CATEGORIES,
    BRANCH_LABELS,
    ClassGroup,
    GENDERS,
    GENDER_LABELS,
    PROGRAMS,
    PROGRAM_LABELS,
    Student,
    Unit,
)
from .common import gender_label, unit_label


def render(store) -> None:
    st.header("📋 Veri Yönetimi")
    tab_students, tab_units, tab_classes = st.tabs(
        ["Öğrenciler", "Birimler", "Sınıflar"]
    )
    with tab_students:
        _students_tab(store)
    with tab_units:
        _units_tab(store)
    with tab_classes:
        _classes_tab(store)


# ---------- Öğrenciler ----------

def _students_tab(store) -> None:
    students = store.load_students()
    units = store.load_units()
    classes = store.load_classes()
    class_names = [c.name for c in classes]

    if students:
        import pandas as pd

        unit_names = {u.id: unit_label(u) for u in units}
        df = pd.DataFrame(
            [
                {
                    "Ad Soyad": s.full_name,
                    "Okul No": s.student_no,
                    "Cinsiyet": gender_label(s.gender),
                    "Grup": s.group,
                    "Sınıf": s.class_name,
                    "Bölüm": PROGRAM_LABELS.get(s.program, s.program),
                    "Diş Muaf": "✓" if s.dis_exempt else "",
                    "Yasaklı Birimler": ", ".join(
                        unit_names.get(uid, "?") for uid in s.banned_unit_ids
                    ),
                    "Not": s.note,
                }
                for s in sorted(students, key=lambda s: (s.group, s.full_name))
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True, height=350)
        missing = [s.full_name for s in students if not s.gender]
        if missing:
            st.warning(
                "Cinsiyeti girilmemiş öğrenciler var (kurallar için gerekli): "
                + ", ".join(missing)
            )
    else:
        st.info("Henüz öğrenci yok. Aşağıdan ekleyin veya Excel'den içe aktarın.")

    st.divider()
    col_new, col_edit = st.columns(2)

    with col_new, st.expander("➕ Yeni öğrenci ekle", expanded=not students):
        with st.form("new_student", clear_on_submit=True):
            name = st.text_input("Ad Soyad")
            student_no = st.text_input("Okul / föy no")
            gender = st.selectbox(
                "Cinsiyet", GENDERS, format_func=GENDER_LABELS.get
            )
            group = st.selectbox("Grup", [1, 2])
            class_name = st.selectbox("Sınıf", class_names or [""])
            program = st.selectbox(
                "Bölüm Türü", PROGRAMS, format_func=PROGRAM_LABELS.get
            )
            dis_exempt = st.checkbox("Diş Poliklinik muafiyeti (madde 9)")
            note = st.text_input("Özel not (madde 10)")
            if st.form_submit_button("Ekle") and name.strip():
                students.append(
                    Student(
                        full_name=name.strip(),
                        gender=gender,
                        group=group,
                        class_name=class_name,
                        program=program,
                        student_no=student_no.strip(),
                        dis_exempt=dis_exempt,
                        note=note.strip(),
                    )
                )
                store.save_students(students)
                st.rerun()

    with col_edit, st.expander("✏️ Öğrenci düzenle / sil", expanded=False):
        if not students:
            st.caption("Öğrenci yok.")
            return
        options = {
            f"{s.full_name} ({s.group}. grup)": s
            for s in sorted(students, key=lambda s: (s.group, s.full_name))
        }
        pick = st.selectbox("Öğrenci seç", list(options))
        s = options[pick]
        group_units = [u for u in units if u.active and u.group in (0, s.group)]
        with st.form(f"edit_student_{s.id}"):
            name = st.text_input("Ad Soyad", value=s.full_name)
            student_no = st.text_input("Okul / föy no", value=s.student_no)
            gender = st.selectbox(
                "Cinsiyet",
                GENDERS,
                index=GENDERS.index(s.gender) if s.gender in GENDERS else 0,
                format_func=GENDER_LABELS.get,
            )
            group = st.selectbox("Grup", [1, 2], index=s.group - 1)
            class_name = st.selectbox(
                "Sınıf",
                class_names or [""],
                index=class_names.index(s.class_name)
                if s.class_name in class_names
                else 0,
            )
            program = st.selectbox(
                "Bölüm Türü",
                PROGRAMS,
                index=PROGRAMS.index(s.program) if s.program in PROGRAMS else 0,
                format_func=PROGRAM_LABELS.get,
            )
            banned = st.multiselect(
                "Yasaklı birimler (madde 8)",
                [u.id for u in group_units],
                default=[
                    uid for uid in s.banned_unit_ids
                    if any(u.id == uid for u in group_units)
                ],
                format_func=lambda uid: unit_label(
                    next(u for u in group_units if u.id == uid)
                ),
            )
            dis_exempt = st.checkbox(
                "Diş Poliklinik muafiyeti (madde 9)", value=s.dis_exempt
            )
            note = st.text_input("Özel not (madde 10)", value=s.note)
            c1, c2 = st.columns(2)
            if c1.form_submit_button("💾 Kaydet", type="primary"):
                s.full_name = name.strip() or s.full_name
                s.student_no = student_no.strip()
                s.gender = gender
                s.group = group
                s.class_name = class_name
                s.program = program
                s.banned_unit_ids = banned
                s.dis_exempt = dis_exempt
                s.note = note.strip()
                store.save_students(students)
                st.rerun()
            if c2.form_submit_button("🗑️ Sil"):
                store.save_students([x for x in students if x.id != s.id])
                st.rerun()


# ---------- Birimler ----------

def _units_tab(store) -> None:
    units = store.load_units()

    if units:
        import pandas as pd

        df = pd.DataFrame(
            [
                {
                    "Birim": u.name,
                    "Grup": "Her ikisi" if u.group == 0 else f"{u.group}. grup",
                    "Kontenjan": u.quota,
                    "Cinsiyet": gender_label(u.gender_restriction)
                    if u.gender_restriction
                    else "-",
                    "Branş": BRANCH_LABELS.get(u.branch_category, "-"),
                    "Tekli": "✓" if u.single_slot else "",
                    "Havuz": "✓" if u.pool else "",
                    "Ebelik Önc.": "✓" if u.ebelik_priority else "",
                    "Tam Dolar": "✓" if u.must_fill else "",
                    "Aktif": "✓" if u.active else "✗",
                }
                for u in sorted(units, key=lambda u: (u.group, u.name))
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True, height=350)
    else:
        st.info("Henüz birim yok.")

    st.divider()
    col_new, col_edit = st.columns(2)
    gender_opts = ["", "K", "E"]
    gender_fmt = lambda g: "Kısıt yok" if not g else GENDER_LABELS[g]  # noqa: E731

    with col_new, st.expander("➕ Yeni birim ekle", expanded=not units):
        with st.form("new_unit", clear_on_submit=True):
            name = st.text_input("Birim adı")
            group = st.selectbox(
                "Grup", [1, 2, 0],
                format_func=lambda g: "Her ikisi" if g == 0 else f"{g}. grup",
            )
            quota = st.number_input("Aylık kontenjan", 1, 50, 1)
            gender = st.selectbox(
                "Cinsiyet kısıtı (madde 2/3)", gender_opts, format_func=gender_fmt
            )
            branch = st.selectbox(
                "Branş kategorisi (madde 6/7)",
                BRANCH_CATEGORIES,
                format_func=BRANCH_LABELS.get,
            )
            single = st.checkbox("Tekli birim — önce doldurulur (madde 4)")
            pool = st.checkbox("Havuz birimi — eşit dağıtım (madde 4)")
            ebelik = st.checkbox("Ebelik öncelikli (madde 18)")
            must_fill = st.checkbox("Kontenjan tam dolmak zorunda (madde 17)")
            if st.form_submit_button("Ekle") and name.strip():
                units.append(
                    Unit(
                        name=name.strip(),
                        group=group,
                        quota=int(quota),
                        gender_restriction=gender,
                        branch_category=branch,
                        single_slot=single,
                        pool=pool,
                        ebelik_priority=ebelik,
                        must_fill=must_fill,
                    )
                )
                store.save_units(units)
                st.rerun()

    with col_edit, st.expander("✏️ Birim düzenle / sil", expanded=False):
        if not units:
            st.caption("Birim yok.")
            return
        options = {
            f"{unit_label(u)} ({'her ikisi' if u.group == 0 else str(u.group) + '. grup'})"
            + ("" if u.active else " [pasif]"): u
            for u in sorted(units, key=lambda u: (u.group, u.name))
        }
        pick = st.selectbox("Birim seç", list(options))
        u = options[pick]
        with st.form(f"edit_unit_{u.id}"):
            name = st.text_input("Birim adı", value=u.name)
            group = st.selectbox(
                "Grup", [1, 2, 0], index=[1, 2, 0].index(u.group),
                format_func=lambda g: "Her ikisi" if g == 0 else f"{g}. grup",
            )
            quota = st.number_input("Aylık kontenjan", 0, 50, u.quota)
            gender = st.selectbox(
                "Cinsiyet kısıtı (madde 2/3)",
                gender_opts,
                index=gender_opts.index(u.gender_restriction),
                format_func=gender_fmt,
            )
            branch = st.selectbox(
                "Branş kategorisi (madde 6/7)",
                BRANCH_CATEGORIES,
                index=BRANCH_CATEGORIES.index(u.branch_category),
                format_func=BRANCH_LABELS.get,
            )
            single = st.checkbox("Tekli birim (madde 4)", value=u.single_slot)
            pool = st.checkbox("Havuz birimi (madde 4)", value=u.pool)
            ebelik = st.checkbox("Ebelik öncelikli (madde 18)", value=u.ebelik_priority)
            must_fill = st.checkbox("Tam dolmak zorunda (madde 17)", value=u.must_fill)
            active = st.checkbox("Aktif", value=u.active)
            c1, c2 = st.columns(2)
            if c1.form_submit_button("💾 Kaydet", type="primary"):
                u.name = name.strip() or u.name
                u.group = group
                u.quota = int(quota)
                u.gender_restriction = gender
                u.branch_category = branch
                u.single_slot = single
                u.pool = pool
                u.ebelik_priority = ebelik
                u.must_fill = must_fill
                u.active = active
                store.save_units(units)
                st.rerun()
            if c2.form_submit_button("🗑️ Sil"):
                assignments = store.load_assignments()
                if any(a.unit_id == u.id for a in assignments):
                    st.error(
                        "Bu birime ait atama geçmişi var; silmek yerine "
                        "'Aktif' işaretini kaldırın (geçmiş korunur)."
                    )
                else:
                    store.save_units([x for x in units if x.id != u.id])
                    st.rerun()


# ---------- Sınıflar ----------

def _classes_tab(store) -> None:
    classes = store.load_classes()
    st.caption(
        "Sınıf sayısı ve adları serbesttir (madde 13); rengi yıllık görünümde "
        "öğrenci adını vurgular (madde 14)."
    )
    for c in classes:
        col1, col2, col3 = st.columns([3, 1, 1])
        col1.markdown(
            f"<span style='background:{c.color_hex or '#eee'};"
            f"padding:2px 12px;border-radius:4px'>{c.name}</span>",
            unsafe_allow_html=True,
        )
        new_color = col2.color_picker(
            "Renk", c.color_hex or "#FFFFFF", key=f"color_{c.id}",
            label_visibility="collapsed",
        )
        if new_color != c.color_hex:
            c.color_hex = new_color
            store.save_classes(classes)
        if col3.button("Sil", key=f"del_class_{c.id}"):
            store.save_classes([x for x in classes if x.id != c.id])
            st.rerun()

    with st.form("new_class", clear_on_submit=True):
        c1, c2, c3 = st.columns([3, 1, 1])
        name = c1.text_input("Sınıf adı", placeholder="örn. A")
        color = c2.color_picker("Renk", "#FFFF00")
        if c3.form_submit_button("Ekle") and name.strip():
            if any(c.name == name.strip() for c in classes):
                st.error("Bu adla bir sınıf zaten var.")
            else:
                classes.append(ClassGroup(name=name.strip(), color_hex=color))
                store.save_classes(classes)
                st.rerun()
