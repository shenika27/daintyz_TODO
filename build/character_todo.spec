# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — Windows 빌드용.
#   build\build.bat 에서 호출됨. 프로젝트 루트에서 실행한다고 가정.
import os

block_cipher = None
ROOT = os.path.abspath(os.getcwd())

datas = [
    (os.path.join(ROOT, "data", "migrations"), os.path.join("data", "migrations")),
    (os.path.join(ROOT, "resources"), "resources"),
    (os.path.join(ROOT, "VERSION"), "."),
]

icon_path = os.path.join(ROOT, "resources", "app.ico")
icon = icon_path if os.path.exists(icon_path) else None

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CharacterTodo",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # GUI 앱: 콘솔 창 숨김
    icon=icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="CharacterTodo",
)
