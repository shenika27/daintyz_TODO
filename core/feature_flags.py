"""core/feature_flags.py — 빌드 타임 기능 플래그.

소스를 수정하지 않고 resources/ 안의 마커 파일 유무로 켜고 끈다.
build.bat 이 환경변수(CHARACTER_EDIT)에 따라 빌드 직전 마커를 만들거나 지운다.
개발 실행(마커 없음)에서는 모든 기능이 켜진 상태가 기본값이다.
"""
from __future__ import annotations

from core import paths

_CHAR_EDIT_DISABLED_FLAG = "character_edit_disabled.flag"


def character_edit_enabled() -> bool:
    """사용자가 캐릭터 이미지를 바꿀 수 있는 빌드인지."""
    try:
        return not (paths.resource_dir() / _CHAR_EDIT_DISABLED_FLAG).exists()
    except Exception:  # noqa: BLE001
        return True
