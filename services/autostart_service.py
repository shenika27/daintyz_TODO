"""services/autostart_service.py — 로그인 시 자동 시작 토글.

Windows: HKCU\\...\\Run 레지스트리 값 등록/삭제.
기타 OS: 안전하게 no-op (지원 시 후속 확장).
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "CharacterTodo"


def _launch_command() -> str:
    if getattr(sys, "frozen", False):  # PyInstaller exe
        return f'"{sys.executable}"'
    script = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{sys.executable}" "{script}"'


class AutostartService:
    @property
    def supported(self) -> bool:
        return sys.platform.startswith("win")

    def is_enabled(self) -> bool:
        if not self.supported:
            return False
        import winreg  # type: ignore

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
                winreg.QueryValueEx(k, _VALUE_NAME)
            return True
        except FileNotFoundError:
            return False
        except OSError:
            return False

    def set_enabled(self, enabled: bool) -> None:
        if not self.supported:
            log.info("Autostart not supported on %s", sys.platform)
            return
        import winreg  # type: ignore

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            if enabled:
                winreg.SetValueEx(k, _VALUE_NAME, 0, winreg.REG_SZ, _launch_command())
                log.info("Autostart enabled")
            else:
                try:
                    winreg.DeleteValue(k, _VALUE_NAME)
                    log.info("Autostart disabled")
                except FileNotFoundError:
                    pass
