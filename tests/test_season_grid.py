"""Yıllık Tablo ekranının saf yardımcıları (Excel benzeri düzenlenebilir ızgara)."""
from rotasyon.models import DEFAULT_MONTHS, Unit
from rotasyon.store import Store
from ui.season_grid import BLANK, _labels_for_group, _save
from conftest import make_assignment


def test_labels_include_active_and_historical_units(small_world):
    students, units, _ = small_world
    group_ids = {s.id for s in students}
    # geçmişte kullanılmış ama artık PASİF birim de listeye girmeli
    old = Unit(name="ESKİ BİRİM", group=1, quota=0, active=False)
    units = units + [old]
    assignments = [make_assignment(students[0], old, "EYLÜL")]
    labels = _labels_for_group(1, units, assignments, group_ids)
    assert "DİŞ" in labels            # aktif
    assert "ESKİ BİRİM" in labels     # geçmişte kullanılmış (pasif)
    # cinsiyet varyantları ayrı etiketlerle
    assert "FTR.ÜNİT k" in labels and "FTR.ÜNİT e" in labels


def test_save_only_writes_changed_months(tmp_path, small_world):
    students, units, _ = small_world
    dis = next(u for u in units if u.name == "DİŞ")
    cerr = next(u for u in units if u.name == "1.KAT CERR.")
    store = Store(tmp_path)
    store.save_students(students)
    store.save_units(units)
    # EYLÜL kayıtlı: s0→DİŞ
    store.save_assignments([make_assignment(students[0], dis, "EYLÜL")])

    group_students = [s for s in students if s.group == 1]
    group_ids = {s.id for s in group_students}
    label_to_id = {"DİŞ": dis.id, "1.KAT CERR.": cerr.id}
    saved = {(students[0].id, "EYLÜL"): "DİŞ"}
    # çalışma: EYLÜL değişmedi, EKİM'de s0→1.KAT CERR. eklendi
    work = {(s.id, m): BLANK for s in group_students for m in DEFAULT_MONTHS}
    work[(students[0].id, "EYLÜL")] = "DİŞ"
    work[(students[0].id, "EKİM")] = "1.KAT CERR."

    _save(store, DEFAULT_MONTHS, group_ids, group_students, work, saved, label_to_id)

    after = store.load_assignments()
    eylul = [a for a in after if a.month == "EYLÜL"]
    ekim = [a for a in after if a.month == "EKİM"]
    assert len(eylul) == 1 and eylul[0].unit_id == dis.id  # korundu
    assert len(ekim) == 1 and ekim[0].unit_id == cerr.id   # yeni yazıldı


def test_save_can_clear_a_cell(tmp_path, small_world):
    """Bir hücreyi BLANK yapmak o ayın o öğrenci atamasını siler."""
    students, units, _ = small_world
    dis = next(u for u in units if u.name == "DİŞ")
    store = Store(tmp_path)
    store.save_students(students)
    store.save_units(units)
    store.save_assignments([make_assignment(students[0], dis, "EYLÜL")])

    group_students = [s for s in students if s.group == 1]
    group_ids = {s.id for s in group_students}
    label_to_id = {"DİŞ": dis.id}
    saved = {(students[0].id, "EYLÜL"): "DİŞ"}
    work = {(s.id, m): BLANK for s in group_students for m in DEFAULT_MONTHS}
    # EYLÜL'ü boşalt (BLANK)

    _save(store, DEFAULT_MONTHS, group_ids, group_students, work, saved, label_to_id)
    assert [a for a in store.load_assignments() if a.month == "EYLÜL"] == []
