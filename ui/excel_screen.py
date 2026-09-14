"""Excel İçe/Dışa Aktarım ekranı.

İçe aktarım dosya türünü kendisi algılar:
- Eşleşme rotasyon dosyası ("A-B EŞLEŞMESİ" başlıklı, altında birim bloğu
  olan sezon başı belgesi) → öğrenciler + birim kataloğu
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
from rotasyon.importer import (
    build_dataset,
    build_roster_dataset,
    default_class_group,
    roster_class_names,
)
from rotasyon.models import (
    BRANCH_LABELS,
    FEMALE,
    GENDER_LABELS,
    INTENSITY_LABELS,
    MALE,
    PROGRAM_HEMSIRELIK,
    PROGRAM_LABELS,
    PROGRAMS,
    SCOPE_PROGRAM,
)
from rotasyon.pdf_io import read_student_list_pdf
from .common import (
    UNITS_CATALOG,
    clear_stale_state,
    create_season_with_units,
    get_manager,
    group_label_md,
    unit_source_options,
)


def render(store) -> None:
    """İçe/dışa aktarım iki ayrı iştir; ikisini birden göstermek gereksiz.

    Sekme yerine tek seçim: seçilmeyen taraf hiç render edilmez (Streamlit
    sekmeleri hepsini DOM'a basar), ekran sade kalır ve kullanıcı hangi işi
    yaptığını her an görür.
    """
    st.header("📊 Excel")
    yon = st.segmented_control(
        "Ne yapmak istiyorsunuz?",
        ["📥 İçe aktar", "📤 Dışa aktar"],
        default="📥 İçe aktar",
        key="excel_yon",
        label_visibility="collapsed",
    )
    st.divider()
    if yon == "📤 Dışa aktar":
        _export_tab(store)
    else:
        _import_tab(store)


# ======================= İÇE AKTARIM =======================

def _import_tab(store) -> None:
    st.caption(
        "Desteklenen dosyalar ve türleri otomatik algılanır: **eşleşme "
        "rotasyon dosyası** (\"A-B EŞLEŞMESİ\" başlıklı sezon başı belgesi — "
        "öğrenciler ve birimler alınır), **rotasyon "
        "dosyası** (aylık sütunlu yıllık tablo, .xlsx), **öğrenci listesi** "
        "(.xlsx — 'SML ÖĞRENCİ LİSTESİ' benzeri ya da 'sıra | ad | şube-kod') "
        "ve **e-okul Sınıf Listesi PDF'i** (.pdf)."
    )
    file = st.file_uploader("Dosya seçin (.xlsx veya .pdf)", type=["xlsx", "pdf"])
    if file is None:
        return

    data = file.read()

    if file.name.lower().endswith(".pdf"):
        _pdf_roster_flow(data)
        return

    # Eşleşme dosyası da ay başlığı taşıdığı için genel "rotasyon" türüne
    # düşerdi; o okuyucu kural bloğunu öğrenci sanıyor. ÖNCE bu format sınanır.
    try:
        from rotasyon.pairing_import import is_pairing_workbook

        if is_pairing_workbook(BytesIO(data)):
            _pairing_import_flow(store, data)
            return
        kind = detect_workbook_kind(BytesIO(data))
    except Exception as exc:
        st.error(f"Dosya okunamadı: {exc}")
        return

    if kind == "rotation":
        _rotation_import_flow(store, data)
    elif kind == "student_list":
        _xlsx_roster_flow(data)
    else:
        st.error(
            "Dosya türü anlaşılamadı: ne ay sütunlu bir rotasyon tablosu ne de "
            "bir öğrenci listesi (ADI SOYADI/SINIF ya da 'sıra | ad | şube-kod') "
            "bulundu."
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
            width="stretch",
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


def _gender_validation_panel(ds, guesses, gender_counts) -> None:
    """PDF'teki şube-bazlı K/E sayılarıyla isim tahminini çapraz kontrol eder."""
    rows = []
    any_mismatch = False
    for sube in sorted(gender_counts):
        pdf_k, pdf_e = gender_counts[sube]
        subs = [s for s in ds.students if s.class_name == sube]
        g_k = sum(1 for s in subs if guesses[s.id].gender == FEMALE)
        g_e = sum(1 for s in subs if guesses[s.id].gender == MALE)
        g_unknown = len(subs) - g_k - g_e
        ok = g_k == pdf_k and g_e == pdf_e
        any_mismatch = any_mismatch or not ok
        rows.append(
            {
                "Şube": sube,
                "PDF (K/E)": f"{pdf_k} / {pdf_e}",
                "Tahmin (K/E)": f"{g_k} / {g_e}",
                "Belirsiz": g_unknown,
                "Durum": "✅" if ok else "⚠️",
            }
        )
    st.markdown("**Cinsiyet doğrulaması** (PDF sayıları ↔ isim tahmini)")
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    if any_mismatch:
        st.warning(
            "Bazı şubelerde tahmin, PDF'teki cinsiyet sayısıyla tutmuyor. "
            "İçe aktarımdan sonra Veri Yönetimi ekranından ilgili öğrencileri "
            "gözden geçirin (belirsizler ve tahmin hataları burada toplanır)."
        )
    else:
        st.success("İsim tahmini, PDF'teki tüm şube cinsiyet sayılarıyla tutuyor. ✅")


def _xlsx_roster_flow(data: bytes) -> None:
    try:
        roster, warns = read_student_list_workbook(BytesIO(data))
    except Exception as exc:
        st.error(f"Dosya çözümlenemedi: {exc}")
        return
    roster_import_flow(roster, warns)


def _pdf_roster_flow(data: bytes) -> None:
    try:
        result = read_student_list_pdf(BytesIO(data))
    except Exception as exc:
        st.error(f"PDF çözümlenemedi: {exc}")
        return
    if result.students:
        st.info(
            f"📄 e-okul PDF'inden **{len(result.students)}** öğrenci okundu "
            f"({len(result.gender_counts)} şube). Elle hazırladığınız listede "
            "bilerek çıkardığınız öğrenciler varsa, içe aktardıktan sonra "
            "Veri Yönetimi'nden pasifleştirin."
        )
    roster_import_flow(result.students, result.warnings, result.gender_counts)


def _class_group_mapping(class_names) -> dict:
    """Her sınıfın (şube) hangi gruba gireceğini kullanıcıya sorar.

    Varsayılan dönüşümlü (A-C→1, B-D→2); kullanıcı serbestçe değiştirir.
    Seçimler widget key'lerinde tutulur, yeniden çalışmada korunur.
    """
    st.markdown("**Sınıf → grup eşleştirmesi**")
    st.caption(
        "Her şubenin hangi gruba ait olacağını seçin. Rotasyonlar grup grup "
        "oluşturulur. Kalıcı değildir: sonradan **Veri Yönetimi ▸ 🎨 Sınıflar** "
        "sekmesindeki “Sınıf → grup eşleştirmesi” bölümünden topluca "
        "değiştirebilirsiniz."
    )
    defaults = default_class_group(class_names)
    mapping: dict[str, int] = {}
    cols = st.columns(min(len(class_names), 4) or 1)
    for i, name in enumerate(class_names):
        mapping[name] = cols[i % len(cols)].selectbox(
            f"{name} şubesi",
            [1, 2],
            index=defaults[name] - 1,
            format_func=lambda g: f"{g}. Grup",
            key=f"roster_grp_{name}",
        )
    counts = {g: sum(1 for v in mapping.values() if v == g) for g in (1, 2)}
    if 0 in counts.values():
        st.warning(
            "⚠️ Bir grupta hiç şube yok — genelde her iki gruba da şube "
            "atanır. Yine de devam edebilirsiniz."
        )
    return mapping


def roster_import_flow(roster, warns, gender_counts=None) -> None:
    st.subheader("Öğrenci listesi algılandı (sezon başı)")
    class_names = roster_class_names(roster)
    class_group = _class_group_mapping(class_names) if class_names else None
    ds = build_roster_dataset(roster, class_group=class_group)
    for w in warns + ds.warnings:
        st.warning(w)
    if not ds.students:
        return

    students_by_id = {s.id: s for s in ds.students}
    guesses = {s.id: guess_gender(s.full_name) for s in ds.students}
    if gender_counts:
        _gender_validation_panel(ds, guesses, gender_counts)
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
        width="stretch",
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
        options = unit_source_options(seasons)
        default_idx = options.index(UNITS_CATALOG) if UNITS_CATALOG in options else 0
        source = st.selectbox(
            "Birimler nereden gelsin?",
            options,
            index=default_idx,  # varsayılan: hazır birim kataloğu
            help="Varsayılan olarak hazır birim kataloğu gelir. Dilerseniz "
            "önceki bir sezonun birimlerini de kopyalayabilirsiniz "
            "(öğrenci ve atamalar kopyalanmaz).",
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
            st.toast(
                f"'{season_name.strip()}' sezonu oluşturuldu, "
                f"{len(ds.students)} öğrenci aktarıldı"
                + (
                    f"; {len(remaining)} öğrencinin cinsiyeti onayınızı bekliyor."
                    if remaining
                    else f" ({len(filled)} cinsiyet isimden dolduruldu)."
                ),
                icon="✅",
            )
            st.balloons()
            st.rerun()
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
            st.toast(
                f"{len(ds.students)} öğrenci '{active}' sezonuna aktarıldı"
                + (
                    f"; {len(remaining)} öğrencinin cinsiyeti onayınızı bekliyor."
                    if remaining
                    else f" ({len(filled)} cinsiyet isimden dolduruldu)."
                ),
                icon="✅",
            )
            st.rerun()


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
        "cinsiyet kısıtlı birimler kırmızı ve yanında (Kız)/(Erkek) yazılı."
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


# ======================= EŞLEŞME DOSYASI =======================

def _pairing_import_flow(store, data: bytes) -> None:
    """Sezon başı eşleşme belgesinden öğrenciler + birim kataloğu.

    Belgenin altındaki serbest metin kurallar bilerek ALINMAZ — sistematik
    ayrıştırılamıyor; kullanıcı onları Gereksinimler / Özel Kurallar
    ekranlarından kurar.
    """
    import hashlib

    from rotasyon.pairing_import import build_students, read_pairing_workbook

    st.subheader("Eşleşme rotasyon dosyası algılandı")
    st.caption(
        "Bu dosyadan **öğrenciler** ve **birimler** (kontenjan, cinsiyet "
        "kısıtı, branş, yoğunluk) alınır. En alttaki elle yazılmış kurallar "
        "alınmaz — onları Gereksinimler ve Özel Kurallar ekranlarından "
        "kurarsınız."
    )
    # Başka bir dosya yüklenince önceki dosyanın sınıf→bölüm seçimleri
    # session_state'te kalıp yanlış sınıfa uygulanmasın.
    clear_stale_state(
        "_pair_fp", hashlib.md5(data).hexdigest()[:12], ("pair_",)
    )

    try:
        result = read_pairing_workbook(BytesIO(data))
    except Exception as exc:
        st.error(f"Dosya çözümlenemedi: {exc}")
        return
    if not result.students:
        for w in result.warnings:
            st.warning(w)
        st.error("Dosyada öğrenci bulunamadı.")
        return

    gruplar = sorted({s.group for s in result.students})
    dosyadan_cinsiyet = sum(1 for s in result.students if s.gender)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Öğrenci", len(result.students))
    c2.metric("Sınıf", len({c.name for c in result.classes}))
    c3.metric("Birim (grup başına)", " / ".join(
        str(sum(1 for u in result.units if u.group == g)) for g in gruplar
    ))
    c4.metric("Cinsiyeti dosyada", dosyadan_cinsiyet)

    if result.warnings:
        with st.expander(f"⚠️ Dosyada dikkat edilecek {len(result.warnings)} nokta",
                         expanded=True):
            for w in result.warnings:
                st.markdown(f"- {w}")
    if result.ignored_assignments:
        st.info(
            f"{result.ignored_assignments} öğrencinin ay sütunlarında yazı var; "
            "bu içe aktarım atamaları ALMAZ, yalnız öğrencileri ve birimleri."
        )

    programlar = _pairing_class_programs(store, result)

    st.markdown("**Birimler**")
    for g in gruplar:
        _pairing_unit_table(result, g)

    ogrenciler, siniflar = build_students(result, programlar)
    with st.expander("👤 Öğrenci listesi"):
        st.markdown(
            "| Ad Soyad | Sınıf | Grup | Bölüm | Cinsiyet |\n|---|---|--:|---|---|\n"
            + "\n".join(
                f"| {s.full_name} | {s.class_name or '—'} | {s.group} | "
                f"{PROGRAM_LABELS.get(s.program, s.program)} | "
                f"{GENDER_LABELS.get(s.gender, '') if s.gender else 'isimden tahmin edilecek'} |"
                for s in ogrenciler
            )
        )

    _pairing_target(store, result, ogrenciler, siniflar, programlar)


def _pairing_class_programs(store, result) -> dict:
    """Sınıf → bölüm (program) seçimi.

    Belge bölüm bilgisi taşımıyor. Bölüm, gereksinimlerin kime uygulanacağını
    belirliyor ("Ebe Yardımcılığı öğrencileri doğum salonu görsün"); yanlış
    kalırsa o gereksinim SESSİZCE hiç kimseye uygulanmaz. Bu yüzden tahmin
    edilmez, sorulur — varsayılan, aktif sezonda aynı sınıftaki öğrencilerin
    bölümüdür.
    """
    from collections import Counter

    mevcut: dict[str, Counter] = {}
    for s in store.load_students():
        if s.class_name:
            mevcut.setdefault(s.class_name, Counter())[s.program] += 1

    st.markdown("**Sınıflar ve bölümleri**")
    st.caption(
        "Dosyada bölüm bilgisi yok. Her sınıfın bölümünü seçin — "
        "gereksinimler (örn. ebelik öğrencilerinin doğum birimleri) buna göre "
        "uygulanır."
    )
    programlar: dict[str, str] = {}
    siniflar = []
    for c in result.classes:
        if c.name not in {x.name for x in siniflar}:
            siniflar.append(c)
    kolonlar = st.columns(min(len(siniflar), 4) or 1)
    for i, c in enumerate(siniflar):
        varsayilan = (
            mevcut[c.name].most_common(1)[0][0]
            if c.name in mevcut else PROGRAM_HEMSIRELIK
        )
        with kolonlar[i % len(kolonlar)]:
            st.markdown(
                f'<span style="background:{c.color};padding:2px 10px;'
                f'border:1px solid #999">{c.name}</span>',
                unsafe_allow_html=True,
            )
            # "Grup 1" diye yazılır: "1. grup" satır başına gelirse Markdown
            # numarayı sıralı liste sanıp yutuyor.
            st.caption(f"Grup {c.group} · {c.count} öğrenci")
            programlar[c.name] = st.selectbox(
                f"{c.name} sınıfının bölümü", PROGRAMS,
                index=PROGRAMS.index(varsayilan) if varsayilan in PROGRAMS else 0,
                format_func=lambda p: PROGRAM_LABELS.get(p, p),
                key=f"pair_prog_{c.name}", label_visibility="collapsed",
            )
    return programlar


def _pairing_unit_table(result, group: int) -> None:
    from rotasyon.models import Student

    birimler = sorted(
        (u for u in result.units if u.group == group), key=lambda u: u.name
    )
    ogr = [Student(full_name=s.full_name, gender="", group=s.group,
                   class_name=s.class_name) for s in result.students]
    kontenjan = sum(u.quota for u in birimler)
    kisi = sum(1 for s in result.students if s.group == group)
    with st.expander(
        f"{group_label_md(ogr, group)} — {len(birimler)} birim, "
        f"toplam kontenjan {kontenjan} / {kisi} öğrenci"
    ):
        st.markdown(
            "| Birim | Kontenjan | Cinsiyet | Branş | Yoğunluk | Belgedeki yazım |\n"
            "|---|--:|---|---|---|---|\n"
            + "\n".join(
                f"| {u.name} | "
                f"{'kapalı' if u.quota == 0 else u.quota} | "
                f"{GENDER_LABELS.get(u.gender, '—') if u.gender else '—'} | "
                f"{BRANCH_LABELS.get(u.branch, '—') if u.branch else '—'} | "
                f"{INTENSITY_LABELS.get(u.intensity, '—') if u.intensity else '—'} | "
                f"{u.quota_text or '(yalnız yer çizelgesinde)'} |"
                for u in birimler
            )
        )


def _pairing_target(store, result, ogrenciler, siniflar, programlar) -> None:
    from rotasyon.catalog import load_default_units
    from rotasyon.pairing_import import build_units

    st.divider()
    manager = get_manager()
    active = manager.active_season()
    atamali = bool(active) and bool(store.load_assignments())

    secenekler = ["Yeni sezon oluştur"]
    if active:
        secenekler.append(f"Aktif sezona aktar ({active})")
    hedef = st.radio(
        "Nereye aktarılsın?", secenekler, key="pair_target",
        help="Sezon başı belgesi genelde yeni bir dönemin başlangıcıdır.",
    )

    yeni = hedef == "Yeni sezon oluştur"
    if yeni:
        sezon_adi = st.text_input(
            "Yeni sezon adı", placeholder="örn. 2026-2027", key="pair_season"
        )
        st.caption(
            "Birimler hazır katalogdan başlar ve bu dosyadaki kontenjan, "
            "cinsiyet, branş ve yoğunlukla güncellenir; dosyada olmayan "
            "katalog birimleri pasif kalır. Yeni sezona hazır gereksinim seti "
            "de gelir — Gereksinimler ekranından gözden geçirin."
        )
        katalog = load_default_units()
        hazir = bool(sezon_adi.strip())
    else:
        if atamali:
            st.error(
                f"**{active}** sezonunda kayıtlı atamalar var. Öğrenci listesini "
                "değiştirmek o atamaları sahipsiz bırakır — bu dosyayı yeni "
                "bir sezona aktarın."
            )
            return
        st.warning(
            f"**{active}** sezonundaki öğrenci, sınıf ve birim listesi bu "
            "dosyadakiyle DEĞİŞTİRİLİR. Gereksinimler, özel kurallar ve "
            "ayarlar korunur. Eski dosyaların yedeği `.json.bak` olarak kalır."
        )
        # kullanıcının bu sezonda yaptığı politika ayarları korunsun
        katalog = store.load_units() or load_default_units()
        hazir = st.checkbox("Anladım, değiştirilsin", key="pair_confirm")

    birimler, notlar = build_units(result, katalog)
    if notlar:
        with st.expander(f"ℹ️ Katalogla birleştirme notları ({len(notlar)})"):
            for n in notlar:
                st.markdown(f"- {n}")

    _pairing_requirement_check(store if not yeni else None, ogrenciler)

    if not st.button("📥 İçe aktar", type="primary", disabled=not hazir,
                     key="pair_go"):
        return

    if yeni:
        try:
            hedef_store = create_season_with_units(
                manager, sezon_adi.strip(), UNITS_CATALOG
            )
        except ValueError as exc:
            st.error(str(exc))
            return
    else:
        hedef_store = store

    dosyadan = sum(1 for s in ogrenciler if s.gender)
    doldurulan, kalan = fill_missing_genders(ogrenciler)
    hedef_store.save_students(ogrenciler)
    hedef_store.save_classes(siniflar)
    hedef_store.save_units(birimler)
    if result.day_labels:
        ayarlar = hedef_store.load_settings()
        ayarlar["day_labels"] = {
            str(g): etiket for g, etiket in result.day_labels.items()
        }
        hedef_store.save_settings(ayarlar)
    if yeni:
        manager.set_active(sezon_adi.strip())

    st.success(
        f"{len(ogrenciler)} öğrenci, {len(siniflar)} sınıf ve "
        f"{sum(1 for u in birimler if u.active)} aktif birim aktarıldı. "
        f"{dosyadan} öğrencinin "
        f"cinsiyeti dosyadan, {len(doldurulan)} öğrencininki isimden alındı"
        + (
            f"; {len(kalan)} öğrenci Veri Yönetimi'nde onayınızı bekliyor."
            if kalan else "."
        )
    )
    st.balloons()


def _pairing_requirement_check(store, ogrenciler) -> None:
    """Ebelik gereksinimi var ama hiçbir sınıf ebelik seçilmemişse uyar.

    Gereksinim kapsamı bölüme bağlı; eşleşme belgesi bölüm taşımadığı için
    yanlış seçim, gereksinimin sessizce kimseye uygulanmaması demek.
    """
    from rotasyon.catalog import load_default_requirements

    reqs = store.load_requirements() if store is not None else load_default_requirements()
    istenen = {
        r.scope_value for r in reqs
        if r.active and r.scope == SCOPE_PROGRAM
    }
    var = {s.program for s in ogrenciler}
    for p in sorted(istenen - var):
        st.warning(
            f"⚠️ **{PROGRAM_LABELS.get(p, p)}** öğrencileri için tanımlı bir "
            "gereksinim var ama hiçbir sınıfı bu bölüme ayırmadınız — o "
            "gereksinim kimseye uygulanmaz. Yukarıdan ilgili sınıfın bölümünü "
            "seçin."
        )
