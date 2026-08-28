"""Uçtan uca destek turu: gönder → yönetici düzeltsin → onayla → uygula.

Ağ yok: "uzak depo" yerel bir bare repo. Bu dosya parçaların birbirine
gerçekten bağlandığını doğrular — parça parça geçen testler, aradaki bir
kopukluğu göstermez (gereksinimler bir kez tam da böyle bağlanmamıştı).
"""
import json
import subprocess

import pytest

from rotasyon.models import Student, Unit
from rotasyon.store import Store
from rotasyon.support import (
    apply_fix,
    assign_codes,
    build_fix,
    build_snapshot,
    data_revision,
    find_by_code,
)
from rotasyon.support_sync import (
    SupportConfig,
    pending_fixes,
    push_snapshot,
    save_config,
)

SEASON = "26-27"


def _git(args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )


@pytest.fixture
def kurulum(tmp_path):
    """Hastane makinesi + uzak depo."""
    uzak = tmp_path / "uzak.git"
    _git(["init", "--bare", "--initial-branch=main", str(uzak)], tmp_path)
    data = tmp_path / "data"
    (data / "seasons" / SEASON).mkdir(parents=True)
    save_config(data, SupportConfig(repo=str(uzak), enabled=True))
    store = Store(data / "seasons" / SEASON)
    store.save_students([
        Student(full_name="KAMİL DENEMEOĞLU", gender="K", group=1,
                class_name="A", student_no="1001"),
        Student(full_name="MEHMET ALİ KAYA", gender="E", group=1,
                class_name="A", student_no="1002"),
    ])
    store.save_units([Unit(name="ACİL", group=1, quota=1)])
    return data, uzak, store


def _push(data, store):
    students = store.load_students()
    codes = assign_codes(students, store.load_support_codes())
    store.save_support_codes(codes)
    snap = build_snapshot(
        SEASON, students, store.load_units(), store.load_requirements(),
        store.load_custom_rules(), store.load_assignments(),
        store.load_settings(), store.load_classes(), codes,
        revision=data_revision(store.raw_season_payload()),
    )
    return push_snapshot(data, SEASON, snap, students=students), codes


def _admin_reads(uzak, tmp_path, name="admin"):
    """Yöneticinin gördüğü şey."""
    calisma = tmp_path / name
    _git(["clone", str(uzak), str(calisma)], tmp_path)
    _git(["config", "user.email", "a@b"], calisma)
    _git(["config", "user.name", "admin"], calisma)
    p = calisma / "snapshots" / f"{SEASON}.json"
    return calisma, json.loads(p.read_text(encoding="utf-8"))["veri"]


def _admin_sends(calisma, fix):
    (calisma / "fixes").mkdir(exist_ok=True)
    (calisma / "fixes" / f"{fix['id']}.json").write_text(
        json.dumps(fix, ensure_ascii=False), encoding="utf-8"
    )
    _git(["add", "-A"], calisma)
    _git(["commit", "-m", "fix"], calisma)
    _git(["push", "origin", "HEAD:main"], calisma)


def test_full_round_trip(kurulum, tmp_path):
    data, uzak, store = kurulum

    # 1) hastane gönderir
    res, codes = _push(data, store)
    assert res.status == "gonderildi", res.message

    # 2) yönetici görür — ama isim GÖRMEZ
    calisma, veri = _admin_reads(uzak, tmp_path)
    metin = json.dumps(veri, ensure_ascii=False)
    assert "KAMİL" not in metin and "1001" not in metin
    assert {s["code"] for s in veri["students"]} == {"Ö-01", "Ö-02"}

    # 3) yönetici kontenjanı düzeltir
    birimler = veri["units"]
    birimler[0]["quota"] = 5
    fix = build_fix(SEASON, "ACİL kontenjanı 5 yapıldı", {"units": birimler},
                    base_revision=veri["revision"])
    _admin_sends(calisma, fix)

    # 4) hastane bekleyeni görür
    bekleyen = pending_fixes(data, SEASON, set(store.load_support_applied()))
    assert len(bekleyen.fixes) == 1
    gelen = bekleyen.fixes[0]
    assert gelen["summary"] == "ACİL kontenjanı 5 yapıldı"

    # 5) uygulanır — öğrenciler DOKUNULMADAN
    sonuc = apply_fix(store, gelen, SEASON)
    store.mark_support_applied(gelen["id"])
    assert store.load_units()[0].quota == 5
    assert [s.full_name for s in store.load_students()] == [
        "KAMİL DENEMEOĞLU", "MEHMET ALİ KAYA"
    ]
    assert sonuc["backup"]

    # 6) aynı paket bir daha teklif edilmez
    assert pending_fixes(
        data, SEASON, set(store.load_support_applied())
    ).fixes == []


