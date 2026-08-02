"""Veri Yönetimi — sezondan sezona TAŞINAN bilgilerin merkezi.

Beş sekme: Öğrenciler, Birimler, Sınıflar, Ayarlar (çözücü) ve Yedekleme.

**Kapsam sınırı — kimlik / rol ayrımı:** burada birimin KALICI KİMLİĞİ
düzenlenir (ad, grup, cinsiyet kısıtı, bölüm türü, yoğunluk). Birimin O
SEZONKİ ROLÜ — kontenjanı, doldurma politikası, bu sezon açık olup olmadığı —
**Kapasite Planı** ekranındadır. Sezon zorunlulukları **Gereksinimler**,
tekil istisnalar (ayrı/birlikte tut, birim yasağı, sabit atama) **Özel
Kurallar** ekranındadır. Üçü de bir zamanlar buradaydı; aynı veriyi iki
ekranda düzenletmek çelişkili kombinasyonlara yol açıyordu (tabloda bir
birim hem "Havuz" hem "Yedek" işaretlenebiliyordu).

Toplu düzenlemeler st.data_editor ile yapılır: 70 öğrencinin cinsiyetini
tek tek form açmadan, tabloda hücre hücre girmek mümkündür.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from rotasyon.models import (
    BRANCH_CATEGORIES,
    BRANCH_LABELS,
    ClassGroup,
    GENDER_LABELS,
    INTENSITIES,
    INTENSITY_LABELS,
    PROGRAM_LABELS,
    PROGRAMS,
    Student,
    Unit,
)
from rotasyon.normalize import normalize_unit_name
from .common import data_fingerprint, gender_label, unit_label

# Boş dize seçeneği Streamlit'te "None" diye görünüyordu; iki bağlamda da
# ne demek olduğunu açıkça yazıyoruz. Öğrencide boş = cinsiyet HENÜZ
# BİLİNMİYOR, birimde boş = cinsiyet KISITI YOK — aynı widget, farklı anlam.
_GENDER_OPTIONS = ["Kısıt yok", "Kız", "Erkek"]
_GENDER_OPTIONS_STUDENT = ["Bilinmiyor", "Kız", "Erkek"]
_GENDER_TO_CODE = {
    "Kısıt yok": "", "Bilinmiyor": "", "": "",
    "Kız": "K", "Erkek": "E",
}
_BRANCH_TO_CODE = {v: k for k, v in BRANCH_LABELS.items()}
_PROGRAM_TO_CODE = {v: k for k, v in PROGRAM_LABELS.items()}
_GROUP_OPTIONS = ["1. grup", "2. grup", "Her ikisi"]
_GROUP_TO_CODE = {"1. grup": 1, "2. grup": 2, "Her ikisi": 0}
_CODE_TO_GROUP = {v: k for k, v in _GROUP_TO_CODE.items()}
_INTENSITY_TO_CODE = {v: k for k, v in INTENSITY_LABELS.items()}


def render(store) -> None:
    st.header("📋 Veri Yönetimi")
    tabs = st.tabs(
        ["👤 Öğrenciler", "🏥 Birimler", "🎨 Sınıflar",
         "⚙️ Ayarlar", "💾 Yedekleme"]
    )
    with tabs[0]:
        _students_tab(store)
    with tabs[1]:
        _units_tab(store)
    with tabs[2]:
        _classes_tab(store)
    with tabs[3]:
        _settings_tab(store)
    with tabs[4]:
        _backup_tab(store)


# ======================= ÖĞRENCİLER =======================

def _students_tab(store) -> None:
    students = store.load_students()
    units = store.load_units()
    classes = store.load_classes()
    class_names = [c.name for c in classes]

    col_imp, col_new = st.columns(2)
    with col_imp, st.expander("📥 Excel listesinden içe aktar", expanded=not students):
        st.caption(
            "Sezon başı öğrenci listesini (SML xlsx, kodlu 'A-HY' xlsx ya da "
            "e-okul Sınıf Listesi PDF'i) buradan da yükleyebilirsiniz; "
            "tür otomatik algılanır."
        )
        file = st.file_uploader(
            "Öğrenci listesi (.xlsx veya .pdf)",
            type=["xlsx", "pdf"],
            key="dm_roster_upload",
        )
        if file is not None:
            from .excel_screen import _pdf_roster_flow, _xlsx_roster_flow

            if file.name.lower().endswith(".pdf"):
                _pdf_roster_flow(file.read())
            else:
                _xlsx_roster_flow(file.read())
    with col_new, st.expander("➕ Yeni öğrenci ekle"):
        _new_student_form(store, students, class_names)

    if not students:
        st.info("Henüz öğrenci yok. Excel'den içe aktarın veya elle ekleyin.")
        return

    missing = [s for s in students if not s.gender]
    if missing:
        st.warning(
            f"⚠️ {len(missing)} öğrencinin cinsiyeti eksik — rotasyon için "
            "gerekli. İsimden tahminle doldurabilir veya alttaki tabloda "
            "elle girebilirsiniz."
        )
        _gender_guess_panel(store, students, missing)

    st.caption(
        "Hücrelere tıklayarak doğrudan düzenleyin, sonra **Kaydet**'e basın. "
        "Yasaklı birimler ve silme işlemi alttaki bölümde."
    )
    ordered = sorted(students, key=lambda s: (s.group, s.class_name, s.full_name))
    df = pd.DataFrame(
        [
            {
                "Ad Soyad": s.full_name,
                "Okul No": s.student_no,
                "Cinsiyet": gender_label(s.gender) if s.gender else "Bilinmiyor",
                "Grup": s.group,
                "Sınıf": s.class_name,
                "Bölüm": PROGRAM_LABELS.get(s.program, s.program),
                "Diş Muaf": s.dis_exempt,
                "Aktif": s.active,
                "Not": s.note,
            }
            for s in ordered
        ]
    )
    edited = st.data_editor(
        df,
        column_config={
            "Ad Soyad": st.column_config.TextColumn(required=True),
            "Okul No": st.column_config.TextColumn(width="small"),
            "Cinsiyet": st.column_config.SelectboxColumn(
                options=_GENDER_OPTIONS_STUDENT, width="small"
            ),
            "Grup": st.column_config.SelectboxColumn(
                options=[1, 2], width="small"
            ),
            "Sınıf": st.column_config.SelectboxColumn(options=class_names),
            "Bölüm": st.column_config.SelectboxColumn(
                options=list(PROGRAM_LABELS.values())
            ),
            "Diş Muaf": st.column_config.CheckboxColumn(
                help="Madde 9: bu öğrenci Diş Poliklinik'e verilmez"
            ),
            "Aktif": st.column_config.CheckboxColumn(
                help="Sezon ortasında ayrılan öğrencinin işaretini kaldırın: "
                "geçmiş ayları korunur, yeni aylara atanmaz. Silmekten "
                "farklıdır — silme geçmişi de bozar."
            ),
            "Not": st.column_config.TextColumn(
                help="Madde 10: özel durum notu"
            ),
        },
        num_rows="fixed",
        width="stretch",
        hide_index=True,
        height=420,
        # anahtar veri içeriğine bağlı: veri başka yerde değişirse düzenleyici
        # sıfırlanır ve güncel hali gösterir (bayat hücre kalmaz)
        key=f"students_editor_{data_fingerprint(ordered)}",
    )
    degisti = not edited.equals(df)
    if st.button(
        "💾 Tablodaki değişiklikleri kaydet", type="primary",
        key="save_students", disabled=not degisti,
    ):
        for s, (_, row) in zip(ordered, edited.iterrows()):
            s.full_name = str(row["Ad Soyad"]).strip() or s.full_name
            s.student_no = str(row["Okul No"] or "").strip()
            s.gender = _GENDER_TO_CODE.get(row["Cinsiyet"] or "Bilinmiyor", "")
            s.group = int(row["Grup"])
            s.class_name = row["Sınıf"] or s.class_name
            s.program = _PROGRAM_TO_CODE.get(row["Bölüm"], s.program)
            s.dis_exempt = bool(row["Diş Muaf"])
            s.active = bool(row["Aktif"])
            s.note = str(row["Not"] or "").strip()
        store.save_students(students)
        st.success("Öğrenciler kaydedildi. ✅")
        st.rerun()

    with st.expander("🔧 Yasaklı birimler / öğrenci silme"):
        options = {
            f"{s.full_name} ({s.group}. grup)": s
            for s in sorted(students, key=lambda s: (s.group, s.full_name))
        }
        pick = st.selectbox("Öğrenci seç", list(options), key="student_detail_pick")
        s = options[pick]
        group_units = [u for u in units if u.active and u.group in (0, s.group)]
        banned = st.multiselect(
            "Yasaklı birimler (madde 8) — bu öğrenci bu birimlere asla atanmaz",
            [u.id for u in group_units],
            default=[
                uid for uid in s.banned_unit_ids
                if any(u.id == uid for u in group_units)
            ],
            format_func=lambda uid: unit_label(
                next(u for u in group_units if u.id == uid)
            ),
            key=f"banned_{s.id}",
        )
        # yalnız bu gruptaki birimler seçilebiliyor; kıyas da o küme üzerinden
        mevcut = [
            uid for uid in s.banned_unit_ids
            if any(u.id == uid for u in group_units)
        ]
        c1, c2 = st.columns(2)
        if c1.button(
            "💾 Yasakları kaydet", key=f"save_banned_{s.id}",
            disabled=set(banned) == set(mevcut),
        ):
            # başka gruba ait eski yasaklar korunur, yalnız bu grubunkiler güncellenir
            digerleri = [uid for uid in s.banned_unit_ids if uid not in mevcut]
            s.banned_unit_ids = digerleri + banned
            store.save_students(students)
            st.success("Kaydedildi. ✅")
        with c2:
            _delete_student_flow(store, students, s)


def _delete_student_flow(store, students, s) -> None:
    """Öğrenci silme — atamaları ve kural üyelikleri de birlikte gider.

    Sahipsiz atama bırakılmaz: bırakılırsa Kural Kontrolü kalıcı bir
    "silinmiş öğrenciye işaret ediyor" hatası gösterir ve teknik olmayan
    kullanıcının bunu temizleyecek aracı yoktur. Yanlışlıkla tek tıkla
    geçmiş silinmesin diye ataması olan öğrencide onay kutusu istenir.
    """
    from rotasyon.maintenance import remove_student

    assignments = store.load_assignments()
    n_assign = sum(1 for a in assignments if a.student_id == s.id)
    if n_assign:
        st.caption(
            f"⚠️ {s.full_name} adına {n_assign} aylık atama geçmişi var. "
            "Sezon ortasında AYRILAN öğrenci için doğrusu tabloda 'Aktif' "
            "işaretini kaldırmaktır (geçmiş korunur). Silme; öğrenciyi, "
            "atamalarını ve özel kural üyeliklerini birlikte kaldırır."
        )
        sure = st.checkbox(
            f"{n_assign} atamasıyla birlikte silmek istiyorum",
            key=f"del_student_sure_{s.id}",
        )
    else:
        sure = True
    if st.button(
        "🗑️ Öğrenciyi sil", key=f"del_student_{s.id}", disabled=not sure
    ):
        result = remove_student(
            students, assignments, store.load_custom_rules(), s.id
        )
        store.save_students(result.students)
        store.save_assignments(result.assignments)
        store.save_custom_rules(result.rules)
        bits = [f"{s.full_name} silindi"]
        if result.removed_assignments:
            bits.append(f"{result.removed_assignments} atama kaldırıldı")
        if result.removed_rules:
            bits.append(f"{result.removed_rules} özel kural kaldırıldı")
        st.toast(" — ".join(bits) + " ✅", icon="🗑️")
        st.rerun()


def _gender_guess_panel(store, students, missing) -> None:
    """Eksik cinsiyetler için isimden tahmin + tek tıkla uygulama.

    Kesinliği eşiğin (%80) altında kalanlar otomatik doldurulmaz;
    kullanıcının ana tablodan elle girmesi beklenir.
    """
    from rotasyon.gender_guess import AUTO_FILL_CONFIDENCE, guess_gender

    with st.expander("🔮 İsimden cinsiyet tahmini", expanded=True):
        rows, applicable = [], 0
        for s in sorted(missing, key=lambda s: s.full_name):
            g = guess_gender(s.full_name)
            ok = bool(g.gender) and g.confidence >= AUTO_FILL_CONFIDENCE
            applicable += ok
            rows.append(
                {
                    "Öğrenci": s.full_name,
                    "Tahmin": GENDER_LABELS.get(g.gender, "—"),
                    "Kesinlik": g.percent,
                    "Otomatik": "✅" if ok else "✏️ elle girin",
                }
            )
        st.dataframe(
            pd.DataFrame(rows),
            width="stretch",
            hide_index=True,
            height=min(38 * (len(rows) + 1), 300),
        )
        if applicable and st.button(
            f"🔮 {applicable} tahmini uygula (kesinlik ≥ "
            f"%{round(AUTO_FILL_CONFIDENCE * 100)})",
            type="primary",
            key="apply_gender_guesses",
        ):
            from rotasyon.gender_guess import fill_missing_genders

            fill_missing_genders(students)
            store.save_students(students)
            st.rerun()


def _new_student_form(store, students, class_names) -> None:
    from rotasyon.models import GENDERS

    with st.form("new_student", clear_on_submit=True):
        name = st.text_input("Ad Soyad")
        student_no = st.text_input("Okul / föy no")
        gender = st.selectbox("Cinsiyet", GENDERS, format_func=GENDER_LABELS.get)
        group = st.selectbox("Grup", [1, 2])
        class_name = st.selectbox("Sınıf", class_names or [""])
        program = st.selectbox(
            "Bölüm Türü", PROGRAMS, format_func=PROGRAM_LABELS.get
        )
        if st.form_submit_button("Ekle") and name.strip():
            students.append(
                Student(
                    full_name=name.strip(),
                    gender=gender,
                    group=group,
                    class_name=class_name,
                    program=program,
                    student_no=student_no.strip(),
                )
            )
            store.save_students(students)
            st.rerun()


# ======================= BİRİMLER =======================

def _units_tab(store) -> None:
    units = store.load_units()

    with st.expander("➕ Yeni birim ekle", expanded=not units):
        _new_unit_form(store, units)

    if not units:
        _empty_units_panel(store)
        return

    # Burada birimin KALICI KİMLİĞİ düzenlenir: adı, hangi grupta olduğu,
    # kimi kabul ettiği, ne tür bir bölüm olduğu. O SEZONKİ ROLÜ (kaç kişi
    # alacak, nasıl doldurulacak, bu sezon açık mı) Kapasite Planı'nda
    # ayarlanır — aynı veriyi iki ekranda düzenletmek, kullanıcının
    # çelişkili kombinasyon kurmasına ve iki farklı zihinsel modele yol
    # açıyordu (örn. tabloda hem "Havuz" hem "Yedek" işaretlenebiliyordu).
    st.caption(
        "Birimin **kalıcı bilgileri**: ad, grup, cinsiyet kısıtı, bölüm türü. "
        "Kontenjan, doldurma politikası ve bu sezon açık olup olmadığı "
        "**Kapasite Planı** ekranındadır."
    )
    _link_capacity()
    ordered = sorted(units, key=lambda u: (u.group, not u.active, u.name))
    df = pd.DataFrame(
        [
            {
                "Birim": u.name,
                "Grup": _CODE_TO_GROUP.get(u.group, "1. grup"),
                "Cinsiyet": gender_label(u.gender_restriction)
                if u.gender_restriction else "Kısıt yok",
                "Branş": BRANCH_LABELS.get(u.branch_category, "Diğer"),
                "Yoğunluk": INTENSITY_LABELS.get(u.intensity, "—"),
                "Ebelik Önc.": u.ebelik_priority,
            }
            for u in ordered
        ]
    )
    edited = st.data_editor(
        df,
        column_config={
            "Birim": st.column_config.TextColumn(required=True),
            "Grup": st.column_config.SelectboxColumn(options=_GROUP_OPTIONS, width="small"),
            "Cinsiyet": st.column_config.SelectboxColumn(
                options=_GENDER_OPTIONS, width="small",
                help="Madde 2/3: yalnız bu cinsiyetten öğrenci atanır",
            ),
            "Branş": st.column_config.SelectboxColumn(
                options=list(BRANCH_LABELS.values()),
                help="Bölümün türü. Gereksinim kurarken birimleri hızlı "
                "seçmek için kullanılır (kendi başına bir kural değildir).",
            ),
            "Yoğunluk": st.column_config.SelectboxColumn(
                options=list(INTENSITY_LABELS.values()), width="small",
                help="Peş peşe iki ay yoğun (veya hafif) bölüme öğrenci verilmez",
            ),
            "Ebelik Önc.": st.column_config.CheckboxColumn(
                help="Madde 18: ebelik öğrencisi öncelikli"
            ),
        },
        num_rows="fixed",
        width="stretch",
        hide_index=True,
        height=420,
        # anahtar veri içeriğine bağlı: dışarıdan değişiklikte sıfırlanır
        key=f"units_editor_{data_fingerprint(ordered)}",
    )
    if st.button(
        "💾 Tablodaki değişiklikleri kaydet", type="primary",
        key="save_units", disabled=edited.equals(df),
    ):
        for u, (_, row) in zip(ordered, edited.iterrows()):
            u.name = normalize_unit_name(str(row["Birim"])) or u.name
            u.group = _GROUP_TO_CODE.get(row["Grup"], u.group)
            u.gender_restriction = _GENDER_TO_CODE.get(
                row["Cinsiyet"] or "Kısıt yok", ""
            )
            u.branch_category = _BRANCH_TO_CODE.get(row["Branş"], u.branch_category)
            u.intensity = _INTENSITY_TO_CODE.get(row["Yoğunluk"] or "—", u.intensity)
            u.ebelik_priority = bool(row["Ebelik Önc."])
            # kontenjan / politika / aktiflik burada DEĞİŞTİRİLMEZ
            # (Kapasite Planı'nın alanı) — dokunulmadan korunur
        store.save_units(units)
        st.success("Birimler kaydedildi. ✅")
        st.rerun()

    with st.expander("🗑️ Birim silme"):
        options = {
            f"{unit_label(u)} ({_CODE_TO_GROUP.get(u.group)})"
            + ("" if u.active else " [pasif]"): u
            for u in ordered
        }
        pick = st.selectbox("Birim seç", list(options), key="unit_del_pick")
        u = options[pick]
        if st.button("🗑️ Sil", key=f"del_unit_{u.id}"):
            assignments = store.load_assignments()
            if any(a.unit_id == u.id for a in assignments):
                st.error(
                    "Bu birime ait atama geçmişi var; silmek yerine tabloda "
                    "'Aktif' işaretini kaldırın (geçmiş korunur)."
                )
            else:
                store.save_units([x for x in units if x.id != u.id])
                st.rerun()


def _empty_units_panel(store) -> None:
    """Birim listesi boşken hızlı doldurma seçenekleri sunar."""
    from rotasyon.catalog import catalog_available, load_default_units
    from .common import get_manager

    st.info(
        "Bu sezonda henüz birim yok. Tek tek eklemek yerine hazır bir "
        "listeyle başlayabilirsiniz:"
    )
    c1, c2 = st.columns(2)
    with c1:
        if catalog_available():
            catalog = load_default_units()
            st.markdown("**📦 Varsayılan birim kataloğu**")
            st.caption(
                f"{len(catalog)} birim (kat servisleri, yoğun bakımlar, "
                "poliklinikler...) kontenjan ve kısıtlarıyla yüklenir; "
                "sonra bu tablodan serbestçe düzenlersiniz."
            )
            if st.button("Kataloğu yükle", type="primary", key="load_catalog"):
                store.save_units(catalog)
                st.rerun()
    with c2:
        manager = get_manager()
        others = [
            s for s in manager.list_seasons() if s != manager.active_season()
        ]
        if others:
            st.markdown("**📅 Başka sezondan kopyala**")
            pick = st.selectbox(
                "Sezon", others, index=len(others) - 1, key="copy_units_season"
            )
            if st.button("Birimleri kopyala", key="copy_units_btn"):
                source = manager.store(pick)
                store.save_units(source.load_units())
                st.rerun()


def _new_unit_form(store, units) -> None:
    with st.form("new_unit", clear_on_submit=True):
        name = st.text_input("Birim adı")
        c1, c2 = st.columns(2)
        group = c1.selectbox(
            "Grup", [1, 2, 0],
            format_func=lambda g: _CODE_TO_GROUP[g],
        )
        quota = c2.number_input("Aylık kontenjan", 1, 50, 1)
        c3, c4 = st.columns(2)
        gender = c3.selectbox(
            "Cinsiyet kısıtı", _GENDER_OPTIONS,
        )
        branch = c4.selectbox(
            "Branş kategorisi", BRANCH_CATEGORIES, format_func=BRANCH_LABELS.get
        )
        intensity = st.selectbox(
            "Yoğunluk", INTENSITIES, format_func=INTENSITY_LABELS.get,
            help="Peş peşe iki ay yoğun (veya hafif) bölüme öğrenci verilmez",
        )
        ebelik = st.checkbox("Ebelik öncelikli (madde 18)")
        st.caption(
            "Yeni birim **havuz** politikasıyla eklenir (kalanlar eşit "
            "dağılır). Doldurma politikasını ve kontenjanı sonra Kapasite "
            "Planı'ndan ayarlarsınız."
        )
        if st.form_submit_button("Ekle") and name.strip():
            units.append(
                Unit(
                    name=normalize_unit_name(name),
                    group=group,
                    quota=int(quota),
                    gender_restriction=_GENDER_TO_CODE.get(gender, ""),
                    branch_category=branch,
                    intensity=intensity,
                    pool=True,  # makul varsayılan; Kapasite Planı'ndan değişir
                    ebelik_priority=ebelik,
                )
            )
            store.save_units(units)
            st.rerun()


def _link_capacity() -> None:
    """Kapasite Planı'na hızlı geçiş (kontenjan/politika oraya taşındı)."""
    pages = st.session_state.get("_pages", {})
    if "kapasite-plani" in pages:
        st.page_link(
            pages["kapasite-plani"],
            label="Kontenjan ve doldurma politikası için Kapasite Planı'na git",
            icon="📦",
        )


