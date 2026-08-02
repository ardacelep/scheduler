"""Ekranların ortak yardımcıları: store erişimi, seed yükleme, etiketler."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import streamlit as st

from rotasyon.catalog import (
    catalog_available,
    load_default_requirements,
    load_default_units,
)
from rotasyon.models import (
    Assignment,
    ClassGroup,
    Student,
    Unit,
    GENDER_LABELS,
)
from rotasyon.store import SeasonManager, Store

DATA_DIR = Path("data")
SEED_DIR = Path("seed_data")


def get_manager() -> SeasonManager:
    return SeasonManager(DATA_DIR)


def get_store() -> Store:
    """Aktif sezonun store'u."""
    return get_manager().store()


def has_data(store: Store) -> bool:
    return bool(store.load_students() or store.load_units())


def seed_available() -> bool:
    return (SEED_DIR / "students.json").exists()


def load_seed(store: Store) -> None:
    """seed_data/ içeriğini çalışma verisi olarak kopyalar."""

    def read(name):
        with open(SEED_DIR / f"{name}.json", encoding="utf-8") as f:
            return json.load(f)

    store.save_students([Student.from_dict(d) for d in read("students")])
    store.save_units([Unit.from_dict(d) for d in read("units")])
    store.save_classes([ClassGroup.from_dict(d) for d in read("classes")])
    # Örnek atamalar geçmiş olarak da yüklenir (madde 16 ekranı hemen dolu olur)
    store.save_assignments([Assignment.from_dict(d) for d in read("assignments")])


def data_fingerprint(*collections) -> str:
    """Verilen kayıt koleksiyonlarının içerik parmak izi.

    Ekranlar bunu "veri değişti mi?" kontrolü için kullanır: başka bir
    ekranda öğrenci/birim/atama düzenlendiyse, session_state'te bekleyen
    taslak öneri, sihirbaz adımı, tablo düzenleyici durumu gibi türetilmiş
    her şey geçersizdir ve temizlenmelidir — ekranda bayat uyarı/veri
    kalmasın.
    """
    h = hashlib.md5()
    for coll in collections:
        for item in coll:
            d = item.to_dict() if hasattr(item, "to_dict") else item
            h.update(
                json.dumps(
                    d, sort_keys=True, ensure_ascii=False, default=str
                ).encode()
            )
        h.update(b"|")
    return h.hexdigest()[:12]


def clear_stale_state(scope_key: str, fingerprint: str, prefixes) -> bool:
    """Parmak izi değiştiyse verilen öneklerle başlayan durumları siler.

    Dönüş: temizlik yapıldıysa True.
    """
    if st.session_state.get(scope_key) == fingerprint:
        return False
    st.session_state[scope_key] = fingerprint
    for k in list(st.session_state):
        if isinstance(k, str) and k.startswith(tuple(prefixes)):
            del st.session_state[k]
    return True


# ---- yeni sezon için birim kaynağı seçenekleri ----

UNITS_EMPTY = "(boş başla — birimleri elle gireceğim)"
UNITS_CATALOG = "📦 Varsayılan birim kataloğu"


def unit_source_options(seasons: list[str]) -> list[str]:
    """Yeni sezon açarken 'birimler nereden gelsin' seçenekleri.

    Sıralama: önce mevcut sezonlar (en pratik yol), sonra katalog, sonra boş.
    """
    options = list(seasons)
    if catalog_available():
        options.append(UNITS_CATALOG)
    options.append(UNITS_EMPTY)
    return options


def create_season_with_units(manager: SeasonManager, name: str, source: str) -> Store:
    """Yeni sezonu açar ve birimleri seçilen kaynaktan doldurur.

    Varsayılan katalog seçildiğinde **gereksinimler de** hazır gelir (belgelerde
    yazılı sezon kuralları); kullanıcı her sezon aynı beş-altı kuralı elle
    kurmak zorunda kalmaz. Önceki sezondan kopyalarken gereksinimler
    SeasonManager.create tarafından taşınır.
    """
    if source == UNITS_CATALOG:
        store = manager.create(name)
        store.save_units(load_default_units())
        if reqs := load_default_requirements():
            store.save_requirements(reqs)
        return store
    if source == UNITS_EMPTY:
        return manager.create(name)
    return manager.create(name, copy_units_from=source)


