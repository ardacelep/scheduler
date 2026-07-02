"""PyInstaller başlatıcısı — çift tıklanınca uygulamayı açar.

Streamlit'i kendi süreç içinde (stcli) başlatır, tarayıcıyı otomatik açar.
Veri klasörü (data/) exe'nin yanında oluşturulur ki kullanıcı verisi
güncellemelerde kaybolmasın.
"""
import os
import socket
import sys
import threading
import time
import webbrowser


def resource_path(relative: str) -> str:
    """PyInstaller onefile modunda dosyalar geçici _MEIPASS klasörüne açılır."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def find_free_port(preferred: int = 8501) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return preferred


def open_browser_when_ready(port: int) -> None:
    url = f"http://localhost:{port}"
    for _ in range(120):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                webbrowser.open(url)
                return
        time.sleep(0.5)


def main() -> None:
    if getattr(sys, "frozen", False):
        # veri klasörü exe'nin yanında dursun
        os.chdir(os.path.dirname(sys.executable))

    port = find_free_port()
    threading.Thread(
        target=open_browser_when_ready, args=(port,), daemon=True
    ).start()

    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit",
        "run",
        resource_path("app.py"),
        f"--server.port={port}",
        "--server.headless=true",
        "--global.developmentMode=false",
        "--browser.gatherUsageStats=false",
    ]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