# ======================= SINIFLAR =======================

def _classes_tab(store) -> None:
    classes = store.load_classes()
    _class_group_panel(store, classes)
    st.divider()
    st.subheader("🎨 Sınıflar ve renkleri")
    st.caption(
        "Sınıf sayısı ve adları serbesttir (madde 13); renk, yıllık Excel "
        "görünümünde öğrenci adını vurgular (madde 14)."
    )
    for c in classes:
        col1, col2, col3 = st.columns([3, 1, 1])
        col1.markdown(
            f"<span style='background:{c.color_hex or '#eee'};color:#111;"
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
        name = c1.text_input("Sınıf adı", placeholder="örn. 11/A")
        color = c2.color_picker("Renk", "#FFFF00")
        if c3.form_submit_button("Ekle") and name.strip():
            if any(c.name == name.strip() for c in classes):
                st.error("Bu adla bir sınıf zaten var.")
            else:
                classes.append(ClassGroup(name=name.strip(), color_hex=color))
                store.save_classes(classes)
                st.rerun()


def _class_group_panel(store, classes) -> None:
    """Sınıf → grup eşleştirmesini sonradan değiştirme.

    Eşleştirme öğrenci içe aktarımında bir kez soruluyordu; sezon başında
    ya da ortasında değişebildiği için (şube birleşmesi, grup dengesi)
    kalıcı bir yerden de yapılabilmeli. Öğrencinin grubu tek tek Öğrenciler
    tablosundan da değiştirilebilir; buradaki panel ŞUBE BAZINDA topluca
    yapar — asıl ihtiyaç budur.
    """
    students = store.load_students()
    st.subheader("🔀 Sınıf → grup eşleştirmesi")
    if not students:
        st.info(
            "Henüz öğrenci yok. Öğrencileri içe aktardıktan sonra şube-grup "
            "eşleştirmesini buradan istediğiniz zaman değiştirebilirsiniz."
        )
        return

    st.caption(
        "Rotasyonlar grup grup üretilir. Bir şubenin hangi gruba ait "
        "olduğunu buradan topluca değiştirebilirsiniz — içe aktarımda "
        "yaptığınız seçim kalıcı değildir."
    )

    from rotasyon.maintenance import (
        apply_class_group,
        class_group_state,
        students_changed_by,
    )

    states = class_group_state(students, [c.name for c in classes])
    if not states:
        st.info("Öğrencilerde sınıf bilgisi yok.")
        return

    def _durum(st_: "object") -> str:
        if not st_.groups:
            return "— (öğrencisi yok)"
        if not st_.is_mixed:
            return f"{st_.groups[0]}. Grup"
        parts = ", ".join(
            f"{g}. grupta {sum(1 for s in students if s.class_name == st_.name and s.group == g)}"
            for g in st_.groups
        )
        return f"⚠️ karışık: {parts}"

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Şube": s.name,
                    "Öğrenci": s.student_count,
                    "Şu anki grup": _durum(s),
                }
                for s in states
            ]
        ),
        width="stretch",
        hide_index=True,
    )

    picks = {}
    cols = st.columns(min(len(states), 4) or 1)
    for i, s in enumerate(states):
        picks[s.name] = cols[i % len(cols)].selectbox(
            f"{s.name} şubesi",
            [1, 2],
            index=s.suggested - 1,
            format_func=lambda g: f"{g}. Grup",
            key=f"cg_pick_{s.name}",
        )

    changed = students_changed_by(students, picks)
    counts = {g: sum(1 for v in picks.values() if v == g) for g in (1, 2)}
    if 0 in counts.values():
        st.warning(
            "⚠️ Bir grupta hiç şube kalmıyor. Genelde her iki gruba da şube "
            "atanır; yine de uygulayabilirsiniz."
        )
    if not changed:
        st.caption("Değişiklik yok — seçimler mevcut durumla aynı.")
        return

    st.info(f"↔️ Bu değişiklik **{len(changed)} öğrencinin** grubunu değiştirir.")
    assignments = store.load_assignments()
    touched = {a.student_id for a in assignments} & {s.id for s in changed}
    if touched:
        st.warning(
            f"⚠️ Bu öğrencilerden **{len(touched)} tanesinin kayıtlı ataması "
            "var**. Birimler gruba özel olduğu için, geçmiş aylar Kural "
            "Kontrolü'nde artık uyumsuz görünebilir. Geçmiş atamalar "
            "kendiliğinden değişmez ve silinmez; grup değişikliği asıl "
            "olarak BUNDAN SONRA üretilecek ayları etkiler."
        )
    if st.button("🔀 Eşleştirmeyi uygula", type="primary", key="apply_class_group"):
        updated, n = apply_class_group(students, picks)
        store.save_students(updated)
        st.toast(f"{n} öğrencinin grubu güncellendi ✅", icon="🔀")
        st.rerun()


