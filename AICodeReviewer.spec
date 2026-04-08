# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import tomllib

try:
    from PyInstaller.utils.win32.versioninfo import (
        VSVersionInfo,
        FixedFileInfo,
        StringFileInfo,
        StringTable,
        StringStruct,
        VarFileInfo,
        VarStruct,
    )
except ImportError:
    version_info = None
else:
    root_dir = Path.cwd()
    project_version = tomllib.loads((root_dir / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    version_parts = [int(part) for part in project_version.split('.')]
    while len(version_parts) < 4:
        version_parts.append(0)

    file_version = tuple(version_parts[:4])
    file_version_text = '.'.join(str(part) for part in file_version)

    version_info = VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=file_version,
            prodvers=file_version,
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        '040904B0',
                        [
                            StringStruct('CompanyName', 'AICodeReviewer Team'),
                            StringStruct('FileDescription', 'AI-powered multi-backend code review tool'),
                            StringStruct('FileVersion', file_version_text),
                            StringStruct('InternalName', 'AICodeReviewer'),
                            StringStruct('OriginalFilename', 'AICodeReviewer.exe'),
                            StringStruct('ProductName', 'AICodeReviewer'),
                            StringStruct('ProductVersion', project_version),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct('Translation', [1033, 1200])]),
        ],
    )

a = Analysis(
    ['src\\aicodereviewer\\main.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=['keyring.backends.Windows', 'boto3'],
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
    name='AICodeReviewer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=version_info,
    icon=['src\\aicodereviewer\\assets\\icon.ico'],
)
