# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['deskpet.py'],
    pathex=[],
    binaries=[],
    datas=[('人物', '人物'), ('logo', 'logo')],
    hiddenimports=['requests', 'idna', 'chardet'],
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
    name='桌宠',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['logo\\logo.ico'],
    version='version.txt',
)
