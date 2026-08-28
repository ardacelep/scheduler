"""Uzaktan destek — kimliksiz görüntü, destek kodları, düzeltme paketi.

Bu dosyanın asıl işi GİZLİLİK bekçiliği: dışarı çıkan görüntüde hiçbir
öğrenci adı/okul numarası bulunmamalı. Modele yeni bir alan eklenip beyaz
liste güncellenmezse burası kırılır.
"""
import json

import pytest

from rotasyon.models import Assignment, ClassGroup, Requirement, Student, Unit
from rotasyon.support import (
    FixError,
    STUDENT_PUBLIC,
    WRITABLE,
    anonymize_student,
    apply_fix,
    assign_codes,
    build_fix,
    build_snapshot,
    code_for_index,
    data_revision,
    describe_fix,
    find_by_code,
    label_with_code,
    leaked_names,
    validate_fix,
)

SEASON = "26-27"


def S(ad="KAMİL DENEMEOĞLU", no="123", not_="", group=1):
    return Student(full_name=ad, gender="K", group=group, class_name="A",
                   student_no=no, note=not_)


def _snapshot(students, units=(), codes=None):
    codes = codes if codes is not None else assign_codes(students)
    return build_snapshot(
        SEASON, students, list(units), [], [], [], {"months": ["EYLÜL"]}, [],
        codes,
    )


# ---- destek kodları ----

def test_codes_are_sequential_and_padded():
    students = [S("A"), S("B"), S("C")]
    kodlar = assign_codes(students)
    assert [kodlar[s.id] for s in students] == ["Ö-01", "Ö-02", "Ö-03"]


def test_existing_codes_never_change():
    """Kod değişirse iki taraf farklı kişiden söz eder ve fark etmezler."""
    a, b = S("A"), S("B")
    ilk = assign_codes([a, b])
    c = S("C")
    ikinci = assign_codes([a, b, c], ilk)
    assert ikinci[a.id] == ilk[a.id]
    assert ikinci[b.id] == ilk[b.id]
    assert ikinci[c.id] == "Ö-03"


def test_code_of_a_departed_student_is_not_reused():
    """Ayrılan öğrencinin kodu yeni birine verilmemeli."""
    a, b = S("A"), S("B")
    kodlar = assign_codes([a, b])
    # a listeden çıktı; yeni öğrenci geldi
    yeni = S("YENİ")
    sonra = assign_codes([b, yeni], kodlar)
    assert sonra[yeni.id] not in (kodlar[a.id], kodlar[b.id])


def test_code_survives_a_reordered_roster():
    a, b = S("A"), S("B")
    kodlar = assign_codes([a, b])
    assert assign_codes([b, a], kodlar) == kodlar


def test_label_shows_name_and_code_together():
    s = S("KAMİL DENEMEOĞLU")
    kodlar = assign_codes([s])
    assert label_with_code(s, kodlar) == "KAMİL DENEMEOĞLU · Ö-01"


def test_label_falls_back_when_code_missing():
    s = S("KAMİL")
    assert label_with_code(s, {}) == "KAMİL"


# ---- koddan öğrenci bulma (telefonda okunan kod) ----

@pytest.mark.parametrize("sorgu", ["Ö-07", "ö-07", "07", "7", "o-7", " 7 "])
def test_lookup_tolerates_how_the_code_is_spoken(sorgu):
    """Telefonda sıfır ve tire kaybolur; katı eşleşme kullanıcıyı bırakır."""
    students = [S(f"Ö{i}") for i in range(8)]
    kodlar = assign_codes(students)
    assert find_by_code(students, kodlar, sorgu) is students[6]  # Ö-07


def test_lookup_returns_none_for_unknown_code():
    students = [S("A")]
    assert find_by_code(students, assign_codes(students), "99") is None


def test_lookup_returns_none_for_empty_query():
    students = [S("A")]
    assert find_by_code(students, assign_codes(students), "") is None
    assert find_by_code(students, assign_codes(students), "abc") is None


def test_code_format_is_two_digits():
    assert code_for_index(7) == "Ö-07"
    assert code_for_index(42) == "Ö-42"


# ---- GİZLİLİK: dışarı ne çıkıyor ----

def test_snapshot_contains_no_student_names():
    students = [S("KAMİL DENEMEOĞLU"), S("MEHMET ALİ KAYA")]
    snap = _snapshot(students)
    metin = json.dumps(snap.to_dict(), ensure_ascii=False)
    assert "KAMİL" not in metin and "MEHMET" not in metin


