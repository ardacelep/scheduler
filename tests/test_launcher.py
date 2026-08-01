"""Başlatıcı (run_app.py) yardımcılarının testleri.

Windows'ta çift tıklama akışının bel kemiği: verinin yazılabilir bir yere
düşmesi, ikinci kez tıklanınca ikinci sunucu açılmaması ve boş port bulma.
Bu fonksiyonlar saf tutulduğu için Windows olmadan da sınanabilir.
"""
import socket

import pytest

import run_app


def test_is_writable_true_for_temp(tmp_path):
    assert run_app.is_writable(tmp_path / "yeni")
    assert not (tmp_path / "yeni" / ".yazma-denemesi.tmp").exists()


def test_is_writable_false_for_readonly(tmp_path):
    target = tmp_path / "kilitli"
    target.mkdir()
    target.chmod(0o500)  # yalnız okuma/gezinme
    try:
        assert not run_app.is_writable(target)
    finally:
        target.chmod(0o700)


def test_choose_working_dir_uses_cwd_when_not_frozen(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    work_dir, fallback = run_app.choose_working_dir()
    assert work_dir == tmp_path
    assert fallback is False


def test_choose_working_dir_falls_back_when_exe_dir_readonly(
    tmp_path, monkeypatch
):
    """Program Files gibi salt-okunur bir yerden çalıştırılırsa veri
    kullanıcı klasörüne düşmeli — sessizce kaybolmamalı."""
    exe_dir = tmp_path / "kurulum"
    exe_dir.mkdir()
    exe_dir.chmod(0o500)
    profile = tmp_path / "profil"
    monkeypatch.setattr(run_app.sys, "frozen", True, raising=False)
    monkeypatch.setattr(
        run_app.sys, "executable", str(exe_dir / "uygulama.exe"), raising=False
    )
    monkeypatch.setenv("LOCALAPPDATA", str(profile))
    try:
        work_dir, fallback = run_app.choose_working_dir()
    finally:
        exe_dir.chmod(0o700)
    assert fallback is True
    assert work_dir == profile / run_app.APP_FOLDER
    assert work_dir.is_dir()


def test_find_free_port_skips_busy_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen(64)  # bağlantı kuyruğu dolmasın: her deneme yanıt alsın
        port = busy.getsockname()[1]
        assert run_app.port_is_open(port)
        assert run_app.find_free_port(port) != port


def test_lock_file_roundtrip(tmp_path):
    # kilit yokken "zaten çalışıyor" denmemeli
    assert run_app.running_instance_port(tmp_path) is None
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as live:
        live.bind(("127.0.0.1", 0))
        live.listen(64)
        port = live.getsockname()[1]
        run_app.write_lock(tmp_path, port)
        assert run_app.running_instance_port(tmp_path) == port
    # süreç öldükten sonra kilit bayat: yeni sunucu başlatılabilmeli
    assert run_app.running_instance_port(tmp_path) is None
    run_app.clear_lock(tmp_path)
    assert not run_app.lock_path(tmp_path).exists()


def test_clear_lock_is_safe_when_missing(tmp_path):
    run_app.clear_lock(tmp_path)  # hata atmamalı


def test_streamlit_env_sets_end_user_defaults(monkeypatch):
    for key in list(run_app.os.environ):
        if key.startswith("STREAMLIT_"):
            monkeypatch.delenv(key, raising=False)
    run_app.streamlit_env()
    env = run_app.os.environ
    assert env["STREAMLIT_SERVER_HEADLESS"] == "true"  # e-posta ekranı çıkmasın
    assert env["STREAMLIT_SERVER_ADDRESS"] == "127.0.0.1"  # firewall sormasın
    assert env["STREAMLIT_CLIENT_TOOLBAR_MODE"] == "minimal"


def test_exe_theme_matches_config_toml(monkeypatch):
    """exe (ortam değişkeni) ile kaynak (config.toml) aynı görünmeli.

    config.toml exe'ye paketlenmiyor; tema iki yerde ayrı tanımlı olduğu için
    biri güncellenip diğeri unutulursa uygulama iki farklı görünüme sahip olur.
    """
    import re
    import pathlib

    for key in list(run_app.os.environ):
        if key.startswith("STREAMLIT_"):
            monkeypatch.delenv(key, raising=False)
    run_app.streamlit_env()

    toml = pathlib.Path(__file__).resolve().parents[1] / ".streamlit/config.toml"
    metin = toml.read_text(encoding="utf-8")
    # [theme] ve [theme.sidebar] bölümlerindeki anahtar = "değer" çiftleri
    bolumler = re.split(r"^\[", metin, flags=re.M)
    bulunan = 0
    for bolum in bolumler:
        if not bolum.startswith("theme"):
            continue
        onek = "STREAMLIT_THEME_SIDEBAR_" if bolum.startswith(
            "theme.sidebar"
        ) else "STREAMLIT_THEME_"
        for anahtar, deger in re.findall(
            r'^(\w+)\s*=\s*"([^"]+)"', bolum, flags=re.M
        ):
            env_key = onek + re.sub(r"(?<!^)(?=[A-Z])", "_", anahtar).upper()
            assert run_app.os.environ.get(env_key) == deger, (
                f"{env_key} config.toml'daki {anahtar}={deger} ile uyuşmuyor"
            )
            bulunan += 1
    assert bulunan >= 7, f"tema anahtarları okunamadı ({bulunan})"


def test_streamlit_env_does_not_override_user_choice(monkeypatch):
    monkeypatch.setenv("STREAMLIT_SERVER_ADDRESS", "0.0.0.0")
    run_app.streamlit_env()
    assert run_app.os.environ["STREAMLIT_SERVER_ADDRESS"] == "0.0.0.0"


@pytest.mark.skipif(run_app.IS_WINDOWS, reason="Windows'ta mesaj kutusu açar")
def test_message_box_falls_back_to_print(capsys):
    run_app.message_box("deneme")
    assert "deneme" in capsys.readouterr().out


def test_setup_logging_writes_and_rotates(tmp_path, capsys):
    original_out, original_err = run_app.sys.stdout, run_app.sys.stderr
    try:
        first = run_app.setup_logging(tmp_path)
        print("ilk çalışma")
        run_app.sys.stdout.flush()
        assert first is not None and first.exists()
        second = run_app.setup_logging(tmp_path)
        assert second == first
        previous = tmp_path / "data" / "gunluk" / "uygulama.onceki.log"
        assert "ilk çalışma" in previous.read_text(encoding="utf-8")
    finally:
        run_app.sys.stdout, run_app.sys.stderr = original_out, original_err
