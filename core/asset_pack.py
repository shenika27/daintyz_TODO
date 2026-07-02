"""core/asset_pack.py — 암호화된 리소스 팩(resources.pak) 런타임 로더.

잠금 배포(빌드 시 이미지 변경 N)에서는 resources\\ 의 이미지(png/gif)를 평문으로
번들하지 않고, AES-256-GCM 으로 암호화한 단일 팩 resources.pak 로만 넣는다.
이 모듈은 팩을 메모리에서 복호화해 파일명 → 원본 bytes 로 제공한다. 디스크에는
평문 이미지를 남기지 않는다.

개발 실행/일반 배포(팩 없음)에서는 is_encrypted_build() 가 False → 호출측이 기존
파일 기반 로딩을 그대로 쓴다.

팩 포맷(향후 유료 테마 프리셋 확장을 위해 버전·키모드 헤더를 둔다):
    MAGIC b"CTPK" (4)
    format_version (1)          현재 1
    key_mode (1)                0 = embedded(내장 임베드 키), 1 = online(서버 발급, 예약)
    pack_id_len (1) + pack_id   utf-8, 예: "builtin"
    nonce (12)
    ciphertext + tag            AESGCM(nonce, plaintext) 결과
평문(복호화 후):
    manifest_len (4, LE) | manifest(JSON utf-8) | blob0 | blob1 ...
    manifest = [{"name": "character_default.png", "off": 0, "len": 123}, ...]
"""
from __future__ import annotations

import json
import logging
import struct

from core import paths

log = logging.getLogger(__name__)

MAGIC = b"CTPK"
FORMAT_VERSION = 1
KEY_MODE_EMBEDDED = 0   # 내장 임베드 키(기본 이미지)
KEY_MODE_ONLINE = 1     # 서버 활성화로 발급(유료 프리셋 — 예약, 미구현)

_PAK_NAME = "resources.pak"

# 복호화 결과 캐시(파일명 → bytes). None = 아직 로드 안 함, {} = 팩 없음/실패.
_cache: dict[str, bytes] | None = None


def _pak_path():
    return paths.resource_dir() / _PAK_NAME


def is_encrypted_build() -> bool:
    """이 실행이 암호화 팩(resources.pak)을 포함한 잠금 빌드인지."""
    return _pak_path().exists()


def _embedded_key() -> bytes | None:
    """빌드 시 생성돼 바이트코드에 심긴 임베드 키. 없으면(개발 실행) None."""
    try:
        from core import _asset_key  # 빌드 시 생성, git 미포함
    except Exception:  # noqa: BLE001
        return None
    try:
        return _asset_key.asset_key()
    except Exception:  # noqa: BLE001
        log.exception("임베드 키 복원 실패")
        return None


def _decrypt_pack(raw: bytes) -> dict[str, bytes]:
    if raw[:4] != MAGIC:
        raise ValueError("팩 매직 불일치")
    ver = raw[4]
    if ver != FORMAT_VERSION:
        raise ValueError(f"지원하지 않는 팩 버전: {ver}")
    key_mode = raw[5]
    id_len = raw[6]
    pos = 7 + id_len  # pack_id 는 현재 로딩에 사용하지 않음(향후 팩 식별용)
    if key_mode != KEY_MODE_EMBEDDED:
        # 온라인 발급 키 모드(유료 프리셋)는 아직 미구현 — 내장 로더는 처리하지 않음.
        raise ValueError(f"미지원 키 모드: {key_mode}")

    key = _embedded_key()
    if key is None:
        raise ValueError("임베드 키 없음")

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = raw[pos:pos + 12]
    ct = raw[pos + 12:]
    plaintext = AESGCM(key).decrypt(nonce, ct, None)

    (manifest_len,) = struct.unpack_from("<I", plaintext, 0)
    m_start = 4
    m_end = m_start + manifest_len
    manifest = json.loads(plaintext[m_start:m_end].decode("utf-8"))
    blob_base = m_end
    out: dict[str, bytes] = {}
    for entry in manifest:
        off = blob_base + entry["off"]
        out[entry["name"]] = plaintext[off:off + entry["len"]]
    return out


def _load() -> dict[str, bytes]:
    global _cache
    if _cache is not None:
        return _cache
    path = _pak_path()
    if not path.exists():
        _cache = {}
        return _cache
    try:
        _cache = _decrypt_pack(path.read_bytes())
    except Exception:  # noqa: BLE001
        log.exception("리소스 팩 복호화 실패: %s", path)
        _cache = {}
    return _cache


def has(name: str) -> bool:
    return name in _load()


def get_bytes(name: str) -> bytes | None:
    """팩에서 파일명(예: 'character_default.png')의 원본 bytes. 없으면 None."""
    return _load().get(name)
