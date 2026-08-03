"""Gereksinimler ekranı — sezonun kurallarını gelen öğrencilere göre belirleme.

Tek kavram: **KİME — HANGİ BİRİMLERDEN — KAÇ KEZ**.

v1'de "her öğrenci bir yoğun bakım görmeli" demek için önce birimlere branş
atanır, sonra o branş sezon zorunluluklarına eklenirdi. Bu dolayım gizliydi ve
zorunluluğu herkese uygulardı; tek istisna (ebelik → doğum salonu) koda
gömülüydü. Burada kullanıcı cümlesini doğrudan kurar: "Ebe Yardımcılığı
öğrencileri — DOĞ.SAL, 2.KAT DOĞUM birimlerinden en az 1".

Branş kavramı silinmedi ama geri plana çekildi: artık kural semantiği değil,
birim seçerken kullanılan bir **hızlı seçim kısayolu**.
"""
from __future__ import annotations

import streamlit as st

from rotasyon.models import (
    BRANCH_CATEGORIES,
    BRANCH_LABELS,
    PROGRAMS,
    PROGRAM_LABELS,
    Requirement,
    SCOPE_ALL,
    SCOPE_CLASS,
    SCOPE_GROUP,
    SCOPE_LABELS,
    SCOPE_PROGRAM,
    SCOPE_STUDENTS,
    SEVERITIES,
    SEVERITY_LABELS,
    SEVERITY_REQUIRED,
)
from rotasyon.normalize import normalize_key
from rotasyon.requirements import applies_to, compile_for_student, describe
from rotasyon.requirements import from_legacy_settings
from ..common import clear_stale_state, data_fingerprint, group_label


def render(store) -> None:
    st.header("🎯 Gereksinimler")
    st.caption(
        "Bu sezonun kurallarını **gelen öğrencilere göre** burada belirlersiniz. "
        "Her satır tek bir cümledir: *kime* — *hangi birimlerden* — *kaç kez*. "
        "Branş seçmenize gerek yok; birimleri doğrudan adıyla seçersiniz."
    )

    units = store.load_units()
    students = store.load_students()

    # "Yeni gereksinim" formu session_state'te BEKLEYEN seçimler tutuyor:
    # birim adları ve ÖĞRENCİ NESNELERİ. Öğrenci listesi yeniden içe
    # aktarılırsa (ya da sezon değişirse) o nesneler ölü id'lere işaret eder
    # ve kaydedilen gereksinim hiç kimseyi kapsamaz; kaybolan bir birim adı
    # ise multiselect'i "default option'da yok" hatasıyla düşürür.
    # Parmak izi bilerek YALNIZ öğrenci+birim üzerinden alınır: gereksinim
    # eklemek/silmek yarı dolu formu temizlemesin.
    clear_stale_state(
        "_req_fp",
        data_fingerprint(students, units),
        ("req_new_", "req_branch_"),
    )

    if not units:
        st.info("Önce Veri Yönetimi'nden birim ekleyin.")
        return

    reqs = store.load_requirements()
    if not reqs:
        _empty_state(store, units)
        return

    _list_panel(store, reqs, units, students)
    st.divider()
    _editor(store, reqs, units, students)


def _unit_names(units) -> list[str]:
    """Katalogdaki AYRI birim adları (grup-1/grup-2 satırları tek ada iner)."""
    seen: dict[str, str] = {}
    for u in units:
        seen.setdefault(normalize_key(u.name), u.name)
    return sorted(seen.values())


