import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import autostart_service


def test_command_target_reads_quoted_exe_path():
    command = r'"C:\Apps\CharacterTodo-onefile-0.4.4.exe"'

    assert (
        autostart_service._command_target(command)
        == r"C:\Apps\CharacterTodo-onefile-0.4.4.exe"
    )


def test_commands_equivalent_ignores_case_for_same_target():
    left = r'"C:\Apps\CharacterTodo.exe"'
    right = r'"c:\apps\charactertodo.exe"'

    assert autostart_service._commands_equivalent(left, right)


def test_commands_equivalent_detects_old_versioned_target():
    old = r'"C:\Apps\CharacterTodo-onefile-0.4.4.exe"'
    current = r'"C:\Apps\CharacterTodo.exe"'

    assert not autostart_service._commands_equivalent(old, current)


def test_commands_equivalent_compares_development_script_path():
    old = r'"C:\Python313\python.exe" "C:\Old\main.py"'
    current = r'"C:\Python313\python.exe" "C:\Apps\main.py"'

    assert not autostart_service._commands_equivalent(old, current)


def test_repair_skips_development_run():
    class Probe(autostart_service.AutostartService):
        def registered_command(self):
            raise AssertionError("registry should not be touched")

    assert Probe().repair_if_registered() is False


def test_launch_command_prefers_existing_fixed_exe_for_frozen_run():
    old_frozen = getattr(sys, "frozen", None)
    old_executable = sys.executable
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        old_exe = folder / "CharacterTodo-onefile-0.4.4.exe"
        fixed_exe = folder / "CharacterTodo.exe"
        old_exe.write_bytes(b"old")
        fixed_exe.write_bytes(b"fixed")
        try:
            sys.frozen = True
            sys.executable = str(old_exe)

            assert autostart_service._launch_command() == f'"{fixed_exe}"'
        finally:
            sys.executable = old_executable
            if old_frozen is None:
                delattr(sys, "frozen")
            else:
                sys.frozen = old_frozen


def test_shortcut_roundtrip_reads_target_and_args():
    if not sys.platform.startswith("win"):
        return  # 시작폴더 바로가기는 Windows 전용
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "CharacterTodo.exe"
        target.write_bytes(b"x")
        lnk = Path(tmp) / "CharacterTodo.lnk"
        autostart_service._write_shortcut(lnk, str(target), '"C:\\a b\\main.py"')
        back = autostart_service._read_shortcut(lnk)
        assert back is not None
        got_target, got_args = back
        assert autostart_service._norm_path(got_target) == autostart_service._norm_path(
            str(target)
        )
        assert got_args == '"C:\\a b\\main.py"'


def test_enable_disable_and_repair_via_shortcut():
    if not sys.platform.startswith("win"):
        return
    with tempfile.TemporaryDirectory() as tmp:
        startup = Path(tmp) / "Startup"
        startup.mkdir()
        exe = Path(tmp) / "CharacterTodo.exe"
        exe.write_bytes(b"x")

        orig_startup = autostart_service._startup_dir
        autostart_service._startup_dir = lambda: startup
        old_frozen = getattr(sys, "frozen", None)
        old_exec = sys.executable
        sys.frozen = True
        sys.executable = str(exe)
        try:
            svc = autostart_service.AutostartService()
            assert svc.is_enabled() is False
            svc.set_enabled(True)
            assert svc.is_enabled() is True
            assert svc.repair_if_registered() is False  # 최신이라 손댈 것 없음

            old_exe = Path(tmp) / "CharacterTodo-onefile-0.4.4.exe"
            old_exe.write_bytes(b"y")
            autostart_service._write_shortcut(
                autostart_service._shortcut_path(), str(old_exe), ""
            )
            assert svc.is_enabled() is False  # 옛 경로 → 불일치
            assert svc.repair_if_registered() is True
            assert svc.is_enabled() is True

            svc.set_enabled(False)
            assert svc.is_enabled() is False
        finally:
            autostart_service._startup_dir = orig_startup
            sys.executable = old_exec
            if old_frozen is None:
                delattr(sys, "frozen")
            else:
                sys.frozen = old_frozen


def test_migrate_creates_shortcut_and_clears_registry():
    if not sys.platform.startswith("win"):
        return
    with tempfile.TemporaryDirectory() as tmp:
        startup = Path(tmp) / "Startup"
        startup.mkdir()
        exe = Path(tmp) / "CharacterTodo.exe"
        exe.write_bytes(b"x")

        orig_startup = autostart_service._startup_dir
        autostart_service._startup_dir = lambda: startup
        old_frozen = getattr(sys, "frozen", None)
        old_exec = sys.executable
        sys.frozen = True
        sys.executable = str(exe)
        deleted = {"called": False}
        try:
            svc = autostart_service.AutostartService()
            # 옛 Run 값이 있고, 삭제 호출을 가로채 실제 레지스트리는 건드리지 않음
            svc._legacy_registry_command = lambda: r'"C:\Old\CharacterTodo.exe"'
            svc._delete_legacy_registry = lambda: deleted.__setitem__("called", True)

            assert svc.migrate_legacy_registry() is True
            assert svc.is_enabled() is True          # 바로가기로 이전됨
            assert deleted["called"] is True         # 레지스트리 정리 호출됨

            # 옛 값이 없으면 마이그레이션은 no-op
            svc._legacy_registry_command = lambda: None
            assert svc.migrate_legacy_registry() is False
        finally:
            autostart_service._startup_dir = orig_startup
            sys.executable = old_exec
            if old_frozen is None:
                delattr(sys, "frozen")
            else:
                sys.frozen = old_frozen


def _run_all():
    fns = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print(f"{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
