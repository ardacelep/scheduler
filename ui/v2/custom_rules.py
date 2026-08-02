"""Özel Kurallar — bu sezona özgü tekil istisnalar.

**Gereksinimler ekranından farkı:** Gereksinimler *"kim hangi birimlerden kaç
kez"* der ve bir öğrenci kümesine uygulanır. Burası ise adı geçen kişilere
dair tekil istisnalardır: şu iki kişi ayrı/birlikte kalsın, şu öğrenci şu
birime gitmesin, şu öğrenci şu ayda şu birimde olsun.

Bu ekran Veri Yönetimi'nin bir sekmesiydi. Oradan alınıp Gereksinimler'in
hemen altına ayrı bir sayfa yapıldı: Veri Yönetimi sezondan sezona TAŞINAN
bilgilerin yeri, kurallar ise sezona özgü — her sezon yeniden kurulur.
Kuralları kurarken zaten Gereksinimler'le birlikte düşünülür.
"""
from __future__ import annotations

import streamlit as st

from rotasyon.models import (
    CustomRule,
    CUSTOM_RULE_LABELS,
    CUSTOM_RULE_TYPES,
    RULE_AYRI_TUT,
    RULE_BIRIM_YASAK,
    RULE_BIRLIKTE_TUT,
    RULE_SABIT_ATAMA,
)
from ..common import unit_label

_BUILTIN_RULES_SUMMARY = """
1. Aynı bölüme ikinci kez gidilmez • 2-3. Kırmızı **k/e** birimlere yalnız o
cinsiyet • 4. Tekli birimler önce dolar, kalanlar havuza eşit dağılır •
5. Gruplar bağımsız • 6. Sezon boyunca herkes **bir cerrahi, bir dahili,
bir yoğun bakım ve bir palyatif** görür • 7. Ebelik öğrencileri doğum salonu
görür • 8. Yasaklı birimler • 9. Diş muafiyeti • 10. Özel not • 11. Gün bazlı
görevlendirme notu • 12. Kontenjanlar düzenlenebilir • 13-14. Sınıflar ve
renkleri • 15. Tek ay görünümü renksiz • 16. Öğrenci geçmişi • 17. FTR ve
2.KAT ÇOCUK-DOĞUM'a 1 kız 1 erkek • 18. Doğum birimlerinde ebelik önceliği •
19. Aynı ikili tekrar aynı birimde olmaz • 20. Peş peşe iki ay **yoğun** (veya
**hafif**) bölüme verilmez • 21. Havuz birimlerinde kız/erkek dengesi gözetilir
(dengesizlik ancak takas ile düzeltilebilir olduğunda uyarı verilir;
gruptaki kız/erkek sayısı zaten dengesizse uyarı üretilmez) •
**Yedek (gri) birimlere** yalnız ihtiyaç olursa öğrenci verilir.

Bu kurallar öğrenci/birim tanımlarındaki alanlarla (cinsiyet kısıtı, branş
kategorisi, yoğunluk, yedeklik, yasaklı birimler...) beslenir ve her zaman
uygulanır.

**6 ve 7 artık burada değil:** hangi öğrencinin hangi birimleri görmesi
gerektiğini **Gereksinimler** ekranından siz belirliyorsunuz. Yukarıdaki
ifade, gereksinim tanımlanmamış eski sezonlarda geçerli olan varsayılandır.
"""


def render(store) -> None:
    st.header("📏 Özel Kurallar")
    st.caption(
        "Adı geçen öğrencilere dair **tekil istisnalar**: ayrı/birlikte "
        "tutma, birim yasağı, sabit atama. Bir öğrenci kümesinin hangi "
        "birimleri görmesi gerektiğini burada değil **Gereksinimler** "
        "ekranında tanımlarsınız."
    )
    _link_requirements()
    st.divider()
    _rules_panel(store)


def _link_requirements() -> None:
    pages = st.session_state.get("_pages", {})
    if "gereksinimler" in pages:
        st.page_link(
            pages["gereksinimler"],
            label="Birim görme zorunlulukları için Gereksinimler'e git",
            icon="🎯",
        )


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


def _rules_panel(store) -> None:
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
        # Kural EKLENMEDEN önce gelecekteki çakışmayı söyle: sabit atamanın
        # klasik tuzağı, öğrencinin o birime başka bir ayda zaten gidiyor
        # olması — o zaman seçilen ayda madde 1 kesin çiğnenir.
        _fixed_rule_preview(
            store, students_by_id, units, sid, unit_opts.get(unit_pick), month,
            rules,
        )
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
            "atanmaz. Kalıcı/tıbbi yasak için Veri Yönetimi ▸ Öğrenciler "
            "sekmesindeki 'yasaklı birimler' alanını kullanın.",
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
        if rtype == RULE_BIRLIKTE_TUT and len(picks) >= 2:
            _together_rule_preview(
                [students_by_id[student_options[p]] for p in picks], units
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


def _fixed_rule_preview(store, students_by_id, units, sid, unit_id, month,
                        rules) -> None:
    """Sabit atama kuralı eklenmeden önce çakışma uyarısı.

    Aynı denetim risk panelinde de var; burada göstermenin değeri, sorunun
    OLUŞMASINI engellemek — kullanıcı kuralı eklemeden vazgeçebilir.
    """
    if not unit_id:
        return
    from rotasyon.models import CustomRule as _CR
    from rotasyon.risk import fixed_assignment_conflicts

    taslak = _CR(
        type=RULE_SABIT_ATAMA, student_ids=[sid], unit_id=unit_id, month=month
    )
    sorunlar = fixed_assignment_conflicts(
        taslak,
        students_by_id,
        {u.id: u for u in units},
        store.load_assignments(),
        rules + [taslak],
    )
    for msg in sorunlar:
        st.warning(f"⚠️ {msg}")
    if sorunlar:
        st.caption(
            "Kuralı yine de ekleyebilirsiniz; bu yalnız uyarıdır. Ancak bu "
            "haliyle ilgili ayda kural çiğnenecek."
        )


def _together_rule_preview(picked_students, units) -> None:
    """'Birlikte tut' eklenmeden önce: bu kişileri alabilecek birim var mı?"""
    from rotasyon.risk import units_fitting_all

    k = len(picked_students)
    uygun = units_fitting_all(picked_students, units)
    if uygun:
        st.caption(
            f"✅ Bu {k} öğrenciyi birlikte alabilecek {len(uygun)} birim var."
        )
        return
    st.warning(
        f"⚠️ Bu {k} öğrenciyi aynı anda alabilecek hiçbir birim yok "
        f"(kontenjanı en az {k} olan ve hepsinin cinsiyet/grup/yasak "
        "kısıtlarına uyan birim bulunmuyor). Kural eklenirse her ay ihlal "
        "edilir."
    )
