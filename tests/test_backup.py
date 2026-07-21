"""Yedekleme / geri yükleme round-trip'i.

Teknik olmayan kullanıcının tek güvencesi bu akış: yedek alınabilmeli,
aynı dosyadan geri yüklenebilmeli ve geri yükleme MEVCUT sezonların
üzerine ASLA yazmamalı.
"""
import io
import json
import zipfile

import pytest

from rotasyon.backup import (
    BackupError,
    backup_filename,
    full_backup_bytes,
    inspect_backup,
    restore_into,
    season_backup_bytes,
    unique_season_name,
)
from rotasyon.models import Assignment, ClassGroup, Student, Unit
from rotasyon.store import SeasonManager


@pytest.fixture
def manager(tmp_path):
    m = SeasonManager(tmp_path / "data")
    store = m.create("2026-2027")
    store.save_students(
        [
            Student(id="s1", full_name="Ayşe Yılmaz", gender="K", group=1),
            Student(id="s2", full_name="Efehan Demir", gender="E", group=1),
        ]
    )
    store.save_units([Unit(id="u1", name="DİŞ", quota=2, group=1)])
    store.save_classes([ClassGroup(name="9-A", color_hex="#FFAA00")])
    store.save_assignments(
        [Assignment(student_id="s1", month="EYLÜL", unit_id="u1")]
    )
    return m


def test_season_backup_roundtrip(manager, tmp_path):
    store = manager.store("2026-2027")
    data = season_backup_bytes(store.data_dir, "2026-2027")

    info = inspect_backup(data)
    assert info["tur"] == "sezon"
    assert len(info["sezonlar"]) == 1
    assert info["sezonlar"][0]["kayit"]["students"] == 2

    created = restore_into(data, manager.root, manager.list_seasons())
    assert created == ["2026-2027 (2)"]  # üzerine yazmadı, yenisini açtı
    restored = manager.store(created[0])
    assert [s.full_name for s in restored.load_students()] == [
        "Ayşe Yılmaz",
        "Efehan Demir",
    ]
    assert len(restored.load_assignments()) == 1
    assert restored.load_units()[0].name == "DİŞ"
    # kaynak sezon dokunulmadan duruyor
    assert len(manager.store("2026-2027").load_students()) == 2


def test_restore_does_not_touch_existing_seasons(manager):
    data = season_backup_bytes(manager.store("2026-2027").data_dir, "2026-2027")
    # kaynak sezonu boşalt: geri yükleme onu geri getirmemeli (yeni sezon açar)
    manager.store("2026-2027").save_students([])
    restore_into(data, manager.root, manager.list_seasons())
    assert manager.store("2026-2027").load_students() == []


def test_restore_with_custom_name(manager):
    data = season_backup_bytes(manager.store("2026-2027").data_dir, "2026-2027")
    created = restore_into(
        data, manager.root, manager.list_seasons(), rename_to="Yedek Deneme"
    )
    assert created == ["Yedek Deneme"]
    assert "Yedek Deneme" in manager.list_seasons()


def test_full_backup_covers_all_seasons(manager):
    manager.create("2027-2028").save_students(
        [Student(id="x", full_name="Test Kişi", gender="K", group=2)]
    )
    seasons = manager.list_seasons()
    data = full_backup_bytes(manager.root, seasons)

    info = inspect_backup(data)
    assert info["tur"] == "tam"
    assert [s["ad"] for s in info["sezonlar"]] == seasons

    created = restore_into(data, manager.root, seasons)
    assert len(created) == 2
    assert all(name.endswith("(2)") for name in created)


def test_plain_zip_without_manifest_is_accepted(manager):
    """Kullanıcının elle zip'lediği sezon klasörü de geri yüklenebilir."""
    store = manager.store("2026-2027")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for path in sorted(store.data_dir.glob("*.json")):
            zf.write(path, path.name)
    created = restore_into(
        buffer.getvalue(), manager.root, manager.list_seasons(),
        rename_to="Elle Zip",
    )
    assert manager.store(created[0]).load_students()[0].full_name == "Ayşe Yılmaz"


def test_rejects_non_backup_files(manager):
    with pytest.raises(BackupError):
        inspect_backup(b"bu bir zip degil")
    empty = io.BytesIO()
    with zipfile.ZipFile(empty, "w") as zf:
        zf.writestr("okuma.txt", "merhaba")
    with pytest.raises(BackupError):
        inspect_backup(empty.getvalue())


def test_rejects_corrupt_json_inside_backup(manager):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("yedek.json", json.dumps({"tur": "sezon", "sezon": "X"}))
        zf.writestr("sezon/students.json", "{bozuk")
    with pytest.raises(BackupError):
        restore_into(buffer.getvalue(), manager.root, manager.list_seasons())


def test_backup_excludes_derived_files(manager):
    store = manager.store("2026-2027")
    store.save_bulk_draft({"gecici": True})
    data = season_backup_bytes(store.data_dir, "2026-2027")
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert not any("draft_bulk" in n or n.endswith(".bak") for n in names)


def test_backup_filename_is_filesystem_safe():
    assert backup_filename("2026-2027").startswith("staj-rotasyonu-yedek_2026-2027_")
    assert " " not in backup_filename("Önceki Dönem")
    assert "TUM-SEZONLAR" in backup_filename(None)


def test_unique_season_name():
    assert unique_season_name([], "A") == "A"
    assert unique_season_name(["A"], "A") == "A (2)"
    assert unique_season_name(["A", "A (2)"], "A") == "A (3)"
