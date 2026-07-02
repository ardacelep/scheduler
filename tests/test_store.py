from rotasyon.models import ClassGroup, Student, Unit
from rotasyon.store import Store


def test_roundtrip(tmp_path, small_world):
    students, units, classes = small_world
    store = Store(tmp_path)
    store.save_students(students)
    store.save_units(units)
    store.save_classes(classes)

    assert [s.full_name for s in store.load_students()] == [
        s.full_name for s in students
    ]
    assert [u.name for u in store.load_units()] == [u.name for u in units]
    assert store.load_classes()[0].color_hex == "#FFFF00"


def test_rule12_unit_quota_is_editable(tmp_path, small_world):
    """Madde 12: birim ve kontenjan düzenlenebilir, kalıcıdır."""
    _, units, _ = small_world
    store = Store(tmp_path)
    store.save_units(units)

    loaded = store.load_units()
    loaded[0].quota = 5
    loaded.append(Unit(name="YENİ BİRİM", group=1, quota=2))
    store.save_units(loaded)

    again = store.load_units()
    assert again[0].quota == 5
    assert again[-1].name == "YENİ BİRİM"

    # silme
    store.save_units([u for u in again if u.name != "YENİ BİRİM"])
    assert all(u.name != "YENİ BİRİM" for u in store.load_units())


def test_rule13_classes_are_user_defined(tmp_path):
    """Madde 13: sınıf sayısı/adı sabit değil; renk atanır (madde 14 verisi)."""
    store = Store(tmp_path)
    classes = [ClassGroup(name=n, color_hex=c) for n, c in
               [("A", "#FFFF00"), ("B", "#C6DEB5"), ("EBELIK-1", "#00FFFF")]]
    store.save_classes(classes)
    loaded = store.load_classes()
    assert len(loaded) == 3
    assert loaded[2].name == "EBELIK-1"


def test_rule10_note_field_persists(tmp_path):
    """Madde 10: özel öğrenci notu saklanır (kural motorunu etkilemez)."""
    store = Store(tmp_path)
    s = Student(full_name="Özel Öğrenci", gender="K", group=1,
                note="raporlu — pazartesi gelemiyor")
    store.save_students([s])
    assert store.load_students()[0].note == "raporlu — pazartesi gelemiyor"


def test_settings_merge_with_defaults(tmp_path):
    store = Store(tmp_path)
    settings = store.load_settings()
    settings["solver"]["weights"]["repeat_pair"] = 99
    store.save_settings(settings)
    loaded = store.load_settings()
    assert loaded["solver"]["weights"]["repeat_pair"] == 99
    # varsayılanda olan diğer anahtarlar kaybolmaz
    assert "pool_balance" in loaded["solver"]["weights"]
    assert loaded["months"][0] == "EYLÜL"

def test_backup_created_on_overwrite(tmp_path):
    store = Store(tmp_path)
    s = Student(full_name="X", gender="K", group=1)
    store.save_students([s])
    store.save_students([s])
    assert (tmp_path / "students.json.bak").exists()
