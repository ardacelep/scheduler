"""Staj Rotasyonu başlatıcısı — .exe'ye çift tıklanınca uygulamayı açar.

Hedef kullanıcı teknik değildir; bu dosya "çift tıkla, tarayıcı açılsın,
başka hiçbir şey yapma" deneyiminden sorumludur. Yaptıkları:

* Verinin yazılabilir bir klasöre düşmesini garanti eder (exe'nin yanı;
  olmuyorsa %LOCALAPPDATA%). Program Files'a kurulmuş ya da salt-okunur
  bir klasörden çalıştırılmış exe veri kaybettirmesin.
* Uygulama zaten açıksa ikinci sunucu başlatmaz, sadece tarayıcıyı açar.
* Her şeyi bir günlük dosyasına yazar; çökme olursa Türkçe bir uyarı
  penceresiyle günlüğün yerini söyler.
* Konsolun "QuickEdit" tuzağını kapatır: kullanıcı siyah pencereye
  tıklayınca uygulama donmuş gibi görünmesin.
* Sunucuyu yalnız 127.0.0.1'e bağlar — Windows güvenlik duvarı izin
  penceresi çıkmaz.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

APP_TITLE = "Staj Rotasyonu"
APP_FOLDER = "StajRotasyonu"  # %LOCALAPPDATA% altındaki klasör adı
DEFAULT_PORT = 8501
PORT_RANGE = 20
IS_WINDOWS = os.name == "nt"


# --------------------------------------------------------------------------
# yol/klasör yardımcıları
# --------------------------------------------------------------------------
def resource_path(relative: str) -> str:
    """Paketlenmiş dosyaların yolu (PyInstaller _MEIPASS'e açar)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_writable(directory: Path) -> bool:
    """Klasöre gerçekten yazılabiliyor mu? (Deneme dosyası yazıp siler.)"""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".yazma-denemesi.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def fallback_data_root() -> Path:
    """Kullanıcı profilindeki yedek konum (her zaman yazılabilir)."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_FOLDER
    return Path.home() / f".{APP_FOLDER.lower()}"


def choose_working_dir() -> tuple[Path, bool]:
    """Uygulamanın çalışacağı klasör. Dönüş: (klasör, yedek_konum_mu).

    Veri `data/` altında, çalışma klasörüne göre tutulur. Kaynaktan
    çalışırken proje kökü kullanılır; exe'de exe'nin yanı tercih edilir ki
    kullanıcı klasörü kopyalayınca verisi de gelsin.
    """
    if not is_frozen():
        return Path.cwd(), False
    beside_exe = Path(sys.executable).resolve().parent
    if is_writable(beside_exe / "data"):
        return beside_exe, False
    fallback = fallback_data_root()
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback, True


# --------------------------------------------------------------------------
# günlük (log)
# --------------------------------------------------------------------------
class _Tee:
    """Yazılanı hem konsola hem günlük dosyasına verir."""

    def __init__(self, stream, log_file):
        self._stream = stream
        self._log = log_file

    def write(self, text):
        if self._stream is not None:
            try:
                self._stream.write(text)
            except (ValueError, OSError):
                pass
        try:
            self._log.write(text)
            self._log.flush()
        except (ValueError, OSError):
            pass
        return len(text)

    def flush(self):
        for target in (self._stream, self._log):
            try:
                if target is not None:
                    target.flush()
            except (ValueError, OSError):
                pass

    def isatty(self):
        return bool(self._stream is not None and self._stream.isatty())


def setup_logging(work_dir: Path) -> Path | None:
    """Günlük dosyasını açar; bir önceki çalışmayı .onceki olarak saklar."""
    log_dir = work_dir / "data" / "gunluk"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "uygulama.log"
        if log_path.exists():
            previous = log_dir / "uygulama.onceki.log"
            previous.unlink(missing_ok=True)
            log_path.rename(previous)
        handle = open(log_path, "w", encoding="utf-8", errors="replace")
    except OSError:
        return None
    sys.stdout = _Tee(sys.stdout, handle)
    sys.stderr = _Tee(sys.stderr, handle)
    return log_path


# --------------------------------------------------------------------------
# Windows konsol/pencere davranışı
# --------------------------------------------------------------------------
def prepare_console() -> None:
    """Konsol başlığını ayarlar ve QuickEdit (tıklayınca donma) kapatır."""
    if not IS_WINDOWS:
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleTitleW(f"{APP_TITLE} — bu pencereyi kapatmayın")
        handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        mode = ctypes.c_uint()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            enable_quick_edit = 0x0040
            enable_extended = 0x0080
            new_mode = (mode.value & ~enable_quick_edit) | enable_extended
            kernel32.SetConsoleMode(handle, new_mode)
    except Exception:  # konsol yoksa/erişilemiyorsa sessizce geç
        pass


def message_box(text: str, title: str = APP_TITLE) -> None:
    """Windows'ta uyarı penceresi; diğer sistemlerde konsola yazar."""
    if IS_WINDOWS:
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)  # MB_ICONERROR
            return
        except Exception:
            pass
    print(f"\n[{title}] {text}\n")


