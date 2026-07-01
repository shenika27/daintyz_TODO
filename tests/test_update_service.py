import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import update_service


def test_canonical_exe_path_migrates_versioned_onefile_name():
    current = Path(r"C:\Apps\CharacterTodo-onefile-0.4.4.exe")

    assert update_service._canonical_exe_path(current) == Path(
        r"C:\Apps\CharacterTodo.exe"
    )


def test_canonical_exe_path_keeps_fixed_name():
    current = Path(r"C:\Apps\CharacterTodo.exe")

    assert update_service._canonical_exe_path(current) == current


def test_ensure_canonical_exe_copy_creates_fixed_name_for_old_run():
    old_frozen = getattr(sys, "frozen", None)
    old_executable = sys.executable
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        old_exe = folder / "CharacterTodo-onefile-0.4.4.exe"
        fixed_exe = folder / "CharacterTodo.exe"
        old_exe.write_bytes(b"new-version")
        try:
            sys.frozen = True
            sys.executable = str(old_exe)

            assert update_service.ensure_canonical_exe_copy() == fixed_exe
            assert fixed_exe.read_bytes() == b"new-version"
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
