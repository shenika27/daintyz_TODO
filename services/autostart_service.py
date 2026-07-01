"""services/autostart_service.py — 로그인 시 자동 시작 토글.

Windows: HKCU\\...\\Run 레지스트리 값 등록/삭제.
기타 OS: 안전하게 no-op (지원 시 후속 확장).
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "CharacterTodo"


def _launch_command() -> str:
    if getattr(sys, "frozen", False):  # PyInstaller exe
        exe = Path(sys.executable).resolve()
        fixed = exe.with_name("CharacterTodo.exe")
        return f'"{fixed if fixed.exists() else exe}"'
    script = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{sys.executable}" "{script}"'


def _command_target(command: str) -> str:
    parts = _command_parts(command)
    return parts[0] if parts else ""


def _command_parts(command: str) -> list[str]:
    command = command.strip()
    if not command:
        return []

    parts: list[str] = []
    current: list[str] = []
    in_quote = False
    for ch in command:
        if ch == '"':
            in_quote = not in_quote
            continue
        if ch.isspace() and not in_quote:
            if current:
                parts.append("".join(current))
                current = []
            continue
        current.append(ch)
    if current:
        parts.append("".join(current))
    return parts


def _norm_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.expandvars(path)))


def _commands_equivalent(left: str, right: str) -> bool:
    left_parts = _command_parts(left)
    right_parts = _command_parts(right)
    if not left_parts or not right_parts:
        return left.strip() == right.strip()
    if len(left_parts) != len(right_parts):
        return False
    return all(_norm_path(a) == _norm_path(b) for a, b in zip(left_parts, right_parts))


class AutostartService:
    @property
    def supported(self) -> bool:
        return sys.platform.startswith("win")

    def is_enabled(self) -> bool:
        command = self.registered_command()
        return bool(command and _commands_equivalent(command, _launch_command()))

    def registered_command(self) -> str | None:
        if not self.supported:
            return None
        import winreg  # type: ignore

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
                value, _value_type = winreg.QueryValueEx(k, _VALUE_NAME)
            return str(value)
        except FileNotFoundError:
            return None
        except OSError:
            return None

    def repair_if_registered(self) -> bool:
        """Refresh an existing Run entry when it points at an older exe name."""
        if not getattr(sys, "frozen", False):
            return False
        command = self.registered_command()
        if not command:
            return False
        current = _launch_command()
        if _commands_equivalent(command, current):
            return False
        self.set_enabled(True)
        log.info("Autostart command repaired: %s -> %s", command, current)
        return True

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