# ======================= YEDEKLEME =======================

def _backup_tab(store) -> None:
    """Tek düğmeyle yedek indirme / yedekten geri yükleme.

    Kullanıcı `data/` klasörünü ne bulur ne kopyalar; yedek almanın da
    geri yüklemenin de dosya sistemine dokunmadan yapılabilmesi gerekir.
    Geri yükleme ASLA üzerine yazmaz: yedek her zaman YENİ sezon açar.
    """
    from rotasyon.backup import (
        BackupError,
        backup_filename,
        full_backup_bytes,
        inspect_backup,
        restore_into,
    )
    from .common import DATA_DIR, get_manager

    manager = get_manager()
    seasons = manager.list_seasons()
    active = manager.active_season()

    st.subheader("💾 Yedek al")
    st.caption(
        "Yedek dosyasını bilgisayarınıza indirir. Ayda bir yedek alıp "
        "e-postanıza ya da bir USB belleğe kopyalamanız önerilir — "
        "bilgisayar değişse bile veriniz kaybolmaz."
    )
    col_one, col_all = st.columns(2)
    with col_one:
        try:
            data = _season_backup(store, active or "sezon")
        except BackupError as exc:
            st.info(str(exc))
        else:
            st.download_button(
                f"📥 Bu sezonu indir ({active})",
                data=data,
                file_name=backup_filename(active),
                mime="application/zip",
                type="primary",
                width="stretch",
            )
    with col_all:
        st.download_button(
            f"📦 Tüm sezonları indir ({len(seasons)} sezon)",
            data=full_backup_bytes(DATA_DIR, seasons),
            file_name=backup_filename(None),
            mime="application/zip",
            disabled=not seasons,
            width="stretch",
        )

    st.divider()
    st.subheader("♻️ Yedekten geri yükle")
    st.caption(
        "Yedek dosyasındaki veriler **yeni bir sezon** olarak açılır; "
        "şu anki sezonlarınızın hiçbiri değişmez veya silinmez."
    )
    upload = st.file_uploader(
        "Yedek dosyası (.zip)", type=["zip"], key="backup_restore_upload"
    )
    if upload is None:
        return
    payload = upload.getvalue()
    try:
        info = inspect_backup(payload)
    except BackupError as exc:
        st.error(str(exc))
        return

    st.success(
        f"Yedek okundu — {len(info['sezonlar'])} sezon"
        + (f", tarih: {info['tarih'][:16].replace('T', ' ')}" if info["tarih"] else "")
    )
    for season in info["sezonlar"]:
        counts = season["kayit"]
        st.markdown(
            f"- **{season['ad']}** — "
            f"{counts.get('students', 0)} öğrenci, "
            f"{counts.get('units', 0)} birim, "
            f"{counts.get('assignments', 0)} atama"
        )
    single = len(info["sezonlar"]) == 1
    new_name = ""
    if single:
        new_name = st.text_input(
            "Yeni sezonun adı",
            value=info["sezonlar"][0]["ad"],
            help="Aynı adlı bir sezon varsa sonuna (2) eklenir.",
            key="backup_restore_name",
        )
    if st.button("♻️ Geri yükle", type="primary", key="backup_restore_go"):
        try:
            created = restore_into(
                payload, DATA_DIR, seasons, rename_to=new_name if single else None
            )
        except BackupError as exc:
            st.error(str(exc))
            return
        if created:
            manager.set_active(created[0])
        st.toast(f"Geri yüklendi: {', '.join(created)} ✅", icon="♻️")
        st.rerun()