# --------------------------------------------------------------------------
# port / tek örnek (single instance)
# --------------------------------------------------------------------------
def port_is_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


def find_free_port(preferred: int = DEFAULT_PORT) -> int:
    for port in range(preferred, preferred + PORT_RANGE):
        if not port_is_open(port):
            return port
    return preferred


def lock_path(work_dir: Path) -> Path:
    return work_dir / "data" / "calisiyor.txt"


def running_instance_port(work_dir: Path) -> int | None:
    """Uygulama zaten açıksa portunu döndürür, değilse None."""
    try:
        port = int(lock_path(work_dir).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return port if port_is_open(port) else None


def write_lock(work_dir: Path, port: int) -> None:
    try:
        lock_path(work_dir).parent.mkdir(parents=True, exist_ok=True)
        lock_path(work_dir).write_text(str(port), encoding="utf-8")
    except OSError:
        pass


def clear_lock(work_dir: Path) -> None:
    try:
        lock_path(work_dir).unlink(missing_ok=True)
    except OSError:
        pass


# --------------------------------------------------------------------------
# açılış
# --------------------------------------------------------------------------
def open_browser_when_ready(port: int, timeout_s: float = 120.0) -> None:
    url = f"http://localhost:{port}"
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if port_is_open(port):
            webbrowser.open(url)
            return
        time.sleep(0.4)
    message_box(
        "Uygulama beklenenden uzun sürdü ve tarayıcı açılamadı.\n\n"
        f"Tarayıcınızı elle açıp şu adrese gidebilirsiniz:\n{url}"
    )


def print_banner(port: int, work_dir: Path, using_fallback: bool) -> None:
    line = "=" * 62
    print(line)
    print(f"  {APP_TITLE}")
    print(line)
    print("  Uygulama açılıyor, ilk açılış yarım dakika sürebilir...")
    print(f"  Tarayıcı kendiliğinden açılmazsa:  http://localhost:{port}")
    print()
    print("  ! BU SİYAH PENCEREYİ KAPATMAYIN — uygulama burada çalışıyor.")
    print("    İşiniz bitince bu pencereyi kapatarak uygulamayı kapatın.")
    print()
    print(f"  Verileriniz: {work_dir / 'data'}")
    if using_fallback:
        print("  (Uygulamanın bulunduğu klasöre yazılamadığı için veriler")
        print("   kullanıcı klasörünüzde tutuluyor.)")
    print(line, flush=True)
    print()


def streamlit_env() -> None:
    """Streamlit'i son kullanıcıya uygun kipe alır.

    Ortam değişkenleri kullanılır: exe'nin yanında .streamlit klasörü
    olmasa da geçerlidir ve komut satırı bayraklarından daha kapsayıcıdır.
    """
    defaults = {
        "STREAMLIT_SERVER_HEADLESS": "true",  # e-posta sorma ekranını atlar
        "STREAMLIT_SERVER_ADDRESS": "127.0.0.1",  # güvenlik duvarı sormasın
        "STREAMLIT_SERVER_FILE_WATCHER_TYPE": "none",
        "STREAMLIT_SERVER_MAX_UPLOAD_SIZE": "200",
        "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
        "STREAMLIT_CLIENT_TOOLBAR_MODE": "minimal",  # geliştirici menüsü gizli
        "STREAMLIT_GLOBAL_DEVELOPMENT_MODE": "false",
        "STREAMLIT_LOGGER_LEVEL": "warning",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


def run_streamlit(port: int) -> None:
    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit",
        "run",
        resource_path("app.py"),
        f"--server.port={port}",
        "--server.address=127.0.0.1",
        "--server.headless=true",
        "--global.developmentMode=false",
        "--browser.gatherUsageStats=false",
        "--client.toolbarMode=minimal",
    ]
    stcli.main()


def main() -> int:
    work_dir, using_fallback = choose_working_dir()
    os.chdir(work_dir)
    log_path = setup_logging(work_dir)
    prepare_console()
    streamlit_env()

    existing = running_instance_port(work_dir)
    if existing:
        print(f"{APP_TITLE} zaten açık — tarayıcıda gösteriliyor.")
        webbrowser.open(f"http://localhost:{existing}")
        time.sleep(2)
        return 0

    port = find_free_port()
    write_lock(work_dir, port)
    print_banner(port, work_dir, using_fallback)
    threading.Thread(
        target=open_browser_when_ready, args=(port,), daemon=True
    ).start()
    try:
        run_streamlit(port)
    except SystemExit as exc:  # stcli normal kapanışta SystemExit atar
        return int(exc.code or 0)
    except KeyboardInterrupt:
        return 0
    except Exception:
        traceback.print_exc()
        detail = f"\n\nAyrıntılar: {log_path}" if log_path else ""
        message_box(
            "Uygulama beklenmedik bir hatayla kapandı.\n\n"
            "Bu pencereyi kapatıp uygulamayı yeniden başlatmayı deneyin. "
            "Sorun sürerse aşağıdaki günlük dosyasını iletin." + detail
        )
        return 1
    finally:
        clear_lock(work_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
