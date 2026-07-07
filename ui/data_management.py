"""Veri Yönetimi — uygulamanın esneklik merkezi.

Dört sekme: Öğrenciler (toplu düzenleme + Excel'den içe aktarma),
Birimler (toplu düzenleme + ekleme), Sınıflar, Kurallar (kullanıcı tanımlı
ayrı tut / birlikte tut / sabit atama kuralları).

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
    CustomRule,
    CUSTOM_RULE_LABELS,
    CUSTOM_RULE_TYPES,
    GENDER_LABELS,
    INTENSITIES,
    INTENSITY_LABELS,
    PROGRAM_LABELS,
    PROGRAMS,
    RULE_AYRI_TUT,
    RULE_BIRIM_YASAK,
    RULE_BIRLIKTE_TUT,
    RULE_SABIT_ATAMA,
    Student,
    Unit,
)
from rotasyon.normalize import normalize_unit_name
from .common import data_fingerprint, gender_label, unit_label

_GENDER_OPTIONS = ["", "Kız", "Erkek"]
_GENDER_TO_CODE = {"": "", "Kız": "K", "Erkek": "E"}
_BRANCH_TO_CODE = {v: k for k, v in BRANCH_LABELS.items()}
_PROGRAM_TO_CODE = {v: k for k, v in PROGRAM_LABELS.items()}
_GROUP_OPTIONS = ["1. grup", "2. grup", "Her ikisi"]
_GROUP_TO_CODE = {"1. grup": 1, "2. grup": 2, "Her ikisi": 0}
_CODE_TO_GROUP = {v: k for k, v in _GROUP_TO_CODE.items()}
_INTENSITY_TO_CODE = {v: k for k, v in INTENSITY_LABELS.items()}


def render(store) -> None:
    st.header("📋 Veri Yönetimi")
    tab_students, tab_units, tab_classes, tab_rules = st.tabs(
        ["👤 Öğrenciler", "🏥 Birimler", "🎨 Sınıflar", "📏 Kurallar"]
    )
    with tab_students:
        _students_tab(store)
    with tab_units:
        _units_tab(store)
    with tab_classes:
        _classes_tab(store)
    with tab_rules:
        _rules_tab(store)


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
                "Cinsiyet": gender_label(s.gender) if s.gender else "",
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
                options=_GENDER_OPTIONS, width="small"
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
        use_container_width=True,
        hide_index=True,
        height=420,
        # anahtar veri içeriğine bağlı: veri başka yerde değişirse düzenleyici
        # sıfırlanır ve güncel hali gösterir (bayat hücre kalmaz)
        key=f"students_editor_{data_fingerprint(ordered)}",
    )
    if st.button("💾 Tablodaki değişiklikleri kaydet", type="primary", key="save_students"):
        for s, (_, row) in zip(ordered, edited.iterrows()):
            s.full_name = str(row["Ad Soyad"]).strip() or s.full_name
            s.student_no = str(row["Okul No"] or "").strip()
            s.gender = _GENDER_TO_CODE.get(row["Cinsiyet"] or "", s.gender)
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
        c1, c2 = st.columns(2)
        if c1.button("💾 Yasakları kaydet", key=f"save_banned_{s.id}"):
            s.banned_unit_ids = banned
            store.save_students(students)
            st.success("Kaydedildi. ✅")
        if c2.button(
            "🗑️ Öğrenciyi sil", key=f"del_student_{s.id}",
            help="Silme, öğrencinin geçmiş atamalarını sahipsiz bırakır. "
            "Sezon ortasında AYRILAN öğrenci için tablodaki 'Aktif' "
            "işaretini kaldırmak doğrusudur.",
        ):
            store.save_students([x for x in students if x.id != s.id])
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
            use_container_width=True,
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

    st.caption(
        "Kontenjan, cinsiyet kısıtı, branş kategorisi ve bayraklar tabloda "
        "doğrudan düzenlenir. Pasif birimler solver'a girmez ama geçmişi korur."
    )
    ordered = sorted(units, key=lambda u: (u.group, not u.active, u.name))
    df = pd.DataFrame(
        [
            {
                "Birim": u.name,
                "Grup": _CODE_TO_GROUP.get(u.group, "1. grup"),
                "Kontenjan": u.quota,
                "Cinsiyet": gender_label(u.gender_restriction)
                if u.gender_restriction else "",
                "Branş": BRANCH_LABELS.get(u.branch_category, "Diğer"),
                "Yoğunluk": INTENSITY_LABELS.get(u.intensity, "—"),
                "Tekli": u.single_slot,
                "Havuz": u.pool,
                "Yedek": u.reserve,
                "Ebelik Önc.": u.ebelik_priority,
                "Tam Dolar": u.must_fill,
                "Aktif": u.active,
            }
            for u in ordered
        ]
    )
    edited = st.data_editor(
        df,
        column_config={
            "Birim": st.column_config.TextColumn(required=True),
            "Grup": st.column_config.SelectboxColumn(options=_GROUP_OPTIONS, width="small"),
            "Kontenjan": st.column_config.NumberColumn(
                min_value=0, max_value=50, step=1, width="small",
                help="Madde 12: aylık kaç öğrenci alır",
            ),
            "Cinsiyet": st.column_config.SelectboxColumn(
                options=_GENDER_OPTIONS, width="small",
                help="Madde 2/3: yalnız bu cinsiyetten öğrenci atanır",
            ),
            "Branş": st.column_config.SelectboxColumn(
                options=list(BRANCH_LABELS.values()),
                help="Madde 6/7: dönem sonu zorunlulukları bu kategoriye bakar",
            ),
            "Yoğunluk": st.column_config.SelectboxColumn(
                options=list(INTENSITY_LABELS.values()), width="small",
                help="Peş peşe iki ay yoğun (veya hafif) bölüme öğrenci verilmez",
            ),
            "Tekli": st.column_config.CheckboxColumn(
                help="Madde 4: önce doldurulan tekli birim"
            ),
            "Havuz": st.column_config.CheckboxColumn(
                help="Madde 4: kat/YB/FTR/acil eşit dağıtım havuzu"
            ),
            "Yedek": st.column_config.CheckboxColumn(
                help="Gri birim: yalnız ihtiyaç olursa öğrenci verilir"
            ),
            "Ebelik Önc.": st.column_config.CheckboxColumn(
                help="Madde 18: ebelik öğrencisi öncelikli"
            ),
            "Tam Dolar": st.column_config.CheckboxColumn(
                help="Madde 17: kontenjan her ay tam dolmak zorunda"
            ),
            "Aktif": st.column_config.CheckboxColumn(),
        },
        num_rows="fixed",
        use_container_width=True,
        hide_index=True,
        height=420,
        # anahtar veri içeriğine bağlı: dışarıdan değişiklikte sıfırlanır
        key=f"units_editor_{data_fingerprint(ordered)}",
    )
    if st.button("💾 Tablodaki değişiklikleri kaydet", type="primary", key="save_units"):
        for u, (_, row) in zip(ordered, edited.iterrows()):
            u.name = normalize_unit_name(str(row["Birim"])) or u.name
            u.group = _GROUP_TO_CODE.get(row["Grup"], u.group)
            u.quota = int(row["Kontenjan"])
            u.gender_restriction = _GENDER_TO_CODE.get(row["Cinsiyet"] or "", "")
            u.branch_category = _BRANCH_TO_CODE.get(row["Branş"], u.branch_category)
            u.intensity = _INTENSITY_TO_CODE.get(row["Yoğunluk"] or "—", u.intensity)
            u.single_slot = bool(row["Tekli"])
            u.pool = bool(row["Havuz"])
            u.reserve = bool(row["Yedek"])
            u.ebelik_priority = bool(row["Ebelik Önc."])
            u.must_fill = bool(row["Tam Dolar"])
            u.active = bool(row["Aktif"])
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
            format_func=lambda g: g or "Kısıt yok",
        )
        branch = c4.selectbox(
            "Branş kategorisi", BRANCH_CATEGORIES, format_func=BRANCH_LABELS.get
        )
        intensity = st.selectbox(
            "Yoğunluk", INTENSITIES, format_func=INTENSITY_LABELS.get,
            help="Peş peşe iki ay yoğun (veya hafif) bölüme öğrenci verilmez",
        )
        single = st.checkbox("Tekli birim — önce doldurulur (madde 4)")
        pool = st.checkbox("Havuz birimi — eşit dağıtım (madde 4)")
        reserve = st.checkbox("Yedek birim — yalnız ihtiyaç olursa kullanılır")
        ebelik = st.checkbox("Ebelik öncelikli (madde 18)")
        must_fill = st.checkbox("Kontenjan tam dolmak zorunda (madde 17)")
        if st.form_submit_button("Ekle") and name.strip():
            units.append(
                Unit(
                    name=normalize_unit_name(name),
                    group=group,
                    quota=int(quota),
                    gender_restriction=_GENDER_TO_CODE.get(gender, ""),
                    branch_category=branch,
                    intensity=intensity,
                    single_slot=single,
                    pool=pool,
                    reserve=reserve,
                    ebelik_priority=ebelik,
                    must_fill=must_fill,
                )
            )
            store.save_units(units)
            st.rerun()


# ======================= SINIFLAR =======================

def _classes_tab(store) -> None:
    classes = store.load_classes()
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


# ======================= KURALLAR =======================

_BUILTIN_RULES_SUMMARY = """
1. Aynı bölüme ikinci kez gidilmez • 2-3. Kırmızı **k/e** birimlere yalnız o
cinsiyet • 4. Tekli birimler önce dolar, kalanlar havuza eşit dağılır •
5. Gruplar bağımsız • 6. Sezon boyunca herkes **bir cerrahi, bir dahili,
bir yoğun bakım ve bir palyatif** görür (branş bazlı zorunluluklar) •
7. Ebelik öğrencileri doğum salonu görür • 8. Yasaklı birimler •
9. Diş muafiyeti • 10. Özel not • 11. Gün bazlı görevlendirme notu •
12. Kontenjanlar düzenlenebilir • 13-14. Sınıflar ve renkleri • 15. Tek ay
görünümü renksiz • 16. Öğrenci geçmişi • 17. FTR ve 2.KAT ÇOCUK-DOĞUM'a
1 kız 1 erkek • 18. Doğum birimlerinde ebelik önceliği • 19. Aynı ikili
tekrar aynı birimde olmaz • 20. Peş peşe iki ay **yoğun** (veya **hafif**)
bölüme verilmez • 21. Havuz birimlerinde kız/erkek dengesi gözetilir
(dengesizlik ancak takas ile düzeltilebilir olduğunda uyarı verilir;
gruptaki kız/erkek sayısı zaten dengesizse uyarı üretilmez) •
**Yedek (gri) birimlere** yalnız ihtiyaç olursa öğrenci verilir.

