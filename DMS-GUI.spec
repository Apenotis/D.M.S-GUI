# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['Gui.py'],
    pathex=[],
    binaries=[],
    datas=[('E:\\Doom Classic\\assets', 'assets')],
    hiddenimports=['dms_core.config', 'dms_core.database', 'dms_core.api', 'dms_core.engine_manager', 'dms_core.game_runner', 'dms_core.initialization', 'dms_core.installer', 'dms_core.map_loader', 'dms_core.setup_wizard', 'dms_core.updater', 'dms_core.utils'],
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
    [],
    exclude_binaries=True,
    name='DMS-GUI',
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
    icon=['E:\\Doom Classic\\assets\\dms_icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DMS-GUI',
)
