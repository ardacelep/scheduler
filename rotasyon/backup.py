"""Yedekleme ve geri yükleme.

Teknik bilgisi olmayan kullanıcı için hayati: veri `data/` klasöründe
JSON olarak durur, ama kullanıcı o klasörü ne bulur ne de kopyalar.
Bu modül tek düğmeyle indirilebilen bir .zip üretir ve aynı .zip'ten
geri yükler.

Zip düzeni (içine `yedek.json` künyesi konur):

    sezon yedeği:  yedek.json + sezon/<dosyalar>.json
    tam yedek:     yedek.json + seasons/<sezon adı>/<dosyalar>.json

Elle zip'lenmiş bir sezon klasörü de (künyesiz, düz JSON'lar) kabul
edilir — kullanıcı kendi kopyaladığı klasörü yükleyebilsin diye.
"""
from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

MANIFEST = "yedek.json"
FORMAT_VERSION = 1
SEASON_PREFIX = "sezon/"
FULL_PREFIX = "seasons/"

# Yedeğe giren veri dosyaları. Türetilmiş/geçici olanlar (.bak, .tmp,
# draft_bulk, günlük, kilit dosyası) dışarıda kalır.
#
# Store'a yeni bir dosya eklendiğinde BURAYA da eklenmeli; yoksa sessizce
# yedek dışı kalır. Bir kez oldu: v2 gereksinimleri (requirements.json)
# yedeğe hiç girmiyordu, geri yüklenen sezon gereksinimsiz açılıp eski branş
# yoluna düşüyordu. tests/test_backup.py bu listeyi Store'la karşılaştırır.
DATA_FILES = (
    "students.json",
    "units.json",
    "classes.json",
    "assignments.json",
    "rules.json",
    "requirements.json",
    "settings.json",
    # destek kodları geri yüklemede DEĞİŞMEMELİ: telefonda "Ö-07" diye
    # konuşulan öğrenci aynı kalmalı
    "support_codes.json",
    "support_applied.json",
)
# Bilerek yedek dışı: türetilmiş/geçici olanlar.
NOT_BACKED_UP = ("draft_bulk.json",)


class BackupError(Exception):
    """Geri yükleme yapılamadı — kullanıcıya gösterilecek Türkçe mesaj."""


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M")


def _slug(name: str) -> str:
    """Dosya adına konabilir sade karşılık ('2026-2027', 'Onceki-Donem')."""
    table = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name.translate(table))
    return cleaned.strip("-") or "sezon"


def backup_filename(season: str | None) -> str:
    if season:
        return f"staj-rotasyonu-yedek_{_slug(season)}_{_stamp()}.zip"
    return f"staj-rotasyonu-yedek_TUM-SEZONLAR_{_stamp()}.zip"


def _season_files(season_dir: Path) -> list[Path]:
    return [season_dir / name for name in DATA_FILES if (season_dir / name).is_file()]


