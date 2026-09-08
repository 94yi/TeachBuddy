# -*- mode: python ; coding: utf-8 -*-

import sys

if sys.version_info[:3] != (3, 8, 10):
    raise SystemExit("Win7 发布包必须使用 Python 3.8.10 构建")
if sys.platform != "win32":
    raise SystemExit("Win7 发布包必须在 Windows 上构建")


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[("app/resources", "app/resources"),
           ("data/config.example.json", "embedded_defaults")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="TeachBuddy",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