def _season_backup(store, season_name: str) -> bytes:
    from rotasyon.backup import season_backup_bytes

    return season_backup_bytes(store.data_dir, season_name)


# ======================= AYARLAR =======================

_WEIGHT_LABELS = {
    # anahtar: (etiket, açıklama) — models.DEFAULT_SETTINGS["solver"]["weights"]
    "pool_balance": (
        "Havuz birimlerine eşit dağılım",
        "Madde 4: kalan öğrenciler havuz birimlerine olabildiğince eşit dağılır.",
    ),
    "repeat_pair": (
        "Tekrar eden ikili cezası",
        "Madde 19: iki öğrencinin farklı aylarda tekrar aynı birime düşmesi "
        "cezalandırılır (yüksek = daha az tekrar eden ikili).",
    ),
    "ebelik_priority": (
        "Ebelik önceliği",
        "Madde 18: ebelik öğrencileri, ebelik öncelikli birimlere önce yerleşir.",
    ),
    "core_branch_early": (
        "Zorunlu branşları erken karşılama",
        "Sezon zorunluluklarının (cerrahi/dahili/YB/palyatif) erken aylarda "
        "görülmesine küçük bir bonus verilir.",
    ),
    "single_slot_fill": (
        "Tekli birimler boş kalmasın",
        "Madde 4: kontenjanı 1 olan birimlerin doldurulması güçlü teşvik edilir.",
    ),
    "reserve_use": (
        "Yedek birimden kaçınma",
        "Gri/yedek birimlere yalnız gerçekten gerekiyorsa öğrenci verilir "
        "(yüksek = daha güçlü kaçınma).",
    ),
    "gender_balance": (
        "Kız/erkek dengesi",
        "Havuz birimlerinde cinsiyet dağılımının dengeli olması teşvik edilir.",
    ),
    "intensive_surplus": (
        "Fazlalık yoğun birime",
        "Eşit dağılımda tam bölünmeyen fazlalık öğrenciler yoğun etiketli "
        "birimlere yönlendirilir. Eşit dağılımdan DÜŞÜK kalmalıdır ki dengeyi "
        "bozmasın, yalnız eşit çözümler arasında tercih yapsın.",
    ),
}


