# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — Windows 빌드용.
#   build\build.bat 에서 호출됨. 프로젝트 루트에서 실행한다고 가정.
import os

block_cipher = None
ROOT = os.path.abspath(os.getcwd())

with open(os.path.join(ROOT, "VERSION")) as _f:
    _version = _f.read().strip()

# 잠금(암호화) 빌드: resources.pak 이 생성돼 있으면 평문 png/gif/wav/flac 는 번들에서 제외하고
# 팩만 넣는다(app.ico·flag 등 비대상 리소스는 유지). build.bat / release.yml 이 이미지 변경
# N 일 때 build/pack_resources.py 로 팩을 만든 뒤 PyInstaller 를 호출한다.
_pak_path = os.path.join(ROOT, "resources", "resources.pak")
_encrypted = os.path.exists(_pak_path)

if _encrypted:
    _res_datas = []
    _res_root = os.path.join(ROOT, "resources")
    for _dir, _subdirs, _files in os.walk(_res_root):
        for _name in _files:
            if _name.lower().endswith((".png", ".gif", ".wav", ".flac")):
                continue  # 평문 이미지/사운드는 번들 제외(팩 안에 암호화되어 들어감)
            _src = os.path.join(_dir, _name)
            _rel = os.path.relpath(_dir, _res_root)
            _dest = "resources" if _rel == "." else os.path.join("resources", _rel)
            _res_datas.append((_src, _dest))
    resource_datas = _res_datas
else:
    resource_datas = [(os.path.join(ROOT, "resources"), "resources")]

datas = [
    (os.path.join(ROOT, "data", "migrations"), os.path.join("data", "migrations")),
    (os.path.join(ROOT, "VERSION"), "."),
    *resource_datas,
]

icon_path = os.path.join(ROOT, "resources", "app.ico")
icon = icon_path if os.path.exists(icon_path) else None

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    # 잠금 빌드는 런타임 복호화에 cryptography(AES-GCM) 사용 → 확실히 포함.
    hiddenimports=(["cryptography.hazmat.primitives.ciphers.aead"] if _encrypted else []),
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# onedir: 코드/DLL/리소스를 풀린 상태의 폴더(dist\CharacterTodo\)로 출력.
# 실행 시 런타임 압축 해제가 없어 시작이 빠르다(onefile 의 5~6초 추출 제거).
# 배포는 폴더 zip(무설치판) 또는 Inno Setup 설치본(설치판)으로 한다 — build.bat 참고.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # 바이너리는 COLLECT 로 폴더에 분리 → onedir
    name="CharacterTodo",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # UPX 압축 비활성 → 빌드 속도↑(대신 용량↑)
    console=False,          # GUI 앱: 콘솔 창 숨김
    icon=icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="CharacterTodo",   # 결과 폴더: dist\CharacterTodo\
)

# onefile: 단독 실행 단일 exe(dist\CharacterTodo.exe). 설치·압축해제 없이 그 자체로 실행.
# 단, 실행할 때마다 임시폴더 추출이 있어 시작이 느리다(빠른 시작은 onedir zip/설치판 사용).
exe_onefile = EXE(
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
    upx=False,
    runtime_tmpdir=None,
    console=False,
    icon=icon,
)
