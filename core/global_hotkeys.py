"""core/global_hotkeys.py — Windows 전역 단축키(앱이 포커스 없어도 동작).

PyQt6 자체로는 전역 단축키를 못 잡으므로 Win32 RegisterHotKey 를 ctypes 로 호출하고,
WM_HOTKEY 메시지를 QAbstractNativeEventFilter 로 받아 콜백을 부른다(권장 방식).
Windows 가 아니면 register 는 조용히 무시된다(no-op).
"""
from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

from PyQt6.QtCore import QAbstractNativeEventFilter

log = logging.getLogger(__name__)

_WM_HOTKEY = 0x0312
_MOD = {"ALT": 0x0001, "CTRL": 0x0002, "SHIFT": 0x0004, "META": 0x0008}
_MOD_NOREPEAT = 0x4000

# Qt 키 이름 → Win32 Virtual-Key 코드(영문/숫자/F키 + 자주 쓰는 키)
_VK_SPECIAL = {
    "SPACE": 0x20, "TAB": 0x09, "RETURN": 0x0D, "ENTER": 0x0D, "ESC": 0x1B,
    "HOME": 0x24, "END": 0x23, "INSERT": 0x2D, "DELETE": 0x2E,
    "PGUP": 0x21, "PGDOWN": 0x22, "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
}


def _parse(seq: str) -> tuple[int, int] | None:
    """'Ctrl+Shift+T' → (modifiers, vk). 파싱 실패 시 None."""
    if not seq:
        return None
    parts = [p.strip() for p in seq.split("+") if p.strip()]
    if not parts:
        return None
    *mods, key = parts
    mod_flags = 0
    for m in mods:
        flag = _MOD.get(m.upper())
        if flag is None:
            return None
        mod_flags |= flag
    k = key.upper()
    if len(k) == 1 and (k.isalpha() or k.isdigit()):
        vk = ord(k)
    elif k.startswith("F") and k[1:].isdigit() and 1 <= int(k[1:]) <= 24:
        vk = 0x70 + int(k[1:]) - 1
    elif k in _VK_SPECIAL:
        vk = _VK_SPECIAL[k]
    else:
        return None
    if mod_flags == 0:  # 전역 단축키는 수식키 필수(오작동 방지)
        return None
    return mod_flags, vk


class GlobalHotkeys(QAbstractNativeEventFilter):
    """앱에 하나만 두고 install 한 뒤, register(seq, callback) 로 등록한다."""

    def __init__(self, app):
        super().__init__()
        self._app = app
        self._callbacks: dict[int, callable] = {}
        self._next_id = 1
        self._enabled = sys.platform == "win32"
        if self._enabled:
            self._user32 = ctypes.windll.user32
            app.installNativeEventFilter(self)

    def register(self, seq: str, callback) -> bool:
        """seq 조합을 등록. 성공 True. 미지원/중복/충돌 시 False."""
        if not self._enabled:
            return False
        parsed = _parse(seq)
        if parsed is None:
            return False
        mods, vk = parsed
        hk_id = self._next_id
        if not self._user32.RegisterHotKey(None, hk_id, mods | _MOD_NOREPEAT, vk):
            log.warning("RegisterHotKey 실패: %s", seq)
            return False
        self._callbacks[hk_id] = callback
        self._next_id += 1
        return True

    def unregister_all(self) -> None:
        if not self._enabled:
            return
        for hk_id in list(self._callbacks):
            self._user32.UnregisterHotKey(None, hk_id)
        self._callbacks.clear()

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (Qt 시그니처)
        if self._enabled and event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == _WM_HOTKEY:
                cb = self._callbacks.get(int(msg.wParam))
                if cb is not None:
                    cb()
        return False, 0
