"""build/pack_resources.py — 빌드 시 리소스 이미지를 암호화 팩으로 묶는다.

잠금 배포(이미지 변경 N)에서만 실행. 프로젝트 루트에서 호출한다고 가정.
  1. 임의 32B 키 생성
  2. resources\\*.png|gif 를 AES-256-GCM 단일 팩 resources\\resources.pak 로 암호화
  3. 키를 XOR 마스킹해 core\\_asset_key.py 로 생성(바이트코드에 심겨 배포됨)

키는 빌드마다 새로 만들고 파일로 보관하지 않는다(onefile 단일 exe 라 릴리즈 간
키 호환이 필요 없음 → GitHub Secret/키 백업 불필요). _asset_key.py 와 resources.pak
은 git 에 커밋하지 않는다(.gitignore).

팩 포맷은 core/asset_pack.py 의 설명과 일치해야 한다.
"""
from __future__ import annotations

import json
import os
import struct
import sys

MAGIC = b"CTPK"
FORMAT_VERSION = 1
KEY_MODE_EMBEDDED = 0
PACK_ID = "builtin"
_EXTS = (".png", ".gif")


def _build_plaintext(res_dir: str) -> tuple[bytes, list[dict]]:
    manifest = []
    blobs: list[bytes] = []
    off = 0
    for name in sorted(os.listdir(res_dir)):
        if not name.lower().endswith(_EXTS):
            continue
        with open(os.path.join(res_dir, name), "rb") as f:
            data = f.read()
        manifest.append({"name": name, "off": off, "len": len(data)})
        blobs.append(data)
        off += len(data)
    if not manifest:
        raise SystemExit("[pack] 암호화할 이미지(png/gif)가 없습니다.")
    manifest_bytes = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
    return b"".join([struct.pack("<I", len(manifest_bytes)), manifest_bytes, *blobs]), manifest


def _write_key_module(root: str, key: bytes) -> None:
    mask = os.urandom(len(key))
    masked = bytes(a ^ b for a, b in zip(key, mask))
    content = (
        "# AUTO-GENERATED at build time by build/pack_resources.py.\n"
        "# 편집·커밋 금지. 이 파일이 있으면 잠금(암호화) 빌드다.\n"
        f'_MASK = bytes.fromhex("{mask.hex()}")\n'
        f'_MASKED = bytes.fromhex("{masked.hex()}")\n\n\n'
        "def asset_key() -> bytes:\n"
        "    return bytes(a ^ b for a, b in zip(_MASKED, _MASK))\n"
    )
    with open(os.path.join(root, "core", "_asset_key.py"), "w", encoding="utf-8") as f:
        f.write(content)


def main() -> None:
    root = os.path.abspath(os.getcwd())
    res_dir = os.path.join(root, "resources")
    if not os.path.isdir(res_dir):
        raise SystemExit(f"[pack] resources 폴더 없음: {res_dir}")

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    plaintext, manifest = _build_plaintext(res_dir)
    key = os.urandom(32)
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext, None)

    pack_id = PACK_ID.encode("utf-8")
    header = MAGIC + bytes([FORMAT_VERSION, KEY_MODE_EMBEDDED, len(pack_id)]) + pack_id
    pak = header + nonce + ct

    pak_path = os.path.join(res_dir, "resources.pak")
    with open(pak_path, "wb") as f:
        f.write(pak)
    _write_key_module(root, key)

    print(f"[pack] {len(manifest)}개 이미지 → {pak_path} ({len(pak)} bytes)")
    print("[pack] core/_asset_key.py 생성됨")


if __name__ == "__main__":
    sys.exit(main())