def test_snapshot_contains_no_school_numbers():
    students = [S("A", no="20251234")]
    metin = json.dumps(_snapshot(students).to_dict(), ensure_ascii=False)
    assert "20251234" not in metin


def test_note_text_is_stripped_but_its_existence_is_kept():
    """Not alanına sağlık durumu yazılabiliyor; metin çıkmaz, VARLIĞI çıkar."""
    students = [S("A", not_="diz ameliyatı oldu")]
    snap = _snapshot(students)
    metin = json.dumps(snap.to_dict(), ensure_ascii=False)
    assert "ameliyat" not in metin
    assert snap.students[0]["has_note"] is True


def test_students_without_notes_are_marked_false():
    snap = _snapshot([S("A")])
    assert snap.students[0]["has_note"] is False


def test_leak_check_finds_a_name_that_slipped_through():
    """Son savunma gerçekten çalışıyor mu — kasten sızdırıp bakıyoruz."""
    students = [S("KAMİL DENEMEOĞLU")]
    snap = _snapshot(students)
    assert leaked_names(snap, students) == []
    snap.settings = {"not": "KAMİL DENEMEOĞLU aradı"}
    assert leaked_names(snap, students) == ["KAMİL DENEMEOĞLU"]


def test_anonymised_student_uses_a_whitelist():
    """Kara liste olsaydı modele eklenen yeni alan sessizce sızardı."""
    s = S("KAMİL")
    out = anonymize_student(s, "Ö-01")
    izinli = {"id", "code", "has_note", "banned_unit_ids", *STUDENT_PUBLIC}
    assert set(out) <= izinli
    assert "full_name" not in out and "student_no" not in out and "note" not in out


def test_snapshot_keeps_what_is_needed_to_diagnose():
    """Karşıt kanıt: temizlik yararlı bilgiyi de silmemeli."""
    students = [S("A", group=2)]
    units = [Unit(name="ACİL", group=1, quota=3)]
    snap = _snapshot(students, units)
    assert snap.students[0]["group"] == 2
    assert snap.students[0]["gender"] == "K"
    assert snap.students[0]["class_name"] == "A"
    assert snap.students[0]["code"] == "Ö-01"
    assert snap.units[0]["name"] == "ACİL"  # birim adı kişisel veri değil


def test_snapshot_carries_the_whole_season():
    s = S("A")
    u = Unit(name="ACİL", group=1, quota=1)
    snap = build_snapshot(
        SEASON, [s], [u],
        [Requirement(name="R", scope="tum", unit_keys=["ACİL"])],
        [], [Assignment(student_id=s.id, month="EYLÜL", unit_id=u.id)],
        {"months": ["EYLÜL"]}, [ClassGroup(name="A", color_hex="#FFF")],
        assign_codes([s]),
    )
    d = snap.to_dict()
    assert d["season"] == SEASON
    assert len(d["assignments"]) == 1 and len(d["requirements"]) == 1
    assert d["classes"][0]["name"] == "A"


# ---- düzeltme paketi ----

def test_fix_cannot_touch_student_records():
    """Yönetici elinde isim olmadığı için öğrenci dosyası GÖNDEREMEZ."""
    assert "students" not in WRITABLE
    with pytest.raises(FixError, match="değiştirilemez"):
        build_fix(SEASON, "dene", {"students": []})


def test_fix_requires_a_human_readable_summary():
    """Kullanıcı neyi onayladığını görmeli."""
    with pytest.raises(FixError):
        build_fix(SEASON, "   ", {"units": []})


def test_fix_carries_summary_and_season():
    fix = build_fix(SEASON, "ALÇI kontenjanı 2 yapıldı", {"units": [{"a": 1}]})
    assert fix["season"] == SEASON
    assert fix["summary"] == "ALÇI kontenjanı 2 yapıldı"
    assert fix["id"] and fix["created"]


def test_validate_rejects_a_fix_for_another_season():
    fix = build_fix("BAŞKA", "x", {"units": []})
    with pytest.raises(FixError, match="sezonu için"):
        validate_fix(fix, SEASON)


def test_validate_rejects_an_empty_package():
    with pytest.raises(FixError, match="boş"):
        validate_fix({"files": {}}, SEASON)


def test_validate_rejects_unknown_shape():
    with pytest.raises(FixError):
        validate_fix({"nope": 1}, SEASON)