RISK_INTRO = (
    "Bu denetim, verinin sezon SONUNA kadar taşıyıp taşımayacağını üretime "
    "başlamadan hesaplar: birimler kalan aylarda dolabiliyor mu, her öğrenci "
    "zorunlu branşlarını görebiliyor mu, gidebileceği birim tükeniyor mu ve "
    "eklediğiniz özel kurallar ileride çakışacak mı. Kritik bulgular "
    "giderilmezse rotasyon bir noktada matematiksel olarak tıkanır ya da "
    "öğrenci eksik mezun olur — hiçbir çözücü bunu sonradan düzeltemez."
)


def collect_risks(students, units, months, assignments, custom_rules=None,
                  settings=None, requirements=None):
    """İleriye dönük risklerin tek kaynağı (rotasyon.risk.forward_risks).

    Ucuzdur (saf aritmetik, ortools yüklemez), her sayfa açılışında çağrılabilir.
    """
    from rotasyon.risk import forward_risks

    return forward_risks(
        students, units, months, assignments, custom_rules, settings,
        requirements,
    )


def season_requirements(store):
    """Bu sezonda geçerli gereksinimler — yoksa None (eski branş yolu).

    Motora giden HER çağrı bunu kullanmalı; aksi halde kullanıcının
    tanımladığı gereksinimler üretimi etkilemez (bir kez öyle oldu).
    """
    from rotasyon.requirements import active_requirements

    return active_requirements(store)


def show_risks(risks) -> None:
    """Riskleri kategori başlıklarıyla gruplayarak yazar."""
    from rotasyon.capacity import ERROR

    for category in dict.fromkeys(r.category for r in risks):
        st.markdown(f"**{category}**")
        for r in [x for x in risks if x.category == category]:
            (st.error if r.level == ERROR else st.warning)(r.message)


def capacity_findings_panel(
    students, units, months, assignments, settings=None, custom_rules=None,
    requirements=None,
) -> None:
    """İleriye dönük risk paneli — Rotasyon Oluştur ve Yıllık Tablo'da.

    Yalnız AKTİF öğrenciler hesaba katılır (pasifler yeni aya atanmaz).
    Tam liste ve "deneme çözümü" Kural Kontrolü ekranındadır.
    """
    from rotasyon.risk import risk_counts

    risks = collect_risks(
        students, units, months, assignments, custom_rules, settings,
        requirements,
    )
    if not risks:
        return
    errs, warns = risk_counts(risks)
    with st.expander(
        f"🔎 Sezon ön-denetimi: {len(risks)} bulgu"
        + (f" ({errs} kritik)" if errs else ""),
        expanded=bool(errs),
    ):
        st.caption(RISK_INTRO)
        show_risks(risks)


def unit_label(u: Unit) -> str:
    """Tablolarda/menülerde gösterilen birim adı: cinsiyet kısıtlı birimler
    gözle kolay ayırt edilsin diye adın yanında '(Kız)' / '(Erkek)' belirtilir.
    Excel dışa aktarımı da aynı biçimi kullanır (Unit.name_with_gender)."""
    return u.name_with_gender


def gender_label(g: str) -> str:
    return GENDER_LABELS.get(g, "Belirsiz")


def groups_in(students: list[Student]) -> list[int]:
    return sorted({s.group for s in students}) or [1, 2]


def replace_month_assignments(
    store: Store,
    group_student_ids: set[str],
    month: str,
    new_mapping: dict[str, str],
    day_notes: dict[str, str] | None = None,
) -> None:
    """Bir grubun bir ayına ait atamaları yenisiyle değiştirir.

    Aynı birimde kalan öğrencinin gün notu korunur (madde 11 notları
    yeniden oluşturmada kaybolmasın).
    """
    day_notes = day_notes or {}
    assignments = store.load_assignments()
    old_notes = {
        a.student_id: a.day_note
        for a in assignments
        if a.month == month and a.student_id in group_student_ids
    }
    old_units = {
        a.student_id: a.unit_id
        for a in assignments
        if a.month == month and a.student_id in group_student_ids
    }
    kept = [
        a
        for a in assignments
        if not (a.month == month and a.student_id in group_student_ids)
    ]
    for sid, uid in new_mapping.items():
        note = day_notes.get(sid, "")
        if not note and old_units.get(sid) == uid:
            note = old_notes.get(sid, "")
        kept.append(
            Assignment(student_id=sid, month=month, unit_id=uid, day_note=note)
        )
    store.save_assignments(kept)