def _settings_tab(store) -> None:
    """Sezon zorunlulukları + çözücü ayarları — JSON'a girmeden düzenleme.

    Çözücü ve denetleyici ayarları HER koşuda yeniden okur; buradaki bir
    değişiklik bir sonraki üretimden/denetimden itibaren geçerlidir, geçmiş
    kayıtlı aylar kendiliğinden değişmez.
    """
    from rotasyon.models import DEFAULT_SETTINGS

    settings = store.load_settings()

    _requirements_notice(store, settings)

    st.subheader("⏱️ Ne kadar beklensin?")
    solver = settings.get("solver", {})
    time_limit, season_limit = _patience_picker(solver)

    st.divider()
    st.subheader("🧮 İnce ayar (ağırlıklar)")
    st.caption(
        "Varsayılanlar gerçek sezon verisiyle ölçülüp seçildi; genelde "
        "dokunmak gerekmez. Ağırlık = kuralın çözüm seçiminde ne kadar söz "
        "sahibi olduğu (yalnız birbirine GÖRE anlamlıdır)."
    )

    weights = dict(solver.get("weights", {}))
    new_weights = {}
    cols = st.columns(2)
    for i, (key, (label, help_text)) in enumerate(_WEIGHT_LABELS.items()):
        default = DEFAULT_SETTINGS["solver"]["weights"].get(key, 0)
        new_weights[key] = cols[i % 2].number_input(
            label,
            min_value=0, max_value=100,
            value=int(weights.get(key, default)),
            help=help_text + f" (Varsayılan: {default})",
            key=f"set_w_{key}",
        )
    # bilinmeyen/eski anahtarlar korunur (ileri sürüm geriye uyum)
    for key, val in weights.items():
        new_weights.setdefault(key, val)

    if new_weights.get("intensive_surplus", 0) >= new_weights.get("pool_balance", 1):
        st.warning(
            "⚠️ 'Fazlalık yoğun birime' ağırlığı, 'eşit dağılım'dan küçük "
            "olmalıdır; aksi halde çözücü eşit dağılımı bozup öğrencileri "
            "yoğun birimlere yığabilir."
        )

    # Kaydedilecek bir değişiklik var mı? (süreler + ağırlıklar)
    degisti = (
        int(time_limit) != int(solver.get("time_limit_seconds",
                       DEFAULT_SETTINGS["solver"]["time_limit_seconds"]))
        or int(season_limit) != int(solver.get("season_time_limit_seconds",
                       DEFAULT_SETTINGS["solver"]["season_time_limit_seconds"]))
        or {k: int(v) for k, v in new_weights.items()}
        != {k: int(v) for k, v in weights.items()}
    )

    c_save, c_reset = st.columns(2)
    if c_save.button(
        "💾 Ayarları kaydet", type="primary", key="save_settings_tab",
        disabled=not degisti,
    ):
        settings.setdefault("solver", {})
        settings["solver"]["time_limit_seconds"] = int(time_limit)
        settings["solver"]["season_time_limit_seconds"] = int(season_limit)
        settings["solver"]["weights"] = {k: int(v) for k, v in new_weights.items()}
        store.save_settings(settings)
        st.toast("Ayarlar kaydedildi ✅", icon="⚙️")
        st.rerun()
    if c_reset.button("↩️ Varsayılanlara dön", key="reset_settings_tab"):
        # yalnız çözücü ayarları sıfırlanır; sezon zorunlulukları artık
        # Gereksinimler ekranının alanı, buradan silinmemeli
        settings["solver"] = json_copy(DEFAULT_SETTINGS["solver"])
        store.save_settings(settings)
        st.toast("Çözücü ayarları varsayılanlara döndü ✅", icon="↩️")
        st.rerun()