def _empty_state(store, units) -> None:
    """Gereksinim yokken iki hazır başlangıç yolu sunar.

    Varsayılan katalogdan açılan yeni sezonlar gereksinimleri ZATEN hazır alır
    (create_season_with_units). Bu ekran, o yoldan gelmemiş sezonlar için
    duruyor: elle kurulmuş sezonlar ve v2'den önce açılmış olanlar.
    """
    from rotasyon.catalog import load_default_requirements

    st.info("Bu sezon için henüz gereksinim tanımlanmamış.")

    hazir = load_default_requirements()
    if hazir:
        st.markdown("**📦 Hazır kural seti** (rotasyon belgelerindeki kurallar):")
        for r in hazir:
            st.markdown(f"- **{r.name}** — {describe(r)}")
        if st.button("Bu seti kur", type="primary", key="req_default"):
            store.save_requirements(hazir)
            st.toast(f"{len(hazir)} gereksinim kuruldu ✅", icon="🎯")
            st.rerun()

    # Eski sezonlar için: settings.season_requirements branşlarından üret.
    # Hazır set varken bu ikinci yol yalnız o sezona ÖZEL bir branş listesi
    # varsa anlamlı — o yüzden ikincil ve katlanmış duruyor.
    preview = from_legacy_settings(store.load_settings(), units)
    if preview:
        with st.expander("⚙️ Bu sezonun eski ayarlarından üret"):
            st.caption(
                "Sezonun **Ayarlar**'ında kayıtlı branş zorunluluklarından "
                "üretir. Hazır set size uymuyorsa ya da bu sezona özel bir "
                "liste tanımladıysanız kullanın."
            )
            for r in preview:
                st.markdown(f"- **{r.name}** — {describe(r)}")
            if st.button("Eski ayarlardan üret", key="req_import"):
                store.save_requirements(preview)
                st.toast(f"{len(preview)} gereksinim oluşturuldu ✅", icon="🎯")
                st.rerun()

    st.divider()
    _editor(store, [], units, store.load_students())


def _coverage(req, students, units) -> tuple[int, dict[int, int]]:
    """Kaç öğrenciyi kapsıyor + grup başına kaç uygun birim var."""
    covered = [s for s in students if applies_to(req, s)]
    per_group: dict[int, int] = {}
    for g in sorted({s.group for s in covered}):
        sample = next(s for s in covered if s.group == g)
        per_group[g] = len(compile_for_student(req, sample, units))
    return len(covered), per_group


def _coverage_note(req, students, units) -> None:
    """Kural kaydedilmeden önce kimi vurduğunu göster."""
    n, per_group = _coverage(req, students, units)
    if not students:
        st.caption("Öğrenci listesi boş — kapsam hesaplanamıyor.")
        return
    parts = [f"**{n} öğrenciyi** kapsıyor"]
    for g, count in per_group.items():
        parts.append(f"{group_label(students, g)}: **{count}** uygun birim")
    st.caption(" · ".join(parts))
    if n == 0:
        st.warning("⚠️ Bu gereksinim hiçbir öğrenciyi kapsamıyor.")
        return
    # NOT: mesajlar "Grup 1:" diye yazılır, "1. grup" diye DEĞİL — Markdown
    # satır başındaki "1." ifadesini sıralı liste madde işareti sanıp numarayı
    # yutuyor ve kullanıcı hangi gruptan söz edildiğini göremiyor.
    for g, count in per_group.items():
        if count == 0:
            st.error(
                f"❌ {group_label(students, g)}: bu gereksinimi karşılayan "
                "aktif birim yok — bu haliyle o gruptaki öğrenciler için "
                "çözüm bulunamaz."
            )
        elif count < req.min_count:
            st.error(
                f"❌ {group_label(students, g)}: yalnız {count} uygun birim "
                f"var ama {req.min_count} ziyaret isteniyor. Aynı bölüme "
                "ikinci kez gidilemediği için bu karşılanamaz."
            )


