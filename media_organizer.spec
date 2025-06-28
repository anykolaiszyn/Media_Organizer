# spec file for PyInstaller single-file build with ExifTool
# To use: pyinstaller media_organizer.spec

block_cipher = None

from PyInstaller.utils.hooks import collect_submodules


# Add exiftool-wrapper Python package to hiddenimports
hiddenimports = collect_submodules('app') + ['exiftool_wrapper']

import os
a_project_root = os.path.abspath('.')
pathex = [a_project_root]
script_path = 'media_organizer/app/main.py'
exiftool_path = 'media_organizer/ExifTool/exiftool.exe'
a = Analysis(
    [script_path],
    pathex=pathex,
    binaries=[(exiftool_path, '.')],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='media_organizer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Hide console window for GUI app
)
