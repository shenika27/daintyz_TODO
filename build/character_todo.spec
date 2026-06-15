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

# onefile: 모든 바이너리/리소스/코드를 단일 exe(dist\CharacterTodo.exe) 안에 포함.
# 실행 시에만 임시폴더로 풀려 동작 → 배포 시 exe 하나만 전달하면 됨.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="CharacterTodo",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # UPX 압축 비활성 → 빌드 속도↑(대신 exe 용량↑)
    runtime_tmpdir=None,
    console=False,          # GUI 앱: 콘솔 창 숨김
    icon=icon,
)