def _list_panel(store, reqs, units, students) -> None:
    aktif = [r for r in reqs if r.active]
    st.caption(f"{len(aktif)} aktif · {len(reqs) - len(aktif)} pasif gereksinim")

    for req in reqs:
        with st.container(border=True):
            baslik = f"**{req.name}**"
            if not req.active:
                baslik = (
                    f"<span style='color:#999;text-decoration:line-through'>"
                    f"{req.name}</span> <span style='color:#c00;font-size:0.8em'>"
                    "pasif</span>"
                )
                st.markdown(baslik, unsafe_allow_html=True)
            else:
                st.markdown(baslik)
            st.caption(describe(req))
            if req.active:
                _coverage_note(req, students, units)
            if req.note:
                st.caption(f"📝 {req.note}")

            # Butonlar SÜTUNA değil yatay kaba konur: sabit oranlı sütunlar
            # pencere daralınca etiketi sarıyordu ("Pasifleşti / r"). Yatay kap
            # her butona kendi metnine yetecek genişliği verir, sığmazsa
            # kelimeyi kırmak yerine butonu alt satıra alır.
            duzenle_key = f"req_edit_{req.id}"
            aciksa = st.session_state.get("req_editing") == req.id
            with st.container(horizontal=True):
                if st.button("Düzenle" if not aciksa else "Kapat",
                             icon="✏️" if not aciksa else "✖️",
                             key=duzenle_key):
                    st.session_state["req_editing"] = None if aciksa else req.id
                    st.rerun()
                if st.button("Aktifleştir" if not req.active else "Pasifleştir",
                             icon="▶️" if not req.active else "⏸️",
                             key=f"req_toggle_{req.id}"):
                    req.active = not req.active
                    store.save_requirements(reqs)
                    st.rerun()
                if st.button("Sil", icon="🗑️", key=f"req_del_{req.id}"):
                    store.save_requirements(
                        [r for r in reqs if r.id != req.id]
                    )
                    st.session_state.pop("req_editing", None)
                    st.toast(f"'{req.name}' silindi", icon="🗑️")
                    st.rerun()

            if aciksa:
                _inline_edit(store, reqs, req, units, students)


def _inline_edit(store, reqs, req, units, students) -> None:
    """Var olan gereksinimi yerinde düzenler.

    Ayrı bir "düzenle" ekranı yerine satırın altında açılır: kullanıcı
    değiştirdiği kuralı listede gördüğü yerde düzenler. Önceden yalnız
    ekle/sil vardı, bir kelimeyi değiştirmek için kuralı silip yeniden
    kurmak gerekiyordu.
    """
    st.divider()
    names = _unit_names(units)
    k = f"re_{req.id}"

    ad = st.text_input("Gereksinim adı", value=req.name, key=f"{k}_ad")

    scope = st.radio(
        "Kime uygulanır?", list(SCOPE_LABELS),
        format_func=lambda s: SCOPE_LABELS[s],
        index=list(SCOPE_LABELS).index(req.scope)
        if req.scope in SCOPE_LABELS else 0,
        horizontal=True, key=f"{k}_scope",
    )
    scope_value, student_ids = "", list(req.student_ids)
    if scope == SCOPE_GROUP:
        gruplar = sorted({s.group for s in students}) or [1, 2]
        mevcut = [str(g) for g in gruplar]
        scope_value = str(st.selectbox(
            "Grup", gruplar, key=f"{k}_grup",
            format_func=lambda g: group_label(students, g),
            index=mevcut.index(req.scope_value)
            if req.scope_value in mevcut else 0,
        ))
    elif scope == SCOPE_CLASS:
        classes = sorted({s.class_name for s in students if s.class_name})
        if classes:
            scope_value = st.selectbox(
                "Sınıf", classes, key=f"{k}_sinif",
                index=classes.index(req.scope_value)
                if req.scope_value in classes else 0,
            )
    elif scope == SCOPE_PROGRAM:
        scope_value = st.selectbox(
            "Program", PROGRAMS, format_func=lambda p: PROGRAM_LABELS.get(p, p),
            index=PROGRAMS.index(req.scope_value)
            if req.scope_value in PROGRAMS else 0,
            key=f"{k}_prog",
        )
    elif scope == SCOPE_STUDENTS:
        by_id = {s.id: s for s in students}
        secim = st.multiselect(
            "Öğrenciler", list(by_id),
            default=[sid for sid in req.student_ids if sid in by_id],
            format_func=lambda sid: (
                f"{by_id[sid].full_name} (grup {by_id[sid].group})"
            ),
            key=f"{k}_ogr",
        )
        student_ids = [sid for sid in secim if sid in by_id]

    # kayıttaki anahtarlar normalize; gösterim adlarına çevrilir
    mevcut_adlar = [
        n for n in names if normalize_key(n) in
        {normalize_key(x) for x in req.unit_keys}
    ]
    secili = st.multiselect(
        "Birimler", names, default=mevcut_adlar, key=f"{k}_birim",
    )
    c1, c2 = st.columns(2)
    minc = c1.number_input(
        "En az kaç birim görülmeli", min_value=1,
        max_value=max(1, len(secili)) if secili else 1,
        value=min(req.min_count, max(1, len(secili))) if secili
        else 1,
        key=f"{k}_min",
    )
    severity = c2.selectbox(
        "Tür", SEVERITIES, format_func=lambda s: SEVERITY_LABELS[s],
        index=SEVERITIES.index(req.severity)
        if req.severity in SEVERITIES else 0,
        key=f"{k}_tur",
    )

    yeni = Requirement(
        id=req.id, name=ad.strip() or req.name, scope=scope,
        scope_value=scope_value, student_ids=student_ids,
        unit_keys=[normalize_key(n) for n in secili],
        min_count=int(minc), severity=severity, active=req.active,
        note=req.note,
    )
    if secili:
        st.markdown("**Önizleme:** " + describe(yeni))
        _coverage_note(yeni, students, units)

    degisti = yeni.to_dict() != req.to_dict()
    hazir = bool(ad.strip()) and bool(secili) and degisti
    if scope in (SCOPE_GROUP, SCOPE_CLASS, SCOPE_PROGRAM) and not scope_value:
        hazir = False
    if scope == SCOPE_STUDENTS and not student_ids:
        hazir = False

    if st.button("💾 Değişiklikleri kaydet", type="primary",
                 disabled=not hazir, key=f"{k}_kaydet"):
        store.save_requirements(
            [yeni if r.id == req.id else r for r in reqs]
        )
        st.session_state["req_editing"] = None
        st.toast(f"'{yeni.name}' güncellendi ✅", icon="🎯")
        st.rerun()
    if not degisti:
        st.caption("Bir şey değiştirince kaydedebilirsiniz.")


