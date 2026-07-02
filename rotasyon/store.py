"""JSON tabanlı kalıcı veri katmanı.

Excel yalnızca içe/dışa aktarım formatıdır; birincil veri kaynağı bu store'dur.
Her kayıt türü ayrı dosyada tutulur, yazımlar atomiktir (tmp + rename) ve her
yazımdan önce mevcut dosyanın .bak yedeği alınır.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Callable, TypeVar

from .models import (
    Assignment,
    ClassGroup,
    Student,
    Unit,
    DEFAULT_SETTINGS,
)

T = TypeVar("T")


class Store:
    def __init__(self, data_dir: str | Path = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # ---- düşük seviye ----
    def _path(self, name: str) -> Path:
        return self.data_dir / f"{name}.json"

    def _read(self, name: str, default):
        p = self._path(name)
        if not p.exists():
            return default
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def _write(self, name: str, payload) -> None:
        p = self._path(name)
        if p.exists():
            shutil.copy2(p, p.with_suffix(".json.bak"))
        tmp = p.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)

    def _load_list(self, name: str, factory: Callable[[dict], T]) -> list[T]:
        return [factory(d) for d in self._read(name, [])]

    def _save_list(self, name: str, items) -> None:
        self._write(name, [it.to_dict() for it in items])

    # ---- öğrenciler ----
    def load_students(self) -> list[Student]:
        return self._load_list("students", Student.from_dict)

    def save_students(self, students: list[Student]) -> None:
        self._save_list("students", students)

    # ---- birimler ----
    def load_units(self) -> list[Unit]:
        return self._load_list("units", Unit.from_dict)

    def save_units(self, units: list[Unit]) -> None:
        self._save_list("units", units)

    # ---- sınıflar ----
    def load_classes(self) -> list[ClassGroup]:
        return self._load_list("classes", ClassGroup.from_dict)

    def save_classes(self, classes: list[ClassGroup]) -> None:
        self._save_list("classes", classes)

    # ---- atamalar ----
    def load_assignments(self) -> list[Assignment]:
        return self._load_list("assignments", Assignment.from_dict)

    def save_assignments(self, assignments: list[Assignment]) -> None:
        self._save_list("assignments", assignments)

    # ---- ayarlar ----
    def load_settings(self) -> dict:
        settings = self._read("settings", None)
        if settings is None:
            return json.loads(json.dumps(DEFAULT_SETTINGS))
        # Yeni eklenen varsayılan anahtarları eski dosyalara da tanıt
        merged = json.loads(json.dumps(DEFAULT_SETTINGS))
        _deep_update(merged, settings)
        return merged

    def save_settings(self, settings: dict) -> None:
        self._write("settings", settings)


def _deep_update(base: dict, override: dict) -> None:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v
