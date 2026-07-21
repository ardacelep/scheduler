# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Windows'ta çalıştırılır (bkz. README).

    pyinstaller --noconfirm packaging/rotasyon.spec

Çıktı: dist/StajRotasyonu/ klasörü, içinde "Staj Rotasyonu.exe".

Neden tek dosya (onefile) değil? OR-Tools + Streamlit ile tek dosya birkaç
yüz MB olur ve HER açılışta geçici klasöre açıldığı için başlangıç yarım
dakikayı aşar. Klasör (onedir) sürümü birkaç saniyede açılır; son
kullanıcıya zip olarak verilir, "klasörü çıkar, exe'ye çift tıkla" yeter.
"""
import os

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SKIP_DIRS = {"__pycache__", ".pytest_cache", ".git"}


def tree(src_rel: str, dest: str):
    """Kaynak ağacını datas girdilerine çevirir (__pycache__ hariç)."""
    entries = []
    src_root = os.path.join(ROOT, src_rel)
    for dirpath, dirnames, filenames in os.walk(src_root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        rel = os.path.relpath(dirpath, src_root)
        target = dest if rel == "." else os.path.join(dest, rel)
        for name in filenames:
            if name.endswith((".pyc", ".pyo")):
                continue
            entries.append((os.path.join(dirpath, name), target))
    return entries


def metadata(package: str):
    """Paket metadata'sı — kurulu değilse derlemeyi kırmasın."""
    try:
        return copy_metadata(package)
    except Exception:
        return []


datas = [(os.path.join(ROOT, "app.py"), ".")]
datas += tree("ui", "ui")
datas += tree("rotasyon", "rotasyon")  # varsayılan birim kataloğu dahil
datas += tree("seed_data", "seed_data")
# .streamlit/config.toml paketlenmez: onedir'de datas `_internal/` altına
# düşer, Streamlit ise config'i çalışma klasöründe arar. Son kullanıcı
# ayarlarını run_app.py ortam değişkeni olarak verir (streamlit_env).

# Streamlit çalışma zamanı dosyaları (statik ön yüz) ve metadata'lar
datas += collect_data_files("streamlit")
for _pkg in (
    "streamlit", "pandas", "numpy", "pyarrow", "openpyxl", "pypdf",
    "ortools", "gender_guesser", "altair", "packaging",
):
    datas += metadata(_pkg)
# gender_guesser'ın isim sözlüğü (cinsiyet tahmini çevrimdışı çalışır)
datas += collect_data_files("gender_guesser")

binaries = collect_dynamic_libs("ortools")

hiddenimports = [
    "streamlit",
    "streamlit.web.cli",
    "streamlit.runtime.scriptrunner.magic_funcs",
    "ortools",
    "ortools.sat.python.cp_model",
    "openpyxl",
    "pypdf",
    "pandas",
    "pyarrow",
    "pyarrow.vendored.version",
    "gender_guesser",
    "gender_guesser.detector",
]
hiddenimports += collect_submodules("rotasyon")
hiddenimports += collect_submodules("ui")

a = Analysis(
    [os.path.join(ROOT, "run_app.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest", "_pytest", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Staj Rotasyonu",
    icon=os.path.join(ROOT, "packaging", "icon.ico"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # Konsol açık: uygulamanın çalıştığının görünür işareti ve kapatma yolu.
    # run_app.py konsola Türkçe yönerge basar ve QuickEdit donmasını kapatır.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="StajRotasyonu",
)