# (ay, sezon) saniye çiftleri. Kademeli deneme sayesinde bunlar bir ÜST SINIR
# değil BAŞLANGIÇ: süre yetmezse çözücü kendiliğinden 2× ve 4× deneyecek.
# O yüzden "Dengeli" çoğu makinede yeterli — "Sabırlı" yalnız bekleme
# süresini baştan uzatır.
_SABIR_SECENEKLERI = {
    "⚡ Hızlı": (3, 30),
    "⚖️ Dengeli": (8, 90),
    "🐢 Sabırlı": (20, 240),
}
_SABIR_ACIKLAMA = {
    "⚡ Hızlı": "Çabuk sonuç. Hızlı bir bilgisayarda ve rahat sezonlarda iyi.",
    "⚖️ Dengeli": "Önerilen. Eski/yavaş bilgisayarlarda da yeterli olacak "
                  "şekilde seçildi.",
    "🐢 Sabırlı": "Zor sezonlar için. Daha uzun bekler, sonuç bulma şansı "
                 "en yüksek.",
}


def clamp(value: int, low: int, high: int) -> int:
    """Kayıtlı bir sayıyı widget'ın kabul ettiği aralığa çeker.

    st.number_input, `value` min/max dışındaysa İSTİSNA fırlatır; st.tabs tüm
    panelleri çalıştırdığı için tek bozuk sayı Veri Yönetimi ekranının
    TAMAMINI (öğrenciler, birimler, yedekleme dahil) erişilemez yapar — yani
    kullanıcı o sayıyı düzeltmek için de oraya giremez.
    """
    return min(high, max(low, int(value)))


