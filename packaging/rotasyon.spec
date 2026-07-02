# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Windows üzerinde çalıştırılır (bkz. README).

Kullanım (Windows, proje kökünde):
    pyinstaller packaging/rotasyon.spec
Çıktı: dist/StajRotasyonu.exe
"""
import os

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

block_cipher = None
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(ROOT, "app.py"), "."),
    (os.path.join(ROOT, "ui"), "ui"),
    (os.path.join(ROOT, "rotasyon"), "rotasyon"),
    (os.path.join(ROOT, "seed_data"), "seed_data"),
]
# Streamlit çalışma zamanı dosyaları ve metadata'sı (bilinen paketleme gereği)
datas += collect_data_files("streamlit")
datas += copy_metadata("streamlit")

a = Analysis(
    [os.path.join(ROOT, "run_app.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "streamlit",
        "streamlit.web.cli",
        "streamlit.runtime.scriptrunner.magic_funcs",
        "ortools",
        "ortools.sat.python.cp_model",
        "openpyxl",
        "pandas",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="StajRotasyonu",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # ilk sürümde konsol açık: hata olursa kullanıcı görebilsin
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
