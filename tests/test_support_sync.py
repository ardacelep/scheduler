"""Destek kanalı taşıma katmanı — gerçek git ile, ağ olmadan.

"Uzak depo" olarak yerel bir bare repo kullanılır: git komutlarının gerçekten
çalıştığı doğrulanır ama hiçbir şey internete çıkmaz.
"""
import json
import subprocess

import pytest

from rotasyon.models import Student, Unit
from rotasyon.support import assign_codes, build_fix, build_snapshot
from rotasyon.support_sync import (
    SupportConfig,
    load_config,
    pending_fixes,
    push_snapshot,
    redact,
    save_config,
)

SEASON = "26-27 test"


def _git(args, cwd):
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )


@pytest.fixture
def kanal(tmp_path):
    """(data_dir, uzak_depo) — kurulmuş, çalışır bir destek kanalı."""
    uzak = tmp_path / "uzak.git"
    _git(["init", "--bare", "--initial-branch=main", str(uzak)], tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    save_config(data, SupportConfig(repo=str(uzak), enabled=True,
                                    machine="hastane"))
    return data, uzak


def _snap(students, units=()):
    return build_snapshot(
        SEASON, students, list(units), [], [], [], {"months": ["EYLÜL"]}, [],
        assign_codes(students),
    )


def S(ad="KAMİL DENEMEOĞLU"):
    return Student(full_name=ad, gender="K", group=1, class_name="A",
                   student_no="123")


# ---- yapılandırma ----

def test_channel_is_off_until_configured(tmp_path):
    assert not load_config(tmp_path).ready


def test_config_round_trips(tmp_path):
    save_config(tmp_path, SupportConfig(repo="https://x", enabled=True,
                                        machine="m"))
    cfg = load_config(tmp_path)
    assert cfg.ready and cfg.repo == "https://x" and cfg.machine == "m"


def test_broken_config_does_not_crash(tmp_path):
    (tmp_path / "support.json").write_text("{bozuk", encoding="utf-8")
    assert not load_config(tmp_path).ready


def test_token_never_appears_in_a_redacted_url():
    url = "https://x-access-token:ghp_GIZLI123@github.com/a/b.git"
    assert "ghp_GIZLI123" not in redact(url)
    assert "github.com/a/b.git" in redact(url)


def test_disabled_channel_sends_nothing(tmp_path):
    (tmp_path).mkdir(exist_ok=True)
    res = push_snapshot(tmp_path, SEASON, _snap([S()]).to_dict())
    assert res.status == "kapali"


# ---- gönderim ----

def test_snapshot_reaches_the_remote(kanal):
    data, uzak = kanal
    res = push_snapshot(data, SEASON, _snap([S()]))
    assert res.status == "gonderildi", res.message
    out = _git(["ls-tree", "-r", "--name-only", "main"], uzak).stdout
    assert "snapshots/26-27-test.json" in out


def test_unchanged_data_is_not_pushed_again(kanal):
    data, _ = kanal
    snap = _snap([S()])
    assert push_snapshot(data, SEASON, snap).status == "gonderildi"
    assert push_snapshot(data, SEASON, snap).status == "degisiklik-yok"


def test_changed_data_is_pushed_again(kanal):
    data, _ = kanal
    s = S()
    push_snapshot(data, SEASON, _snap([s]))
    res = push_snapshot(data, SEASON, _snap([s], [Unit(name="ACİL", group=1)]))
    assert res.status == "gonderildi"


def test_pushed_file_has_no_student_names(kanal):
    data, uzak = kanal
    push_snapshot(data, SEASON, _snap([S("KAMİL DENEMEOĞLU")]))
    icerik = _git(["show", "main:snapshots/26-27-test.json"], uzak).stdout
    assert "KAMİL" not in icerik
    assert "Ö-01" in icerik


def test_a_leak_stops_the_push_entirely(kanal):
    """Beyaz liste bozulursa gönderim HİÇ yapılmamalı — son savunma."""
    data, uzak = kanal
    students = [S("KAMİL DENEMEOĞLU")]
    snap = _snap(students)
    snap.settings = {"not": "KAMİL DENEMEOĞLU aradı"}  # kasten sızdır
    res = push_snapshot(data, SEASON, snap, students=students)
    assert res.status == "hata"
    assert "kişisel bilgi" in res.message
    # uzak depoda hiçbir şey yok
    assert _git(["rev-list", "--all", "--count"], uzak).stdout.strip() == "0"


def test_clean_snapshot_passes_the_leak_check(kanal):
    """Karşıt kanıt: denetim temiz görüntüyü engellememeli."""
    data, _ = kanal
    students = [S("KAMİL DENEMEOĞLU")]
    res = push_snapshot(data, SEASON, _snap(students), students=students)
    assert res.status == "gonderildi", res.message


def test_bad_repo_reports_an_error_without_crashing(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    save_config(data, SupportConfig(repo=str(tmp_path / "yok.git"),
                                    enabled=True))
    res = push_snapshot(data, SEASON, _snap([S()]))
    assert res.status == "hata"


# ---- düzeltmelerin gelmesi ----

def _publish_fix(uzak, tmp_path, fix, name="f1.json"):
    """Yönetici tarafını taklit eder: düzeltmeyi uzak depoya koyar."""
    calisma = tmp_path / f"admin-{name}"
    _git(["clone", str(uzak), str(calisma)], tmp_path)
    _git(["config", "user.email", "a@b"], calisma)
    _git(["config", "user.name", "admin"], calisma)
    (calisma / "fixes").mkdir(exist_ok=True)
    (calisma / "fixes" / name).write_text(
        json.dumps(fix, ensure_ascii=False), encoding="utf-8"
    )
    _git(["add", "-A"], calisma)
    _git(["commit", "-m", "fix"], calisma)
    _git(["push", "origin", "HEAD:main"], calisma)


def test_pending_fix_is_seen(kanal, tmp_path):
    data, uzak = kanal
    push_snapshot(data, SEASON, _snap([S()]))  # depoda ilk commit olsun
    _publish_fix(uzak, tmp_path, build_fix(SEASON, "kontenjan", {"units": []}))
    res = pending_fixes(data, SEASON)
    assert len(res.fixes) == 1
    assert res.fixes[0]["summary"] == "kontenjan"


def test_already_applied_fix_is_not_offered_again(kanal, tmp_path):
    data, uzak = kanal
    push_snapshot(data, SEASON, _snap([S()]))
    fix = build_fix(SEASON, "kontenjan", {"units": []})
    _publish_fix(uzak, tmp_path, fix)
    assert pending_fixes(data, SEASON, applied={fix["id"]}).fixes == []


def test_fix_for_another_season_is_ignored(kanal, tmp_path):
    data, uzak = kanal
    push_snapshot(data, SEASON, _snap([S()]))
    _publish_fix(uzak, tmp_path, build_fix("BAŞKA SEZON", "x", {"units": []}))
    assert pending_fixes(data, SEASON).fixes == []


def test_corrupt_fix_file_is_skipped_not_fatal(kanal, tmp_path):
    data, uzak = kanal
    push_snapshot(data, SEASON, _snap([S()]))
    _publish_fix(uzak, tmp_path, build_fix(SEASON, "iyi", {"units": []}))
    calisma = tmp_path / "admin-bozuk"
    _git(["clone", str(uzak), str(calisma)], tmp_path)
    _git(["config", "user.email", "a@b"], calisma)
    _git(["config", "user.name", "admin"], calisma)
    (calisma / "fixes" / "bozuk.json").write_text("{{{", encoding="utf-8")
    _git(["add", "-A"], calisma)
    _git(["commit", "-m", "bozuk"], calisma)
    _git(["push", "origin", "HEAD:main"], calisma)
    res = pending_fixes(data, SEASON)
    assert len(res.fixes) == 1 and res.fixes[0]["summary"] == "iyi"


def test_pending_fixes_off_when_channel_disabled(tmp_path):
    assert pending_fixes(tmp_path, SEASON).status == "kapali"
