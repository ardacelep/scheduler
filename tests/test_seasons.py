"""Sezon (öğretim dönemi) yönetimi testleri."""
import json

from rotasyon.models import ClassGroup, Student, Unit, Assignment
from rotasyon.store import SeasonManager, Store


def test_create_and_switch_seasons(tmp_path):
    m = SeasonManager(tmp_path)
    m.create("2024-2025")
    m.create("2025-2026")
    assert m.list_seasons() == ["2024-2025", "2025-2026"]
    assert m.active_season() == "2025-2026"  # son oluşturulan aktif
    m.set_active("2024-2025")
    assert m.active_season() == "2024-2025"


def test_seasons_are_isolated(tmp_path):
    m = SeasonManager(tmp_path)
    s1 = m.create("2024-2025")
    s1.save_students([Student(full_name="Eski Öğrenci", gender="K", group=1)])
    s2 = m.create("2025-2026")
    assert s2.load_students() == []  # yeni sezon boş
    assert len(m.store("2024-2025").load_students()) == 1


def test_create_with_unit_copy(tmp_path):
    m = SeasonManager(tmp_path)
    s1 = m.create("2024-2025")
    s1.save_units([Unit(name="ACİL", group=1, quota=2)])
    s1.save_classes([ClassGroup(name="12/A", color_hex="#FFFF00")])
    s1.save_students([Student(full_name="X", gender="K", group=1)])
    s1.save_assignments(
        [Assignment(student_id="x", month="EYLÜL", unit_id="u")]
    )

    s2 = m.create("2025-2026", copy_units_from="2024-2025")
    assert [u.name for u in s2.load_units()] == ["ACİL"]
    assert [c.name for c in s2.load_classes()] == ["12/A"]
    # öğrenci ve atamalar ASLA kopyalanmaz
    assert s2.load_students() == []
    assert s2.load_assignments() == []


def test_duplicate_season_name_rejected(tmp_path):
    m = SeasonManager(tmp_path)
    m.create("2024-2025")
    try:
        m.create("2024-2025")
        assert False, "aynı adla ikinci sezon açılamamalı"
    except ValueError:
        pass


def test_legacy_flat_layout_migrates(tmp_path):
    """Eski tek-sezon düzeni (data/*.json) otomatik sezona taşınır."""
    legacy_store = Store(tmp_path)
    legacy_store.save_students(
        [Student(full_name="Göç Eden", gender="E", group=1)]
    )
    legacy_store.save_units([Unit(name="DİŞ", group=1, quota=4)])

    m = SeasonManager(tmp_path)  # migrasyon burada tetiklenir
    assert m.list_seasons() == ["Önceki Dönem"]
    assert m.active_season() == "Önceki Dönem"
    store = m.store()
    assert store.load_students()[0].full_name == "Göç Eden"
    assert store.load_units()[0].name == "DİŞ"
    # kökte eski dosya kalmaz
    assert not (tmp_path / "students.json").exists()


def test_store_creates_first_season_when_empty(tmp_path):
    m = SeasonManager(tmp_path)
    store = m.store()
    assert m.active_season() is not None
    store.save_students([Student(full_name="İlk", gender="K", group=1)])
    assert len(m.store().load_students()) == 1
