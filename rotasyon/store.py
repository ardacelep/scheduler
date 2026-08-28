"""JSON tabanlı kalıcı veri katmanı.

Excel yalnızca içe/dışa aktarım formatıdır; birincil veri kaynağı bu store'dur.
Her kayıt türü ayrı dosyada tutulur, yazımlar atomiktir (tmp + rename) ve her
yazımdan önce mevcut dosyanın .bak yedeği alınır.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable, TypeVar

from .models import (
    Assignment,
    ClassGroup,
    CustomRule,
    Requirement,
    Student,
    Unit,
    DEFAULT_SETTINGS,
    SCOPE_STUDENTS,
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

    # ---- özel kurallar ----
    def load_custom_rules(self) -> list[CustomRule]:
        return self._load_list("rules", CustomRule.from_dict)

    def save_custom_rules(self, rules: list[CustomRule]) -> None:
        self._save_list("rules", rules)

    # ---- gereksinimler (v2 kural modeli) ----
    # Dosya yoksa boş liste döner: v2'yi hiç kullanmamış sezonlar etkilenmez,
    # v1 ekranları bu dosyayı hiç okumaz.
    def load_requirements(self) -> list[Requirement]:
        return self._load_list("requirements", Requirement.from_dict)

    def save_requirements(self, requirements: list[Requirement]) -> None:
        self._save_list("requirements", requirements)

    # ---- uzaktan destek ----
    # Destek kodları (öğrenci_id -> "Ö-07") sezonun yanında durur ve BİR KEZ
    # verilir: kod değişirse geliştirici ile kullanıcı telefonda farklı
    # kişiden söz eder ve bunu fark etmezler.
    def load_support_codes(self) -> dict:
        return self._read("support_codes", {}) or {}

    def save_support_codes(self, codes: dict) -> None:
        self._write("support_codes", codes)

    # Uygulanmış düzeltmelerin id'leri — aynı paket ikinci kez teklif
    # edilmesin (yöneticinin dosyayı silmesine bağlı kalmaz).
    def load_support_applied(self) -> list[str]:
        return list(self._read("support_applied", []) or [])

    def mark_support_applied(self, fix_id: str) -> None:
        kayit = self.load_support_applied()
        if fix_id and fix_id not in kayit:
            kayit.append(fix_id)
            self._write("support_applied", kayit)

    def raw_season_payload(self) -> dict:
        """Sezonun ham JSON içeriği — damga hesabı ve düzeltme uygulaması için."""
        return {
            ad: self._read(ad, [] if ad != "settings" else {})
            for ad in ("units", "requirements", "custom_rules", "assignments",
                       "settings")
        }

    def write_raw(self, name: str, payload) -> None:
        """Ham JSON yazımı (yedek + atomik). Yalnız destek akışı kullanır."""
        self._write(name, payload)

    # ---- toplu taslak (kalıcı) ----
    # Toplu üretim dakikalar sürebilir; sonucu yalnız oturum belleğinde
    # tutmak sayfa yenilemede/uygulama kapanmasında emeği çöpe atar. Taslak
    # onaylanana ya da silinene kadar diskte bekler; içindeki fingerprint
    # veriyle karşılaştırılır, veri değiştiyse taslak bayattır ve atılır.
    def save_bulk_draft(self, payload: dict) -> None:
        self._write("draft_bulk", payload)

    def load_bulk_draft(self) -> dict | None:
        return self._read("draft_bulk", None)

    def clear_bulk_draft(self) -> None:
        for suffix in (".json", ".json.bak"):
            p = self.data_dir / f"draft_bulk{suffix}"
            if p.exists():
                p.unlink()

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


# ======================= SEZON YÖNETİMİ =======================

_LEGACY_FILES = ("students", "units", "classes", "assignments", "settings")


def _safe_dir_name(name: str) -> str:
    """Sezon adını dosya sistemi için güvenli klasör adına çevirir."""
    cleaned = "".join(c if c.isalnum() or c in "-_ ." else "_" for c in name)
    return cleaned.strip() or "sezon"


class SeasonManager:
    """Birden fazla öğretim dönemi (sezon) yönetir.

    Yerleşim:
        data/app.json                  -> {"active_season": "2025-2026"}
        data/seasons/<sezon adı>/*.json -> o sezonun Store verisi

    Her sezonun öğrenci/birim/sınıf/atama verisi tamamen bağımsızdır;
    yeni sezon açılırken birim ve sınıflar istenirse önceki sezondan
    kopyalanır (öğrenci ve atamalar asla kopyalanmaz).
    """

    def __init__(self, root: str | Path = "data"):
        self.root = Path(root)
        self.seasons_dir = self.root / "seasons"
        self.root.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy()

    # ---- app.json ----
    def _app_path(self) -> Path:
        return self.root / "app.json"

    def _read_app(self) -> dict:
        if self._app_path().exists():
            with open(self._app_path(), encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _write_app(self, payload: dict) -> None:
        tmp = self._app_path().with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self._app_path())

    # ---- migrasyon ----
    def _migrate_legacy(self) -> None:
        """Eski tek-sezon yerleşimini (data/*.json) sezon klasörüne taşır."""
        legacy = [
            self.root / f"{name}.json"
            for name in _LEGACY_FILES
            if (self.root / f"{name}.json").exists()
        ]
        if not legacy:
            return
        target = self.seasons_dir / "Önceki Dönem"
        target.mkdir(parents=True, exist_ok=True)
        for p in legacy:
            shutil.move(str(p), target / p.name)
            bak = p.with_suffix(".json.bak")
            if bak.exists():
                shutil.move(str(bak), target / bak.name)
        app = self._read_app()
        app.setdefault("active_season", "Önceki Dönem")
        self._write_app(app)

    # ---- sezonlar ----
    def list_seasons(self) -> list[str]:
        if not self.seasons_dir.exists():
            return []
        return sorted(
            p.name for p in self.seasons_dir.iterdir() if p.is_dir()
        )

    def active_season(self) -> str | None:
        name = self._read_app().get("active_season")
        if name and (self.seasons_dir / name).is_dir():
            return name
        seasons = self.list_seasons()
        return seasons[-1] if seasons else None

    def set_active(self, name: str) -> None:
        if name not in self.list_seasons():
            raise ValueError(f"Sezon bulunamadı: {name}")
        app = self._read_app()
        app["active_season"] = name
        self._write_app(app)

    def create(
        self,
        name: str,
        copy_units_from: str | None = None,
    ) -> Store:
        """Yeni sezon açar; istenirse birim + sınıf tanımlarını kopyalar."""
        dir_name = _safe_dir_name(name)
        target = self.seasons_dir / dir_name
        if target.exists():
            raise ValueError(f"Bu adla bir sezon zaten var: {dir_name}")
        target.mkdir(parents=True)
        store = Store(target)
        if copy_units_from:
            source = self.store(copy_units_from)
            store.save_units(source.load_units())
            store.save_classes(source.load_classes())
            store.save_settings(source.load_settings())
            # Gereksinimler birimlere ADA göre bağlı olduğundan yeni sezona
            # taşınabilir. Tek istisna: tek tek öğrenci seçilmiş gereksinimler
            # — öğrenciler kopyalanmadığı için o id'ler yeni sezonda karşılıksız
            # kalırdı, bu yüzden atlanır.
            carried = [
                r for r in source.load_requirements() if r.scope != SCOPE_STUDENTS
            ]
            if carried:
                store.save_requirements(carried)
        self.set_active(dir_name)
        return store

    def delete(self, name: str) -> None:
        """Sezonu siler — kalıcı silme yerine data/trash/ altına taşır.

        Yanlışlıkla silmede veri kurtarılabilsin diye klasör çöpe taşınır;
        aktif sezon silinirse kalan son sezon aktif yapılır.
        """
        if name not in self.list_seasons():
            raise ValueError(f"Sezon bulunamadı: {name}")
        trash = self.root / "trash"
        trash.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.move(
            str(self.seasons_dir / name), trash / f"{name}_{stamp}"
        )
        app = self._read_app()
        if app.get("active_season") == name:
            seasons = self.list_seasons()
            if seasons:
                app["active_season"] = seasons[-1]
            else:
                app.pop("active_season", None)
            self._write_app(app)

    def store(self, name: str | None = None) -> Store:
        """Verilen (veya aktif) sezonun Store'unu döndürür."""
        name = name or self.active_season()
        if name is None:
            # hiç sezon yok: ilk sezonu aç
            return self.create("Yeni Dönem")
        return Store(self.seasons_dir / name)
