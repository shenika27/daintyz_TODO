"""core/paths.py — OS별 사용자 데이터 경로 및 리소스 경로 해석.

설치 경로(읽기전용일 수 있음)에 쓰지 않고, 사용자별 쓰기 가능 위치를 쓴다.
  Windows : %APPDATA%\\CharacterTodo
  기타    : ~/.local/share/CharacterTodo
PyInstaller 로 묶였을 때 번들 리소스는 sys._MEIPASS 에서 찾는다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "CharacterTodo"


def app_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return app_data_dir() / "todo.db"


def log_dir() -> Path:
    d = app_data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def project_root() -> Path:
    """소스 기준 루트(개발 실행 시)."""
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """번들/개발 양쪽에서 동작하는 리소스 디렉토리."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "resources"
    return project_root() / "resources"


def migrations_dir() -> Path:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "data" / "migrations"
    return project_root() / "data" / "migrations"