def _patience_picker(solver: dict) -> tuple[int, int]:
    """Saniye kutuları yerine üç hazır seçim.

    "Aylık çözüm süresi (saniye)" gibi bir alan teknik bilgi ister: kullanıcı
    ne kadar yazacağını bilemez. Üç hazır kademe + gerekirse açılan sayısal
    ayar. Dönüş: (aylık saniye, sezon saniye).
    """
    from rotasyon.models import DEFAULT_SETTINGS

    varsayilan = DEFAULT_SETTINGS["solver"]
    mevcut = (
        int(solver.get("time_limit_seconds",
                       varsayilan["time_limit_seconds"])),
        int(solver.get("season_time_limit_seconds",
                       varsayilan["season_time_limit_seconds"])),
    )
    eslesen = next(
        (ad for ad, v in _SABIR_SECENEKLERI.items() if v == mevcut), None
    )
    secenekler = list(_SABIR_SECENEKLERI)
    if eslesen is None:
        secenekler = secenekler + ["✏️ Kendi ayarım"]
    secim = st.radio(
        "Çözücü ne kadar uğraşsın?",
        secenekler,
        index=secenekler.index(eslesen or "✏️ Kendi ayarım"),
        horizontal=True,
        key="set_patience",
        label_visibility="collapsed",
    )
    st.caption(
        _SABIR_ACIKLAMA.get(
            secim,
            "Sayıları kendiniz belirlediniz; hazır kademelerden birine "
            "dönmek için yukarıdan seçin.",
        )
    )
    st.caption(
        "🛈 Süre yetmezse uygulama **kendiliğinden daha uzun deniyor** "
        "(2 ve 4 katı). Yani bu seçim bir üst sınır değil, başlangıç."
    )
    if secim in _SABIR_SECENEKLERI:
        return _SABIR_SECENEKLERI[secim]

    with st.expander("Sayısal ayar", expanded=True):
        c1, c2 = st.columns(2)
        ay = c1.number_input(
            "Tek ay için başlangıç (saniye)", min_value=1, max_value=120,
            value=clamp(mevcut[0], 1, 120), key="set_time_limit",
        )
        sezon = c2.number_input(
            "Tüm sezon için başlangıç (saniye)", min_value=10, max_value=600,
            value=clamp(mevcut[1], 10, 600), key="set_season_limit",
        )
    return int(ay), int(sezon)