def _editor(store, reqs, units, students) -> None:
    st.subheader("➕ Yeni gereksinim")
    names = _unit_names(units)
    classes = sorted({s.class_name for s in students if s.class_name})

    ad = st.text_input(
        "Gereksinim adı", key="req_new_name",
        placeholder="örn. Yoğun bakım",
        help="İhlal mesajlarında bu ad görünür.",
    )

    st.markdown("**Kime uygulanır?**")
    scope = st.radio(
        "Kapsam", list(SCOPE_LABELS),
        format_func=lambda s: SCOPE_LABELS[s],
        horizontal=True, key="req_new_scope", label_visibility="collapsed",
    )
    scope_value, student_ids = "", []
    if scope == SCOPE_GROUP:
        gruplar = sorted({s.group for s in students}) or [1, 2]
        scope_value = str(
            st.selectbox(
                "Grup", gruplar, key="req_new_group",
                format_func=lambda g: group_label(students, g),
            )
        )
    elif scope == SCOPE_CLASS:
        if not classes:
            st.warning("Öğrencilerde sınıf bilgisi yok.")
        else:
            scope_value = st.selectbox("Sınıf", classes, key="req_new_class")
    elif scope == SCOPE_PROGRAM:
        scope_value = st.selectbox(
            "Program", PROGRAMS,
            format_func=lambda p: PROGRAM_LABELS.get(p, p),
            key="req_new_program",
        )
    elif scope == SCOPE_STUDENTS:
        # Seçenekler ÖĞRENCİ NESNESİ değil id: session_state'te kalan bir
        # nesne, öğrenci düzenlenince hiçbir seçeneğe eşit olmaz ve widget
        # düşer. id ile tutulunca en kötü durumda seçim sessizce boşalır.
        by_id = {s.id: s for s in students}
        secim = st.multiselect(
            "Öğrenciler", list(by_id),
            format_func=lambda sid: (
                f"{by_id[sid].full_name} (grup {by_id[sid].group})"
            ),
            key="req_new_students",
        )
        student_ids = [sid for sid in secim if sid in by_id]

    st.markdown("**Hangi birimlerden?**")
    # Bekleyen seçim, artık var olmayan bir birim adı içeriyorsa multiselect
    # "default option'larda yok" diye patlar — mevcut adlarla kesiştir.
    # (clear_stale_state çoğu durumu zaten temizler; bu son savunma.)
    onerilen = [
        n for n in st.session_state.get("req_branch_pick", []) if n in names
    ]
    secili_birimler = st.multiselect(
        "Birimler", names, default=onerilen, key="req_new_units",
        help="Birimleri doğrudan adıyla seçin. Aynı ad her iki grupta da "
        "varsa öğrencinin kendi grubundaki birim otomatik kullanılır.",
    )
    with st.expander("⚡ Branşa göre hızlı seçim"):
        st.caption(
            "Branş artık bir kural değil, yalnız birim seçmeyi kolaylaştıran "
            "bir etiket. Seçtiğiniz branştaki birim adlarını yukarıdaki "
            "listeye ekler."
        )
        b = st.selectbox(
            "Branş", BRANCH_CATEGORIES,
            format_func=lambda x: BRANCH_LABELS.get(x, x), key="req_branch_sel",
        )
        eslesen = _unit_names([u for u in units if u.branch_category == b])
        st.caption(
            f"{len(eslesen)} birim: {', '.join(eslesen) if eslesen else '—'}"
        )
        if st.button("Listeye ekle", key="req_branch_add", disabled=not eslesen):
            st.session_state["req_branch_pick"] = sorted(
                set(secili_birimler) | set(eslesen)
            )
            st.rerun()

    c1, c2 = st.columns(2)
    n_secili = len(secili_birimler)
    min_count = c1.number_input(
        "En az kaç birim görülmeli", min_value=1,
        max_value=max(1, n_secili) if secili_birimler else 1,
        value=1, key="req_new_min",
        help="**1** = listedekilerden **herhangi biri** yeterli (en sık "
        "kullanılan). Seçtiğiniz birim sayısına eşitlerseniz **hepsi** "
        "zorunlu olur.",
    )
    severity = c2.selectbox(
        "Tür", SEVERITIES, format_func=lambda s: SEVERITY_LABELS[s],
        key="req_new_severity",
        help="**Zorunlu**: karşılanmazsa çözücü o sezonu üretmez, denetleyici "
        "hata verir. **Tercih**: çözücü karşılamaya çalışır ama gerekirse "
        "vazgeçer; karşılanmazsa yalnız uyarı çıkar, kaydı engellemez.",
    )
    # "Hepsi zorunlu" durumunda ayrı satırlar daha okunur hata mesajı verir:
    # tek satır "2 ziyaret eksik" der, ayrı satırlar HANGİSİNİN eksik olduğunu
    # söyler. Kullanıcıyı zorlamıyoruz, yalnız hatırlatıyoruz.
    if secili_birimler and int(min_count) == n_secili and n_secili > 1:
        st.info(
            f"ℹ️ Bu haliyle **{n_secili} birimin hepsi** zorunlu olur. "
            "Bunlar birbirinin alternatifi değil de ayrı ayrı zorunluluksa, "
            "her biri için **ayrı bir gereksinim** eklemeniz daha iyi olur: "
            "o zaman denetleyici hangisinin eksik olduğunu adıyla söyler."
        )

    aday = Requirement(
        name=ad.strip() or "(adsız)",
        scope=scope, scope_value=scope_value, student_ids=student_ids,
        unit_keys=[normalize_key(n) for n in secili_birimler],
        min_count=int(min_count), severity=severity,
    )
    if secili_birimler:
        st.markdown("**Önizleme:** " + describe(aday))
        _coverage_note(aday, students, units)

    hazir = bool(ad.strip()) and bool(secili_birimler)
    if scope in (SCOPE_GROUP, SCOPE_CLASS, SCOPE_PROGRAM) and not scope_value:
        hazir = False
    if scope == SCOPE_STUDENTS and not student_ids:
        hazir = False

    if st.button("💾 Gereksinimi ekle", type="primary", disabled=not hazir,
                 key="req_new_save"):
        store.save_requirements(list(reqs) + [aday])
        st.session_state.pop("req_branch_pick", None)
        st.toast(f"'{aday.name}' eklendi ✅", icon="🎯")
        st.rerun()
    if not hazir:
        st.caption("Ad ve en az bir birim seçilince kaydedebilirsiniz.")