def test_phone_workflow_code_to_name_and_back(kurulum):
    """Telefon akışı: yönetici kod söyler, kullanıcı adı bulur; tersi de."""
    data, _, store = kurulum
    _, codes = _push(data, store)
    students = store.load_students()

    # yönetici "Ö-02'de sorun var" der
    bulunan = find_by_code(students, codes, "Ö-02")
    assert bulunan.full_name == "MEHMET ALİ KAYA"

    # kullanıcı "Ayşe'den söz ediyorum" der → kodunu okur
    ayse = next(s for s in students if s.full_name.startswith("KAMİL"))
    assert codes[ayse.id] == "Ö-01"


def test_codes_survive_a_roster_change(kurulum):
    """Yeni öğrenci gelince eskilerin kodu kaymamalı — yoksa telefonda
    yanlış kişiden söz edilir ve kimse fark etmez."""
    data, _, store = kurulum
    _, ilk = _push(data, store)
    ogrenciler = store.load_students()
    ogrenciler.insert(0, Student(full_name="YENİ GELEN", gender="K", group=1,
                                 class_name="A"))
    store.save_students(ogrenciler)
    _, sonra = _push(data, store)
    for sid, kod in ilk.items():
        assert sonra[sid] == kod


def test_stale_fix_is_flagged_before_applying(kurulum, tmp_path):
    """Kullanıcı arada çalıştıysa uyarı çıkmalı."""
    from rotasyon.support import validate_fix

    data, uzak, store = kurulum
    _push(data, store)
    calisma, veri = _admin_reads(uzak, tmp_path)
    fix = build_fix(SEASON, "x", {"units": veri["units"]},
                    base_revision=veri["revision"])

    # kullanıcı arada bir birim ekledi
    birimler = store.load_units()
    birimler.append(Unit(name="DİŞ", group=1, quota=1))
    store.save_units(birimler)

    uyarilar = validate_fix(
        fix, SEASON, data_revision(store.raw_season_payload())
    )
    assert uyarilar and "geri alınabilir" in uyarilar[0]


def test_untouched_data_produces_no_warning(kurulum, tmp_path):
    """Karşıt kanıt: dokunulmamışsa uyarı çıkmamalı."""
    from rotasyon.support import validate_fix

    data, uzak, store = kurulum
    _push(data, store)
    _, veri = _admin_reads(uzak, tmp_path)
    fix = build_fix(SEASON, "x", {"units": veri["units"]},
                    base_revision=veri["revision"])
    assert validate_fix(
        fix, SEASON, data_revision(store.raw_season_payload())
    ) == []


def test_revision_is_carried_not_recomputed(kurulum, tmp_path):
    """Damga makinede bir kez hesaplanıp olduğu gibi taşınmalı.

    Yönetici tarafında yeniden hesaplansaydı iki taraf farklı şeyi
    damgalardı (biri ham settings.json, öteki varsayılanlarla birleştirilmiş
    hâli) ve "veri değişmiş" uyarısı hiçbir şey değişmese bile HER SEFERİNDE
    çıkardı. Böyle bir uyarıyı kullanıcı bir süre sonra okumaz.
    """
    data, uzak, store = kurulum
    _push(data, store)
    _, veri = _admin_reads(uzak, tmp_path)
    assert veri["revision"] == data_revision(store.raw_season_payload())
