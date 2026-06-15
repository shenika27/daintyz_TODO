"""data/todo_repository.py — todos 테이블 전담. SQLite 만 아는 곳."""
from __future__ import annotations

from datetime import datetime

from domain.models import Todo


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class TodoRepository:
    def __init__(self, db):
        self._db = db
        self.conn = db.conn

    # ── 조회 ────────────────────────────────────────────────
    def list_for_date(self, iso: str) -> list[Todo]:
        rows = self.conn.execute(
            "SELECT * FROM todos WHERE due_date = ? AND hidden = 0 "
            "ORDER BY sort_order, id",
            (iso,),
        ).fetchall()
        return [Todo.from_row(r) for r in rows]

    def get(self, todo_id: int) -> Todo | None:
        r = self.conn.execute(
            "SELECT * FROM todos WHERE id = ?", (todo_id,)
        ).fetchone()
        return Todo.from_row(r) if r else None

    def _next_order(self, iso: str) -> int:
        return self.conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM todos WHERE due_date = ?",
            (iso,),
        ).fetchone()[0]

    # ── 쓰기 ────────────────────────────────────────────────
    def add(self, content: str, iso: str) -> int:
        order = self._next_order(iso)
        cur = self.conn.execute(
            "INSERT INTO todos (content, due_date, sort_order, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (content, iso, order, _now(), _now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def set_content(self, todo_id: int, content: str) -> None:
        self.conn.execute(
            "UPDATE todos SET content = ?, updated_at = ? WHERE id = ?",
            (content, _now(), todo_id),
        )
        self.conn.commit()

    def set_completed(self, todo_id: int, completed: bool) -> None:
        self.conn.execute(
            "UPDATE todos SET completed = ?, updated_at = ? WHERE id = ?",
            (1 if completed else 0, _now(), todo_id),
        )
        self.conn.commit()

    def move(self, todo_id: int, new_iso: str, new_order: int | None = None) -> None:
        """날짜 간 이동(+선택적 정렬 위치)."""
        if new_order is None:
            new_order = self._next_order(new_iso)
        self.conn.execute(
            "UPDATE todos SET due_date = ?, sort_order = ?, updated_at = ? WHERE id = ?",
            (new_iso, new_order, _now(), todo_id),
        )
        self.conn.commit()

    def reorder(self, iso: str, ordered_ids: list[int]) -> None:
        """하루 안 순서 일괄 갱신."""
        for idx, tid in enumerate(ordered_ids):
            self.conn.execute(
                "UPDATE todos SET sort_order = ? WHERE id = ? AND due_date = ?",
                (idx, tid, iso),
            )
        self.conn.commit()

    def hide(self, todo_id: int) -> None:
        """반복 회차 제거: 삭제 대신 tombstone 으로 남겨 재생성 방지."""
        self.conn.execute(
            "UPDATE todos SET hidden = 1, updated_at = ? WHERE id = ?",
            (_now(), todo_id),
        )
        self.conn.commit()

    def unhide(self, todo_id: int) -> None:
        self.conn.execute(
            "UPDATE todos SET hidden = 0, updated_at = ? WHERE id = ?",
            (_now(), todo_id),
        )
        self.conn.commit()

    def delete(self, todo_id: int) -> None:
        self.conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        self.conn.commit()

    def insert_raw(self, todo: Todo) -> int:
        """undo(되돌리기)용: 삭제했던 일반 할일을 원래 값으로 복원."""
        cur = self.conn.execute(
            "INSERT INTO todos (content, due_date, completed, hidden, sort_order, "
            "remind_at, recurring_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                todo.content, todo.due_date, int(todo.completed), int(todo.hidden),
                todo.sort_order, todo.remind_at, todo.recurring_id, _now(), _now(),
            ),
        )
        self.conn.commit()
        return cur.lastrowid
