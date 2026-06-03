# -*- mode: python ; coding: utf-8 -*-
# 在 Windows 11 上执行: .\build_windows.ps1
# 输出目录: dist\PCGOfflineAudio\

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# PyInstaller 注入的 SPECPATH 为「包含本 .spec 的目录」，不是 .spec 文件本身路径
spec_dir = Path(SPECPATH).resolve()

block_cipher = None

sf_bin = collect_dynamic_libs("soundfile")
sf_data = collect_data_files("soundfile")

a = Analysis(
    [str(spec_dir / "app.py")],
    pathex=[str(spec_dir)],
    binaries=sf_bin,
    datas=sf_data,
    hiddenimports=[
        "numpy",
        "soundfile",
        "_soundfile",
        "sounddevice",
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
    [],
    exclude_binaries=True,
    name="PCGOfflineAudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PCGOfflineAudio",
)
