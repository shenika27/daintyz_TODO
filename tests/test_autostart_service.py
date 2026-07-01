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


def _run_all():
    fns = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print(f"{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
