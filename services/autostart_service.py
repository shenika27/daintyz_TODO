"""services/autostart_service.py — 로그인 시 자동 시작 토글.

Windows: 시작프로그램 폴더(shell:startup)에 바로가기(.lnk) 생성/삭제.
과거에는 HKCU\\...\\Run 레지스트리 값을 썼으나, 일부 백신(V3 등)이
"Run 키에 자기 자신을 등록" 하는 동작을 지속성 악성행위(Persistence/AutoRun)
로 오탐했다. 시작폴더 바로가기는 사용자가 직접 보고 지울 수 있는 표준 방식이라
행위 탐지에 훨씬 덜 걸린다. 기존 사용자의 Run 값은 시작 시 마이그레이션으로 제거한다.

기타 OS: 안전하게 no-op (지원 시 후속 확장).
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# 과거 방식(레지스트리)에서 남은 값을 정리하기 위한 상수 — 신규 등록에는 쓰지 않는다.
_LEGACY_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "CharacterTodo"

_SHORTCUT_NAME = "CharacterTodo.lnk"


def _launch_target_and_args() -> tuple[str, str]:
    """자동시작이 실행해야 할 (실행파일, 인자) 쌍."""
    if getattr(sys, "frozen", False):  # PyInstaller exe
        exe = Path(sys.executable).resolve()
        fixed = exe.with_name("CharacterTodo.exe")
        target = fixed if fixed.exists() else exe
        return str(target), ""
    script = Path(__file__).resolve().parent.parent / "main.py"
    return sys.executable, f'"{script}"'


def _launch_command() -> str:
    """레지스트리 비교용 결합 명령 문자열(마이그레이션 시 옛 값 비교에 사용)."""
    target, args = _launch_target_and_args()
    return f'"{target}" {args}'.strip()


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


def _command_target(command: str) -> str:
    parts = _command_parts(command)
    return parts[0] if parts else ""


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


# ---------------------------------------------------------------------------
# Windows 시작폴더 바로가기(.lnk) — 종속성 없이 COM(IShellLink)을 ctypes 로 호출.
# ---------------------------------------------------------------------------
def _startup_dir() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _shortcut_path() -> Path:
    return _startup_dir() / _SHORTCUT_NAME


def _write_shortcut(lnk: Path, target: str, arguments: str = "") -> None:
    import ctypes
    from ctypes import wintypes  # noqa: F401  (ensures wintypes loaded)

    ole32 = ctypes.windll.ole32

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong),
            ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    def guid(s: str) -> GUID:
        g = GUID()
        ole32.CLSIDFromString(ctypes.c_wchar_p(s), ctypes.byref(g))
        return g

    CLSID_ShellLink = "{00021401-0000-0000-C000-000000000046}"
    IID_IShellLinkW = "{000214F9-0000-0000-C000-000000000046}"
    IID_IPersistFile = "{0000010B-0000-0000-C000-000000000046}"
    CLSCTX_INPROC_SERVER = 1

    def call(this, index, *args, argtypes=(), restype=ctypes.HRESULT):
        vtbl = ctypes.cast(this, ctypes.POINTER(ctypes.c_void_p))[0]
        func = ctypes.cast(vtbl, ctypes.POINTER(ctypes.c_void_p))[index]
        proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
        return proto(func)(this, *args)

    ole32.CoInitialize(None)
    link = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(
        ctypes.byref(guid(CLSID_ShellLink)),
        None,
        CLSCTX_INPROC_SERVER,
        ctypes.byref(guid(IID_IShellLinkW)),
        ctypes.byref(link),
    )
    if hr != 0:
        raise OSError(f"CoCreateInstance(ShellLink) failed: {hr:#010x}")
    try:
        # IShellLinkW::SetPath(20), SetArguments(11), SetWorkingDirectory(9)
        call(link, 20, ctypes.c_wchar_p(target), argtypes=(ctypes.c_wchar_p,))
        if arguments:
            call(link, 11, ctypes.c_wchar_p(arguments), argtypes=(ctypes.c_wchar_p,))
        workdir = str(Path(target).parent)
        call(link, 9, ctypes.c_wchar_p(workdir), argtypes=(ctypes.c_wchar_p,))

        # QueryInterface(IPersistFile) → Save
        persist = ctypes.c_void_p()
        call(
            link, 0,
            ctypes.byref(guid(IID_IPersistFile)), ctypes.byref(persist),
            argtypes=(ctypes.c_void_p, ctypes.c_void_p),
        )
        try:
            lnk.parent.mkdir(parents=True, exist_ok=True)
            # IPersistFile::Save(6): (pszFileName, fRemember)
            call(
                persist, 6,
                ctypes.c_wchar_p(str(lnk)), ctypes.c_int(1),
                argtypes=(ctypes.c_wchar_p, ctypes.c_int),
            )
        finally:
            call(persist, 2, argtypes=(), restype=ctypes.c_ulong)  # Release
    finally:
        call(link, 2, argtypes=(), restype=ctypes.c_ulong)  # Release


def _read_shortcut(lnk: Path) -> tuple[str, str] | None:
    """.lnk 의 (대상, 인자)를 읽는다. 실패 시 None."""
    if not lnk.exists():
        return None
    import ctypes

    ole32 = ctypes.windll.ole32
    MAX = 1024

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong),
            ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    def guid(s: str) -> GUID:
        g = GUID()
        ole32.CLSIDFromString(ctypes.c_wchar_p(s), ctypes.byref(g))
        return g

    CLSID_ShellLink = "{00021401-0000-0000-C000-000000000046}"
    IID_IShellLinkW = "{000214F9-0000-0000-C000-000000000046}"
    IID_IPersistFile = "{0000010B-0000-0000-C000-000000000046}"
    CLSCTX_INPROC_SERVER = 1
    STGM_READ = 0

    def call(this, index, *args, argtypes=(), restype=ctypes.HRESULT):
        vtbl = ctypes.cast(this, ctypes.POINTER(ctypes.c_void_p))[0]
        func = ctypes.cast(vtbl, ctypes.POINTER(ctypes.c_void_p))[index]
        proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
        return proto(func)(this, *args)

    ole32.CoInitialize(None)
    link = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(
        ctypes.byref(guid(CLSID_ShellLink)),
        None,
        CLSCTX_INPROC_SERVER,
        ctypes.byref(guid(IID_IShellLinkW)),
        ctypes.byref(link),
    )
    if hr != 0:
        return None
    try:
        persist = ctypes.c_void_p()
        call(
            link, 0,
            ctypes.byref(guid(IID_IPersistFile)), ctypes.byref(persist),
            argtypes=(ctypes.c_void_p, ctypes.c_void_p),
        )
        try:
            # IPersistFile::Load(5): (pszFileName, dwMode)
            call(
                persist, 5,
                ctypes.c_wchar_p(str(lnk)), ctypes.c_ulong(STGM_READ),
                argtypes=(ctypes.c_wchar_p, ctypes.c_ulong),
            )
        finally:
            call(persist, 2, argtypes=(), restype=ctypes.c_ulong)

        buf = ctypes.create_unicode_buffer(MAX)
        # IShellLinkW::GetPath(3): (buf, cch, WIN32_FIND_DATA*, flags)
        # flags=SLGP_RAWPATH(4): 저장된 원본 경로를 그대로 반환(링크 해석/네트워크 조회 회피).
        SLGP_RAWPATH = 4
        call(
            link, 3,
            buf, ctypes.c_int(MAX), None, ctypes.c_ulong(SLGP_RAWPATH),
            argtypes=(ctypes.c_wchar_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong),
        )
        target = buf.value
        abuf = ctypes.create_unicode_buffer(MAX)
        # IShellLinkW::GetArguments(10): (buf, cch)
        call(
            link, 10,
            abuf, ctypes.c_int(MAX),
            argtypes=(ctypes.c_wchar_p, ctypes.c_int),
        )
        return target, abuf.value
    except OSError:
        return None
    finally:
        call(link, 2, argtypes=(), restype=ctypes.c_ulong)


class AutostartService:
    @property
    def supported(self) -> bool:
        return sys.platform.startswith("win")

    def is_enabled(self) -> bool:
        current = _read_shortcut(_shortcut_path())
        if not current:
            return False
        target, args = _launch_target_and_args()
        want = f'"{target}" {args}'.strip()
        have = f'"{current[0]}" {current[1]}'.strip()
        return _commands_equivalent(want, have)

    def set_enabled(self, enabled: bool) -> None:
        if not self.supported:
            log.info("Autostart not supported on %s", sys.platform)
            return
        lnk = _shortcut_path()
        if enabled:
            target, args = _launch_target_and_args()
            _write_shortcut(lnk, target, args)
            log.info("Autostart enabled (shortcut): %s", lnk)
        else:
            try:
                lnk.unlink()
                log.info("Autostart disabled (shortcut removed)")
            except FileNotFoundError:
                pass

    def repair_if_registered(self) -> bool:
        """등록돼 있던 바로가기가 옛 exe 이름을 가리키면 현재 경로로 갱신."""
        if not getattr(sys, "frozen", False):
            return False
        current = _read_shortcut(_shortcut_path())
        if not current:
            return False
        target, args = _launch_target_and_args()
        want = f'"{target}" {args}'.strip()
        have = f'"{current[0]}" {current[1]}'.strip()
        if _commands_equivalent(want, have):
            return False
        self.set_enabled(True)
        log.info("Autostart shortcut repaired: %s -> %s", have, want)
        return True

    # ------------------------------------------------------------------
    # 레거시 마이그레이션: 과거 HKCU\Run 값 제거 + 켜져 있었으면 .lnk 로 이전.
    # ------------------------------------------------------------------
    def _legacy_registry_command(self) -> str | None:
        if not self.supported:
            return None
        import winreg  # type: ignore

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _LEGACY_RUN_KEY) as k:
                value, _ = winreg.QueryValueEx(k, _VALUE_NAME)
            return str(value)
        except FileNotFoundError:
            return None
        except OSError:
            return None

    def _delete_legacy_registry(self) -> None:
        import winreg  # type: ignore

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _LEGACY_RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as k:
                winreg.DeleteValue(k, _VALUE_NAME)
        except FileNotFoundError:
            pass
        except OSError:
            log.warning("레거시 자동시작 레지스트리 값 삭제 실패", exc_info=True)

    def migrate_legacy_registry(self) -> bool:
        """옛 Run 레지스트리 값이 있으면 시작폴더 바로가기로 이전하고 값을 삭제.

        반환: 마이그레이션이 실제로 일어났으면 True.
        """
        if not self.supported:
            return False
        legacy = self._legacy_registry_command()
        if legacy is None:
            return False
        # Run 값이 있었다는 건 자동시작이 켜져 있었다는 뜻 → 바로가기로 재등록.
        if not _read_shortcut(_shortcut_path()):
            try:
                self.set_enabled(True)
            except OSError:
                log.warning("자동시작 바로가기 생성 실패(마이그레이션)", exc_info=True)
        self._delete_legacy_registry()
        log.info("자동시작을 레지스트리 → 시작폴더 바로가기로 마이그레이션함")
        return True

    def sync_on_startup(self) -> bool:
        """앱 시작 시 1회 호출: 레거시 마이그레이션 후 바로가기 경로 보정."""
        migrated = self.migrate_legacy_registry()
        repaired = self.repair_if_registered()
        return migrated or repaired
