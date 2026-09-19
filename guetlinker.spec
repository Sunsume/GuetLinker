# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for GuetLinker."""

import sys

block_cipher = None
is_macos = sys.platform == 'darwin'
hidden_imports = [
    'PySide6.QtWidgets',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'httpx',
    'bs4',
    'cryptography',
    'psutil',
]
if is_macos:
    hidden_imports.extend(['AppKit', 'Foundation', 'objc'])

a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hidden_imports,
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
    [] if is_macos else a.binaries,
    [] if is_macos else a.zipfiles,
    [] if is_macos else a.datas,
    [],
    name='GuetLinker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=not is_macos,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # TODO: Add icon
    exclude_binaries=is_macos,
)

if is_macos:
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        name='GuetLinker',
    )

    app = BUNDLE(
        coll,
        name='GuetLinker.app',
        icon=None,
        bundle_identifier='io.github.sunsume.GuetLinker',
        info_plist={
            'CFBundleDisplayName': 'GuetLinker',
            'CFBundleName': 'GuetLinker',
            'CFBundleShortVersionString': '1.0.0',
            'CFBundleVersion': '1.0.0',
            'LSMinimumSystemVersion': '12.0',
            # Run as a menu-bar agent on macOS. The main window remains fully
            # usable, while closing it keeps monitoring active in background.
            'LSUIElement': True,
            'NSHighResolutionCapable': True,
        },
    )
