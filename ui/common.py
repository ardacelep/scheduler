"""Ekranların ortak yardımcıları: store erişimi, seed yükleme, etiketler."""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from rotasyon.catalog import catalog_available, load_default_units
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
    """Yeni sezonu açar ve birimleri seçilen kaynaktan doldurur."""
    if source == UNITS_CATALOG:
        store = manager.create(name)
        store.save_units(load_default_units())
        return store
    if source == UNITS_EMPTY:
        return manager.create(name)
    return manager.create(name, copy_units_from=source)


def unit_label(u: Unit) -> str:
    """Kullanıcıya gösterilen birim adı: cinsiyet kısıtı ekiyle."""
    return u.display_name


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
        use_container_width=True,
        hide_index=True,
    )
