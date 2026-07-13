import tempfile
from pathlib import Path

from data.database import Database
from data.todo_repository import TodoRepository


def _repo():
    tmp = tempfile.TemporaryDirectory()
    db = Database(Path(tmp.name) / "todo.db")
    return tmp, db, TodoRepository(db)


def test_deadline_todo_is_virtual_only_between_visible_from_and_deadline():
    tmp, db, repo = _repo()
    try:
        todo_id = repo.add(
            "보고서 작성",
            "2026-07-13",
            deadline_date="2026-07-15",
            visible_from_date="2026-07-13",
        )

        assert repo.list_for_date("2026-07-12") == []

        preview = repo.list_for_date("2026-07-13")
        assert len(preview) == 1
        assert preview[0].id == todo_id
        assert preview[0].is_virtual_deadline_preview is True

        due_day = repo.list_for_date("2026-07-15")
        assert len(due_day) == 1
        assert due_day[0].id == todo_id
        assert due_day[0].is_virtual_deadline_preview is False
    finally:
        db.close()
        tmp.cleanup()


def test_completed_deadline_todo_disappears_from_preview_dates_only():
    tmp, db, repo = _repo()
    try:
        todo_id = repo.add(
            "보고서 작성",
            "2026-07-13",
            deadline_date="2026-07-15",
            visible_from_date="2026-07-13",
        )

        repo.set_completed(todo_id, True)

        assert repo.list_for_date("2026-07-13") == []
        due_day = repo.list_for_date("2026-07-15")
        assert len(due_day) == 1
        assert due_day[0].completed is True
    finally:
        db.close()
        tmp.cleanup()


def test_todo_count_includes_future_and_deadlineless_overdue_only():
    tmp, db, repo = _repo()
    try:
        repo.add("미래 일반", "2026-07-15")
        repo.add("마감 없는 밀린 일", "2026-07-10")
        repo.add(
            "미래 마감",
            "2026-07-13",
            deadline_date="2026-07-16",
            visible_from_date="2026-07-13",
        )
        repo.add(
            "지난 마감",
            "2026-07-10",
            deadline_date="2026-07-13",
            visible_from_date="2026-07-10",
        )

        assert repo.count_visible_incomplete_for_today("2026-07-14") == 3
    finally:
        db.close()
        tmp.cleanup()


def _run_all():
    fns = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print(f"{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
