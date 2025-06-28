# spec file for PyInstaller single-file build with ExifTool
# To use: pyinstaller media_organizer.spec

block_cipher = None

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules('app')

script_path = 'media-organizer/cli.py'
exiftool_path = 'media-organizer/ExifTool/exiftool.exe'
a = Analysis(
    [script_path],
    pathex=[],
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
    name='media-organizer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
