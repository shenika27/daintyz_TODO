"""services/update_service.py — 업데이트 확인 및 자동 설치 서비스.

version.json 형식:
    {"version": "0.4.7", "download_url": "https://..."}
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, NamedTuple

log = logging.getLogger(__name__)

# GitHub Releases 의 latest 릴리즈에 올라간 version.json 을 항상 가리키는 안정 URL.
# 새 버전 릴리즈 때마다 자동으로 갱신되므로 이 값은 바꿀 필요 없습니다.
UPDATE_CHECK_URL: str = (
    "https://github.com/shenika27/daintyz_TODO"
    "/releases/latest/download/version.json"
)
# 자동 교체가 불가할 때(설치판 등) 사용자에게 안내할 릴리즈 페이지.
RELEASES_PAGE_URL: str = "https://github.com/shenika27/daintyz_TODO/releases/latest"
# 최신 릴리즈 메타(패치노트 본문 등)를 읽는 GitHub API.
API_LATEST_URL: str = (
    "https://api.github.com/repos/shenika27/daintyz_TODO/releases/latest"
)


class UpdateNeedsManualInstall(Exception):
    """설치 위치에 쓸 수 없어 자동 교체가 불가한 경우(예: Program Files 설치판)."""


class UpdateInfo(NamedTuple):
    version: str
    download_url: str


class ReleaseNotes(NamedTuple):
    version: str
    published_at: str  # YYYY-MM-DD
    body: str          # 릴리즈 본문(마크다운)


def _parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.strip().lstrip("v").split("."))
    except Exception:  # noqa: BLE001
        return (0,)


def current_version() -> str:
    from core import paths

    try:
        return (paths.app_root() / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:  # noqa: BLE001
        return "0.0.0"


def check_update() -> tuple[str, UpdateInfo | None]:
    """최신 version.json 을 읽어 업데이트 확인 결과를 (status, info) 로 반환.

    status: "update"(새 버전 있음) / "latest"(최신 버전) / "error"(네트워크·기타 오류).
    """
    if not UPDATE_CHECK_URL:
        return "error", None
    import urllib.request

    try:
        req = urllib.request.Request(
            UPDATE_CHECK_URL,
            headers={"User-Agent": "CharacterTodo-Updater"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        latest: str = data["version"]
        url: str = data["download_url"]
        if _parse_version(latest) > _parse_version(current_version()):
            return "update", UpdateInfo(version=latest, download_url=url)
        return "latest", None
    except Exception as e:  # noqa: BLE001
        log.warning("업데이트 확인 실패: %s", e)
        return "error", None


def fetch_release_notes() -> tuple[str, ReleaseNotes | None]:
    """최신 릴리즈 패치노트를 (status, notes) 로 반환.

    status: "ok"(notes 있음) / "not_found"(아직 게시된 릴리즈 없음, HTTP 404)
            / "error"(네트워크·기타 오류).
    """
    import urllib.error
    import urllib.request

    try:
        req = urllib.request.Request(
            API_LATEST_URL,
            headers={
                "User-Agent": "CharacterTodo-Updater",
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        tag = data.get("tag_name") or data.get("name") or ""
        return "ok", ReleaseNotes(
            version=tag.lstrip("v"),
            published_at=(data.get("published_at") or "")[:10],
            body=(data.get("body") or "").strip(),
        )
    except urllib.error.HTTPError as e:
        # 404 = 아직 릴리즈가 없음(리포는 정상). 그 외 HTTP 오류는 error 로.
        if e.code == 404:
            return "not_found", None
        log.warning("패치노트 조회 실패(HTTP %s): %s", e.code, e)
        return "error", None
    except Exception as e:  # noqa: BLE001
        log.warning("패치노트 조회 실패: %s", e)
        return "error", None


def download_update(
    url: str,
    progress_cb: Callable[[int, int], None] | None = None,
) -> Path:
    """URL 에서 새 EXE 를 다운로드해 임시 경로로 반환."""
    import urllib.request

    from core import paths

    dl_dir = paths.app_data_dir() / "update"
    dl_dir.mkdir(parents=True, exist_ok=True)
    dest = dl_dir / "CharacterTodo_new.exe"

    req = urllib.request.Request(url, headers={"User-Agent": "CharacterTodo-Updater"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 65536
        with dest.open("wb") as f:
            while True:
                buf = resp.read(chunk_size)
                if not buf:
                    break
                f.write(buf)
                downloaded += len(buf)
                if progress_cb:
                    progress_cb(downloaded, total)
    return dest


def _dir_writable(path: Path) -> bool:
    """디렉토리에 실제로 쓸 수 있는지 시험 파일로 확인."""
    probe = path / f".ct_write_test_{os.getpid()}"
    try:
        probe.write_text("x", encoding="ascii")
        probe.unlink()
        return True
    except OSError:
        return False


def apply_and_restart(new_exe: Path) -> None:
    """현재 EXE 를 새 파일로 교체하고 재시작.

    PyInstaller onefile 빌드에서만 동작. 개발 실행 시에는 건너뜁니다.
    실행 중인 EXE 는 교체 불가(Windows 잠금)이므로 현재 프로세스 종료를
    기다리는 임시 BAT 을 만들어 비동기로 실행한 뒤 앱을 종료합니다.

    설치 위치가 쓰기 불가(예: 관리자 권한이 필요한 Program Files 설치판)이면
    조용히 구버전으로 되돌아가는 대신 UpdateNeedsManualInstall 을 던집니다.
    """
    if not getattr(sys, "frozen", False):
        log.warning("개발 실행 중 — EXE 교체 건너뜀. 새 파일: %s", new_exe)
        return

    current_exe = Path(sys.executable).resolve()
    if not _dir_writable(current_exe.parent):
        raise UpdateNeedsManualInstall(str(current_exe.parent))

    pid = os.getpid()

    # 종료 대기: PID 로 필터 후 이미지명(CharacterTodo)까지 확인해 PID 재사용 오탐 방지.
    # 교체는 백신/핸들 잠금으로 잠깐 실패할 수 있어 최대 15회 재시도한다.
    # 끝내 실패하면(권한 등) 받은 새 파일을 지우지 않고 남겨 구버전을 그대로 재실행한다.
    bat_lines = [
        "@echo off",
        # PyInstaller onefile 은 실행 중 자기 임시 폴더(_MEIxxxxx) 경로를
        # _MEIPASS2 등 환경변수로 자식 프로세스에 물려준다. 이 BAT 은 그 자식이라
        # 값을 물려받은 상태다. 비우지 않으면 재시작된 새 exe 가 '이미 삭제된'
        # 옛 _MEI 폴더에서 python DLL 을 찾다 실패한다("Failed to load Python DLL").
        'set "_MEIPASS2="',
        'set "_PYI_APPLICATION_HOME_DIR="',
        'set "_PYI_ARCHIVE_INDEX="',
        'set "_PYI_PARENT_PROCESS_LEVEL="',
        f'set "TARGET={current_exe}"',
        f'set "NEW={new_exe}"',
        ":wait_loop",
        f'tasklist /FI "PID eq {pid}" /NH 2>nul | findstr /I "CharacterTodo" >nul',
        "if not errorlevel 1 ( timeout /t 1 /nobreak >nul & goto wait_loop )",
        "set TRIES=0",
        ":copy_loop",
        'copy /Y "%NEW%" "%TARGET%" >nul && goto copied',
        "set /a TRIES+=1",
        "if %TRIES% geq 15 goto copy_failed",
        "timeout /t 1 /nobreak >nul",
        "goto copy_loop",
        ":copied",
        'del /F /Q "%NEW%" >nul 2>&1',
        'start "" "%TARGET%"',
        "goto cleanup",
        ":copy_failed",
        'start "" "%TARGET%"',
        ":cleanup",
        'del /F /Q "%~f0"',
    ]

    bat_fd, bat_path = tempfile.mkstemp(suffix="_ct_update.bat")
    try:
        # cmd 는 BAT 을 시스템 ANSI 코드페이지로 읽으므로 mbcs 로 기록해야
        # 한글 사용자명 경로(C:\Users\홍길동\...)가 깨지지 않는다.
        with os.fdopen(bat_fd, "w", encoding="mbcs", errors="replace", newline="") as f:
            f.write("\r\n".join(bat_lines) + "\r\n")
        # 자식(cmd)이 현재 onefile 프로세스의 _MEIPASS2 등을 물려받지 않도록 제거.
        env = os.environ.copy()
        for var in (
            "_MEIPASS2",
            "_PYI_APPLICATION_HOME_DIR",
            "_PYI_ARCHIVE_INDEX",
            "_PYI_PARENT_PROCESS_LEVEL",
        ):
            env.pop(var, None)
        subprocess.Popen(
            ["cmd", "/c", bat_path],
            creationflags=subprocess.CREATE_NO_WINDOW,
            env=env,
        )
    except Exception:  # noqa: BLE001
        log.exception("업데이트 런처 실행 실패")
        raise