def season_backup_bytes(season_dir: Path, season_name: str) -> bytes:
    """Tek sezonun yedeği."""
    season_dir = Path(season_dir)
    files = _season_files(season_dir)
    if not files:
        raise BackupError(f"'{season_name}' sezonunda yedeklenecek veri yok.")
    manifest = {
        "tur": "sezon",
        "sezon": season_name,
        "tarih": datetime.now().isoformat(timespec="seconds"),
        "surum": FORMAT_VERSION,
        "uygulama": "Staj Rotasyonu",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
        for path in files:
            zf.write(path, SEASON_PREFIX + path.name)
    return buffer.getvalue()


def full_backup_bytes(root: Path, seasons: list[str]) -> bytes:
    """Tüm sezonların tek dosyada yedeği."""
    root = Path(root)
    manifest = {
        "tur": "tam",
        "sezonlar": list(seasons),
        "tarih": datetime.now().isoformat(timespec="seconds"),
        "surum": FORMAT_VERSION,
        "uygulama": "Staj Rotasyonu",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
        for season in seasons:
            for path in _season_files(root / "seasons" / season):
                zf.write(path, f"{FULL_PREFIX}{season}/{path.name}")
    return buffer.getvalue()


# ---------------------------------------------------------------- okuma
def _open(data: bytes) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise BackupError(
            "Bu dosya geçerli bir yedek (.zip) değil."
        ) from exc


def _collect(zf: zipfile.ZipFile) -> dict[str, dict[str, str]]:
    """Zip içindeki sezonları {sezon adı: {dosya adı: zip yolu}} olarak çıkarır.

    Künyesiz (elle zip'lenmiş) dosyalar da desteklenir: tanınan JSON'lar
    hangi klasördeyse o klasör bir sezon sayılır.
    """
    found: dict[str, dict[str, str]] = {}
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = Path(info.filename).name
        if name not in DATA_FILES:
            continue
        parts = Path(info.filename).parts
        if len(parts) >= 3 and parts[0] == "seasons":
            season = parts[1]
        elif len(parts) >= 2 and parts[0] == "sezon":
            season = ""  # tek sezon yedeği: adı künyeden/kullanıcıdan gelir
        elif len(parts) == 1:
            season = ""  # düz zip
        else:
            season = parts[-2]
        found.setdefault(season, {})[name] = info.filename
    return found


def inspect_backup(data: bytes) -> dict:
    """Yedeğin künyesi + içindeki sezonlar. Geri yüklemeden önce gösterilir."""
    with _open(data) as zf:
        manifest = {}
        if MANIFEST in zf.namelist():
            try:
                manifest = json.loads(zf.read(MANIFEST).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                manifest = {}
        found = _collect(zf)
        if not found:
            raise BackupError(
                "Zip içinde tanınan veri dosyası yok "
                "(students.json, units.json ...). Yanlış dosya olabilir."
            )
        seasons = []
        for season, files in found.items():
            seasons.append(
                {
                    "ad": season or manifest.get("sezon", "") or "Yedekten Gelen",
                    "dosyalar": sorted(files),
                    "kayit": _count_records(zf, files),
                }
            )
    return {
        "tur": manifest.get("tur", "bilinmiyor"),
        "tarih": manifest.get("tarih", ""),
        "sezonlar": sorted(seasons, key=lambda s: s["ad"]),
    }


def _count_records(zf: zipfile.ZipFile, files: dict[str, str]) -> dict[str, int]:
    counts = {}
    for name in ("students.json", "units.json", "assignments.json"):
        path = files.get(name)
        if not path:
            continue
        try:
            payload = json.loads(zf.read(path).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(payload, list):
            counts[name.removesuffix(".json")] = len(payload)
    return counts


def unique_season_name(existing: list[str], wanted: str) -> str:
    """Var olan adla çakışmayan bir sezon adı üretir ('X', 'X (2)', ...)."""
    name = wanted.strip() or "Yedekten Gelen"
    if name not in existing:
        return name
    for i in range(2, 100):
        candidate = f"{name} ({i})"
        if candidate not in existing:
            return candidate
    return f"{name} ({_stamp()})"


def restore_into(data: bytes, target_root: Path, existing: list[str],
                 rename_to: str | None = None) -> list[str]:
    """Yedekteki sezonları `target_root/seasons/` altına YENİ sezon olarak açar.

    Var olan sezonların üzerine asla yazmaz: ad çakışırsa "(2)" eklenir.
    Dönüş: oluşturulan sezon adları.
    """
    target_root = Path(target_root)
    with _open(data) as zf:
        found = _collect(zf)
        if not found:
            raise BackupError(
                "Zip içinde tanınan veri dosyası yok. Yanlış dosya olabilir."
            )
        manifest_name = ""
        if MANIFEST in zf.namelist():
            try:
                manifest_name = json.loads(
                    zf.read(MANIFEST).decode("utf-8")
                ).get("sezon", "")
            except (ValueError, UnicodeDecodeError):
                manifest_name = ""

        created: list[str] = []
        taken = list(existing)
        for season, files in sorted(found.items()):
            wanted = rename_to or season or manifest_name or "Yedekten Gelen"
            name = unique_season_name(taken, _safe_name(wanted))
            taken.append(name)
            season_dir = target_root / "seasons" / name
            season_dir.mkdir(parents=True, exist_ok=True)
            for file_name, zip_path in files.items():
                payload = zf.read(zip_path)
                _validate_json(payload, file_name)
                (season_dir / file_name).write_bytes(payload)
            created.append(name)
    return created


def _safe_name(name: str) -> str:
    """SeasonManager ile aynı klasör adı kuralı."""
    cleaned = "".join(c if c.isalnum() or c in "-_ ." else "_" for c in name)
    return cleaned.strip() or "sezon"


def _validate_json(payload: bytes, file_name: str) -> None:
    try:
        json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise BackupError(
            f"Yedekteki '{file_name}' dosyası bozuk görünüyor, geri yüklenemedi."
        ) from exc
