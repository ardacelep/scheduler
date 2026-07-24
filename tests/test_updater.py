"""Otomatik güncelleyicinin (scripts/updater.py) testleri.

Uzak makinede gözetimsiz çalışacak — en kritik güvenceler:
kullanıcı verisine (data/, git dışı) asla dokunulmaması, çevrimdışıyken
sessizce mevcut sürümle devam edilmesi ve bağımlılık kurulumu patlarsa
eski sürüme geri dönülmesi. Hepsi yerel git depolarıyla, ağsız sınanır.
"""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import updater


def git(root, *args):
    proc = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout.strip()


def make_repos(tmp_path):
    """origin (bare) + geliştirici klonu + saha (hastane) klonu."""
    origin = tmp_path / "origin.git"
    origin.mkdir()
    git(origin, "init", "--bare", "--initial-branch=main")

    dev = tmp_path / "dev"
    git(tmp_path, "clone", str(origin), "dev")
    git(dev, "config", "user.email", "test@test")
    git(dev, "config", "user.name", "Test")
    (dev / "app.py").write_text("SURUM = 1\n", encoding="utf-8")
    (dev / "requirements.txt").write_text("streamlit>=1.36\n", encoding="utf-8")
    (dev / ".gitignore").write_text("/data/\n", encoding="utf-8")
    git(dev, "add", "-A")
    git(dev, "commit", "-m", "ilk sürüm")
    git(dev, "push", "origin", "main")

    site = tmp_path / "site"
    git(tmp_path, "clone", str(origin), "site")
    git(site, "config", "user.email", "site@test")
    git(site, "config", "user.name", "Site")
    # kullanıcı verisi: git dışı, güncellemeden etkilenmemeli
    (site / "data").mkdir()
    (site / "data" / "students.json").write_text(
        '[{"ad": "korunmalı"}]', encoding="utf-8"
    )
    return origin, dev, site


def push_change(dev, version=2, requirements=None):
    (dev / "app.py").write_text(f"SURUM = {version}\n", encoding="utf-8")
    if requirements is not None:
        (dev / "requirements.txt").write_text(requirements, encoding="utf-8")
    git(dev, "add", "-A")
    git(dev, "commit", "-m", f"sürüm {version}")
    git(dev, "push", "origin", "main")


def test_up_to_date(tmp_path):
    _o, _d, site = make_repos(tmp_path)
    result = updater.check_and_update(site, log=lambda *_: None)
    assert result.status == "guncel"


def test_turkish_commit_message_decoded_utf8(tmp_path):
    """git çıktısı UTF-8 çözülmeli — Windows'ta commit mesajı bozulmasın.

    _git text=True'yu locale kodlamasıyla çözerse "İ ş ğ ü" gibi harfler
    'Ã'lı bozuk dizilere döner; encoding='utf-8' bunu engeller.
    """
    _o, dev, site = make_repos(tmp_path)
    (dev / "app.py").write_text("SURUM = 2\n", encoding="utf-8")
    git(dev, "add", "-A")
    git(dev, "commit", "-m", "İleriye dönük düzeltme: şubeler güncellendi")
    git(dev, "push", "origin", "main")

    result = updater.check_and_update(site, log=lambda *_: None)
    assert result.status == "guncellendi"
    birlesik = " ".join(result.notes)
    assert "İleriye dönük düzeltme: şubeler güncellendi" in birlesik
    assert "Ã" not in birlesik  # bozuk kodlama izi yok


def test_update_applies_and_preserves_user_data(tmp_path):
    _o, dev, site = make_repos(tmp_path)
    push_change(dev, version=2)
    result = updater.check_and_update(site, log=lambda *_: None)
    assert result.status == "guncellendi"
    assert (site / "app.py").read_text(encoding="utf-8") == "SURUM = 2\n"
    # kullanıcı verisi el değmeden duruyor
    assert (site / "data" / "students.json").read_text(
        encoding="utf-8"
    ) == '[{"ad": "korunmalı"}]'
    # değişiklik özeti dolu (uzaktaki kullanıcıya okunur bilgi)
    assert any("sürüm 2" in n for n in result.notes)


def test_unchanged_requirements_skip_pip(tmp_path):
    _o, dev, site = make_repos(tmp_path)
    push_change(dev, version=2)  # requirements aynı kaldı
    calls = []
    result = updater.check_and_update(
        site, log=lambda *_: None, pip_runner=lambda r: calls.append(r) or True
    )
    assert result.status == "guncellendi"
    assert calls == []  # pip hiç çağrılmadı: açılış yavaşlamaz


def test_changed_requirements_run_pip(tmp_path):
    _o, dev, site = make_repos(tmp_path)
    push_change(dev, version=2, requirements="streamlit>=1.36\nyeni-paket\n")
    calls = []
    result = updater.check_and_update(
        site, log=lambda *_: None, pip_runner=lambda r: calls.append(r) or True
    )
    assert result.status == "guncellendi"
    assert calls == [site]


def test_pip_failure_rolls_back_code(tmp_path):
    """Yarı güncel durum bırakılmaz: kod yeni + bağımlılık eksik = hiç açılmaz."""
    _o, dev, site = make_repos(tmp_path)
    old_rev = git(site, "rev-parse", "HEAD")
    push_change(dev, version=2, requirements="olmayan-paket==999\n")
    result = updater.check_and_update(
        site, log=lambda *_: None, pip_runner=lambda r: False
    )
    assert result.status == "geri-alindi"
    assert git(site, "rev-parse", "HEAD") == old_rev
    assert (site / "app.py").read_text(encoding="utf-8") == "SURUM = 1\n"


def test_offline_keeps_current_version(tmp_path):
    origin, dev, site = make_repos(tmp_path)
    push_change(dev, version=2)
    # origin'i ortadan kaldır: ağ yok senaryosu
    git(site, "remote", "set-url", "origin", str(tmp_path / "yok.git"))
    result = updater.check_and_update(site, log=lambda *_: None)
    assert result.status == "cevrimdisi"
    assert (site / "app.py").read_text(encoding="utf-8") == "SURUM = 1\n"


def test_non_repo_directory(tmp_path):
    plain = tmp_path / "duz-klasor"
    plain.mkdir()
    result = updater.check_and_update(plain, log=lambda *_: None)
    assert result.status in ("depo-degil", "git-yok")


def test_local_edits_are_overwritten_but_untracked_kept(tmp_path):
    """Sahada dosya bozulsa bile (izlenen dosyada oynama) depo kendini onarır;
    git dışı dosyalara (data/) dokunulmaz — git clean asla çalışmaz."""
    _o, dev, site = make_repos(tmp_path)
    (site / "app.py").write_text("BOZULDU\n", encoding="utf-8")
    (site / "data" / "ekstra.txt").write_text("dursun", encoding="utf-8")
    push_change(dev, version=3)
    result = updater.check_and_update(site, log=lambda *_: None)
    assert result.status == "guncellendi"
    assert (site / "app.py").read_text(encoding="utf-8") == "SURUM = 3\n"
    assert (site / "data" / "ekstra.txt").exists()