def _requirements_notice(store, settings) -> None:
    """Sezon zorunluluklarının artık NEREDE olduğunu ve hangisinin GEÇERLİ
    olduğunu söyler.

    Branş multiselect'i buradan kaldırıldı: "birime branş ata → o branşı
    zorunlu tut" dolayımı kullanıcının şikâyet ettiği workaround'un ta
    kendisiydi. Yerine Gereksinimler ekranı geçti. Eski alan veride duruyor
    (gereksinim tanımlanmamış sezonlar için geriye uyum) ama düzenlenmiyor.
    """
    from rotasyon.requirements import active_requirements

    st.subheader("🎓 Sezon zorunlulukları")
    reqs = active_requirements(store)
    if reqs:
        st.success(
            f"Bu sezonda **{len(reqs)} gereksinim** tanımlı ve üretimde "
            "bunlar geçerli."
        )
    else:
        eski = [
            BRANCH_LABELS.get(r.get("branch"), r.get("branch"))
            for r in settings.get("season_requirements", [])
            if r.get("branch")
        ]
        st.info(
            "Bu sezonda gereksinim tanımlı değil; **eski branş yolu** "
            "çalışıyor"
            + (f" (zorunlu branşlar: {', '.join(eski)})." if eski else ".")
            + " Gereksinimler ekranından tek tıkla aktarabilirsiniz."
        )
    pages = st.session_state.get("_pages", {})
    if "gereksinimler" in pages:
        st.page_link(
            pages["gereksinimler"],
            label="Gereksinimler ekranını aç", icon="🎯",
        )
    st.divider()


def json_copy(obj):
    import json

    return json.loads(json.dumps(obj))