Bu kurallar öğrenci/birim tanımlarındaki alanlarla (cinsiyet kısıtı, branş
kategorisi, yoğunluk, yedeklik, yasaklı birimler...) beslenir ve her zaman
uygulanır.
"""


def _window_text(rule) -> str:
    """Kuralın zaman penceresini insan diline çevirir."""
    if rule.start_month and rule.end_month:
        return f" _( {rule.start_month}–{rule.end_month} ayları dahil)_"
    if rule.start_month:
        return f" _( {rule.start_month} ayından itibaren, bu ay dahil)_"
    if rule.end_month:
        return f" _( {rule.end_month} ayına kadar, bu ay dahil)_"
    return ""


def _describe_rule(rule, students_by_id, units_by_id, months) -> str:
    names = [
        students_by_id[sid].full_name
        for sid in rule.student_ids
        if sid in students_by_id
    ]
    who = ", ".join(names) if names else "(öğrenci silinmiş)"
    if rule.type == RULE_SABIT_ATAMA:
        unit = units_by_id.get(rule.unit_id)
        return (
            f"📌 **Sabit atama:** {who} → {rule.month} ayında "
            f"**{unit.name if unit else '(silinmiş birim)'}**"
        )
    if rule.type == RULE_BIRIM_YASAK:
        unit = units_by_id.get(rule.unit_id)
        return (
            f"🚫 **Birim yasağı:** {who} → "
            f"**{unit.name if unit else '(silinmiş birim)'}** birimine "
            f"gitmesin{_window_text(rule)}"
        )
    if rule.type == RULE_AYRI_TUT:
        return f"↔️ **Ayrı tut:** {who} aynı birime düşmesin{_window_text(rule)}"
    return f"🤝 **Birlikte tut:** {who} hep aynı birimde olsun{_window_text(rule)}"


def _next_unplanned_month(months, assignments) -> str:
    """Henüz hiç ataması olmayan ilk ay (zaman kapsamlı kuralların güvenli
    varsayılan başlangıcı — geçmişi bozmamak için)."""
    planned = {a.month for a in assignments}
    return next((m for m in months if m not in planned), "")


def _window_pickers(months, default_start):
    """Ortak başlangıç/bitiş ayı seçicileri; (start, end) döner.

    Seçilen aylar DAHİLDİR (başlangıç ayının kendisi ve bitiş ayının kendisi
    de kuralın geçerli olduğu aylardır). Altına, kuralın hangi aylarda etkin
    olacağını canlı gösteren bir bilgi satırı basar.
    """
    START_ALL = "Sezon başı (tüm sezon)"
    END_ALL = "Sezon sonuna kadar"
    c1, c2 = st.columns(2)
    start_opts = [START_ALL] + months
    default_idx = start_opts.index(default_start) if default_start in months else 0
    start = c1.selectbox(
        "Başlangıç ayı — bu ay **dahil**",
        start_opts,
        index=default_idx,
        key="rule_start_month",
        help="Kural bu aydan itibaren (bu ay DAHİL) uygulanır. Sezon "
        "ortasında eklenen kural, tamamlanmış geçmiş ayları etkilemez ve "
        "orada ihlal sayılmaz.",
    )
    end_opts = [END_ALL] + months
    end = c2.selectbox(
        "Bitiş ayı — bu ay **dahil** (isteğe bağlı)",
        end_opts,
        index=0,
        key="rule_end_month",
        help="Kural bu aya kadar (bu ay DAHİL) geçerlidir; boş bırakılırsa "
        "sezon sonuna kadar sürer.",
    )
    start_val = "" if start == START_ALL else start
    end_val = "" if end == END_ALL else end
    # Kuralın etkin olacağı ayları canlı göster (seçilenler dahil)
    active = _window_months(months, start_val, end_val)
    if active:
        st.caption(
            "📆 Bu kural şu aylarda geçerli olacak (seçtiğiniz aylar **dahil**): "
            + " · ".join(active)
        )
    else:
        st.caption(
            "⚠️ Seçilen aralık boş — başlangıç ayı bitiş ayından sonra."
        )
    return start_val, end_val


def _window_months(months, start, end) -> list[str]:
    """Verilen pencereye (dahil sınırlar) düşen ayların listesi."""
    s = months.index(start) if start in months else 0
    e = months.index(end) if end in months else len(months) - 1
    return months[s : e + 1] if s <= e else []


def _rules_tab(store) -> None:
    students = store.load_students()
    units = store.load_units()
    months = store.load_settings()["months"]
    rules = store.load_custom_rules()
    assignments = store.load_assignments()
    students_by_id = {s.id: s for s in students}
    units_by_id = {u.id: u for u in units}
    default_start = _next_unplanned_month(months, assignments)

    st.caption(
        "Yerleşik 19 kural her zaman uygulanır. Buraya eklediğiniz özel "
        "kurallar hem rotasyon oluştururken hem kural denetiminde dikkate "
        "alınır. Ayrı/birlikte tut ve birim yasağı **belirli bir aydan "
        "itibaren** geçerli kılınabilir; sezon ortasında eklenen kural "
        "tamamlanmış geçmiş ayları etkilemez."
    )
    with st.expander("ℹ️ Yerleşik kurallar (özet)"):
        st.markdown(_BUILTIN_RULES_SUMMARY)

    if rules:
        st.subheader("Tanımlı özel kurallar")
        for rule in rules:
            c1, c2, c3 = st.columns([6, 1, 1])
            desc = _describe_rule(rule, students_by_id, units_by_id, months)
            if rule.note:
                desc += f" — _{rule.note}_"
            c1.markdown(desc)
            new_active = c2.toggle(
                "Aktif", value=rule.active, key=f"rule_active_{rule.id}"
            )
            if new_active != rule.active:
                rule.active = new_active
                store.save_custom_rules(rules)
            if c3.button("🗑️", key=f"rule_del_{rule.id}", help="Kuralı sil"):
                store.save_custom_rules([r for r in rules if r.id != rule.id])
                st.rerun()
        st.divider()

    st.subheader("➕ Yeni kural ekle")
    if not students:
        st.info("Kural tanımlamak için önce öğrenci ekleyin.")
        return
    rtype = st.selectbox(
        "Kural türü",
        CUSTOM_RULE_TYPES,
        format_func=CUSTOM_RULE_LABELS.get,
        key="new_rule_type",
    )
    student_options = {
        f"{s.full_name} ({s.group}. grup)": s.id
        for s in sorted(students, key=lambda s: (s.group, s.full_name))
    }
    note = ""
    if rtype == RULE_SABIT_ATAMA:
        c1, c2, c3 = st.columns(3)
        who = c1.selectbox("Öğrenci", list(student_options), key="rule_student")
        month = c2.selectbox("Ay", months, key="rule_month")
        sid = student_options[who]
        student = students_by_id[sid]
        unit_opts = {
            unit_label(u): u.id
            for u in sorted(units, key=lambda u: u.name)
            if u.active and u.quota > 0 and u.group in (0, student.group)
        }
        unit_pick = c3.selectbox("Birim", list(unit_opts), key="rule_unit")
        note = st.text_input("Not (isteğe bağlı)", key="rule_note_sabit")
        if st.button("Kuralı ekle", type="primary", key="add_rule_sabit"):
            rules.append(
                CustomRule(
                    type=RULE_SABIT_ATAMA,
                    student_ids=[sid],
                    unit_id=unit_opts[unit_pick],
                    month=month,
                    note=note.strip(),
                )
            )
            store.save_custom_rules(rules)
            st.success("Kural eklendi. ✅")
            st.rerun()
    elif rtype == RULE_BIRIM_YASAK:
        picks = st.multiselect(
            "Öğrenci(ler)", list(student_options), key="rule_ban_students",
            help="Bu öğrenciler seçilen birime (belirtilen aydan itibaren) "
            "atanmaz. Kalıcı/tıbbi yasak için Öğrenciler sekmesindeki "
            "'yasaklı birimler' alanını kullanın.",
        )
        pick_groups = {students_by_id[student_options[p]].group for p in picks}
        # yasak birim seçenekleri: seçili öğrencilerin grubuna uygun
        unit_opts = {
            unit_label(u): u.id
            for u in sorted(units, key=lambda u: u.name)
            if u.active and (not pick_groups or u.group in {0, *pick_groups})
        }
        unit_pick = st.selectbox(
            "Yasaklı birim", list(unit_opts), key="rule_ban_unit"
        )
        start, end = _window_pickers(months, default_start)
        note = st.text_input("Not (isteğe bağlı)", key="rule_note_ban")
        if st.button(
            "Kuralı ekle", type="primary",
            disabled=not picks or not unit_pick, key="add_rule_ban",
        ):
            rules.append(
                CustomRule(
                    type=RULE_BIRIM_YASAK,
                    student_ids=[student_options[p] for p in picks],
                    unit_id=unit_opts[unit_pick],
                    start_month=start,
                    end_month=end,
                    note=note.strip(),
                )
            )
            store.save_custom_rules(rules)
            st.success("Kural eklendi. ✅")
            st.rerun()
    else:
        picks = st.multiselect(
            "Öğrenciler (en az 2)", list(student_options), key="rule_students"
        )
        start, end = _window_pickers(months, default_start)
        note = st.text_input("Not (isteğe bağlı)", key="rule_note_pair")
        groups = {students_by_id[student_options[p]].group for p in picks}
        if len(groups) > 1:
            st.warning(
                "Seçilen öğrenciler farklı gruplarda — gruplar zaten ayrı "
                "planlandığı için bu kural etkisiz olur."
            )
        if st.button(
            "Kuralı ekle", type="primary",
            disabled=len(picks) < 2, key="add_rule_pair",
        ):
            rules.append(
                CustomRule(
                    type=rtype,
                    student_ids=[student_options[p] for p in picks],
                    start_month=start,
                    end_month=end,
                    note=note.strip(),
                )
            )
            store.save_custom_rules(rules)
            st.success("Kural eklendi. ✅")
            st.rerun()