def violations_dataframe(violations):
    import pandas as pd

    def _rule_label(rule_no: int) -> str:
        if rule_no == -1:
            return "Özel Kural"
        if rule_no == 20:
            return "Peş peşe yoğun/hafif"
        if rule_no == 21:
            return "K/E dengesi"
        return f"Madde {rule_no}" if rule_no else "Veri"

    return pd.DataFrame(
        [
            {
                "Düzey": "❌ Hata" if v.severity == "hata" else "⚠️ Uyarı",
                "Kural": _rule_label(v.rule_no),
                "Açıklama": v.message,
            }
            for v in violations
        ]
    )


def _violation_in_scope(v, scope_months, scope_students) -> bool:
    """blocking_errors ile AYNI kapsam mantığı (ama tüm düzeyler için).

    Kapsam içi ("güncel") = yapısal (aysız ve öğrencisiz) VEYA ayı/öğrencisi
    kullanıcının o an çalıştığı kapsamda. Kapsam dışı = "geçmişe dönük".
    """
    if v.student_id and v.student_id in scope_students:
        return True
    if v.month and v.month in scope_months:
        return True
    if not v.month and not v.student_id:
        return True
    return False


def partition_violations(violations, scope_months=None, scope_students=None):
    """İhlalleri (güncel, geçmişe_dönük) olarak ikiye ayırır."""
    sm = scope_months or set()
    ss = scope_students or set()
    current, past = [], []
    for v in violations:
        (current if _violation_in_scope(v, sm, ss) else past).append(v)
    return current, past


def show_past_violations_enabled() -> bool:
    """Kenar çubuğundaki 'geçmişe dönük uyarıları göster' ayarı (varsayılan açık)."""
    return st.session_state.get("show_past_violations", True)


def show_violations_scoped(
    violations, scope_months=None, scope_students=None,
    empty_message="Kural ihlali yok. ✅",
) -> None:
    """Kapsam-duyarlı ihlal gösterimi.

    Ayar AÇIKKEN tüm ihlaller gösterilir (mevcut davranış). KAPALIYKEN yalnız
    güncel kapsamdakiler; geçmişe dönük olanlar gizlenir ve sayısı bilgi
    olarak yazılır. ÖNEMLİ: bu YALNIZ gösterimi etkiler — kaydı hangi hataların
    engellediği (blocking_errors) ayrıca ve TAM ihlal kümesinden hesaplanır,
    bu ayardan etkilenmez.
    """
    if show_past_violations_enabled():
        show_violations(violations, empty_message)
        return
    current, past = partition_violations(violations, scope_months, scope_students)
    if current:
        show_violations(current, empty_message)
    elif past:
        st.info("Güncel kapsamda ihlal yok.")
    else:
        st.success(empty_message)
    if past:
        st.caption(
            f"🕘 {len(past)} geçmişe dönük uyarı gizli — kenar çubuğundaki "
            "“Geçmişe dönük uyarıları göster” ile açabilirsiniz."
        )


def show_violations(violations, empty_message="Kural ihlali yok. ✅") -> None:
    errors = [v for v in violations if v.severity == "hata"]
    warnings = [v for v in violations if v.severity == "uyarı"]
    if not violations:
        st.success(empty_message)
        return
    if errors:
        st.error(f"{len(errors)} kural ihlali (hata) bulundu.")
    if warnings:
        st.warning(f"{len(warnings)} uyarı bulundu.")
    st.dataframe(
        violations_dataframe(violations),
        width="stretch",
        hide_index=True,
    )