def test_validate_warns_when_data_changed_since_the_fix_was_made():
    """Bayat düzeltme kullanıcının arada yaptığı işi geri alabilir."""
    fix = build_fix(SEASON, "x", {"units": []}, base_revision="AAA")
    uyarilar = validate_fix(fix, SEASON, current_revision="BBB")
    assert uyarilar and "geri alınabilir" in uyarilar[0]


def test_validate_is_silent_when_data_is_untouched():
    fix = build_fix(SEASON, "x", {"units": []}, base_revision="AAA")
    assert validate_fix(fix, SEASON, current_revision="AAA") == []


def test_describe_lists_what_will_change():
    fix = build_fix(SEASON, "x", {"units": [1, 2], "settings": {"a": 1}})
    metin = " ".join(describe_fix(fix))
    assert "Birimler" in metin and "2 kayıt" in metin
    assert "Ayarlar" in metin


def test_revision_changes_with_the_data():
    assert data_revision({"a": 1}) == data_revision({"a": 1})
    assert data_revision({"a": 1}) != data_revision({"a": 2})


# ---- uygulama: yedek zorunlu ----

def test_apply_writes_files_and_returns_a_backup(tmp_path):
    from rotasyon.store import Store

    store = Store(tmp_path / "seasons" / SEASON)
    store.save_units([Unit(name="ACİL", group=1, quota=1)])
    fix = build_fix(SEASON, "kontenjan 5", {
        "units": [Unit(name="ACİL", group=1, quota=5).to_dict()]
    })
    sonuc = apply_fix(store, fix, SEASON)
    assert sonuc["written"] == ["units"]
    assert sonuc["backup"] and len(sonuc["backup"]) > 100  # zip döndü
    assert store.load_units()[0].quota == 5


def test_apply_backup_holds_the_previous_state(tmp_path):
    """Geri alma yolu kullanıcının elinde olmalı."""
    import zipfile
    from io import BytesIO

    from rotasyon.store import Store

    store = Store(tmp_path / "seasons" / SEASON)
    store.save_units([Unit(name="ESKİ", group=1, quota=1)])
    fix = build_fix(SEASON, "değiştir", {
        "units": [Unit(name="YENİ", group=1, quota=1).to_dict()]
    })
    yedek = apply_fix(store, fix, SEASON)["backup"]
    with zipfile.ZipFile(BytesIO(yedek)) as zf:
        icerik = " ".join(zf.read(n).decode() for n in zf.namelist())
    assert "ESKİ" in icerik


def test_apply_refuses_a_package_for_another_season(tmp_path):
    from rotasyon.store import Store

    store = Store(tmp_path / "seasons" / SEASON)
    store.save_units([])
    with pytest.raises(FixError):
        apply_fix(store, build_fix("BAŞKA", "x", {"units": []}), SEASON)


def test_apply_leaves_students_untouched(tmp_path):
    """Paket öğrenci dosyasına dokunamaz — asıl güvence bu."""
    from rotasyon.store import Store

    store = Store(tmp_path / "seasons" / SEASON)
    ogrenciler = [S("KAMİL DENEMEOĞLU")]
    store.save_students(ogrenciler)
    store.save_units([])
    apply_fix(store, build_fix(SEASON, "x", {"units": [
        Unit(name="ACİL", group=1, quota=1).to_dict()
    ]}), SEASON)
    assert [s.full_name for s in store.load_students()] == ["KAMİL DENEMEOĞLU"]


# ---- belge ile kod aynı şeyi söylüyor mu ----

def test_readme_privacy_claim_matches_the_code():
    """README "kişisel veri makineden çıkmaz" diyordu; destek kanalı bunu
    koşullu hale getirdi. Yanlış bir gizlilik iddiası, hiç iddia
    etmemekten kötüdür — belge kanaldan söz etmeli."""
    from pathlib import Path

    metin = Path("README.md").read_text(encoding="utf-8")
    assert "Uzaktan destek" in metin
    # "hiçbir öğrenci bilgisi harici servise gönderilmez" mutlak iddiası kalkmalı
    assert "hiçbir öğrenci bilgisi harici servise gönderilmez" not in metin


def test_readme_documents_the_writable_whitelist():
    """Belgedeki liste ile koddaki liste ayrışmasın."""
    from pathlib import Path

    metin = Path("README.md").read_text(encoding="utf-8")
    for ad in WRITABLE:
        assert f"`{ad}`" in metin, ad
    assert "Öğrenci kayıtları uzaktan\ndeğiştirilemez" in metin
