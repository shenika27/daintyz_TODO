"""data/todo_repository.py — todos 테이블 전담. SQLite 만 아는 곳."""
from __future__ import annotations

from datetime import datetime

from domain.models import RecurringRule, Todo


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

    def has_incomplete_before(self, iso: str) -> bool:
        """주어진 날짜 이전(< iso)에 미완료·미숨김 할일이 하나라도 있는지."""
        r = self.conn.execute(
            "SELECT 1 FROM todos WHERE due_date < ? AND completed = 0 AND hidden = 0 "
            "LIMIT 1",
            (iso,),
        ).fetchone()
        return r is not None

    def count_incomplete(self) -> int:
        """날짜와 무관하게 미완료·미숨김 할일 전체 개수."""
        r = self.conn.execute(
            "SELECT COUNT(*) FROM todos WHERE completed = 0 AND hidden = 0"
        ).fetchone()
        return r[0] if r else 0

    def latest_activity(self) -> str | None:
        """숨기지 않은 할일 중 가장 최근 created_at/updated_at. 없으면 None."""
        r = self.conn.execute(
            "SELECT MAX(updated_at) FROM todos WHERE hidden = 0"
        ).fetchone()
        return r[0] if r else None

    def incomplete_counts_before(self, iso: str) -> list[tuple[str, int]]:
        """주어진 날짜 이전(< iso)에 미완료 할일이 있는 날짜별 개수(날짜 오름차순)."""
        rows = self.conn.execute(
            "SELECT due_date, COUNT(*) AS c FROM todos "
            "WHERE due_date < ? AND completed = 0 AND hidden = 0 "
            "GROUP BY due_date ORDER BY due_date",
            (iso,),
        ).fetchall()
        return [(r["due_date"], r["c"]) for r in rows]

    def count_incomplete_regular_before(self, iso: str) -> int:
        """주어진 날짜 이전(< iso)의 미완료 일반 할일 개수."""
        r = self.conn.execute(
            "SELECT COUNT(*) FROM todos "
            "WHERE due_date < ? AND completed = 0 AND hidden = 0 AND recurring_id IS NULL",
            (iso,),
        ).fetchone()
        return r[0] if r else 0

    def incomplete_for_date(self, iso: str) -> list[Todo]:
        """해당 날짜의 미완료·미숨김 할일 스냅샷."""
        rows = self.conn.execute(
            "SELECT * FROM todos WHERE due_date = ? AND completed = 0 AND hidden = 0 "
            "ORDER BY sort_order, id",
            (iso,),
        ).fetchall()
        return [Todo.from_row(r) for r in rows]

    def incomplete_before(self, iso: str) -> list[Todo]:
        """주어진 날짜 이전(< iso)의 미완료·미숨김 할일 스냅샷."""
        rows = self.conn.execute(
            "SELECT * FROM todos WHERE due_date < ? AND completed = 0 AND hidden = 0 "
            "ORDER BY due_date, sort_order, id",
            (iso,),
        ).fetchall()
        return [Todo.from_row(r) for r in rows]

    def incomplete_regular_for_date(self, iso: str) -> list[Todo]:
        """해당 날짜의 미완료·미숨김 일반 할일 스냅샷."""
        rows = self.conn.execute(
            "SELECT * FROM todos "
            "WHERE due_date = ? AND completed = 0 AND hidden = 0 AND recurring_id IS NULL "
            "ORDER BY sort_order, id",
            (iso,),
        ).fetchall()
        return [Todo.from_row(r) for r in rows]

    def incomplete_regular_before(self, iso: str) -> list[Todo]:
        """주어진 날짜 이전(< iso)의 미완료·미숨김 일반 할일 스냅샷."""
        rows = self.conn.execute(
            "SELECT * FROM todos "
            "WHERE due_date < ? AND completed = 0 AND hidden = 0 AND recurring_id IS NULL "
            "ORDER BY due_date, sort_order, id",
            (iso,),
        ).fetchall()
        return [Todo.from_row(r) for r in rows]

    def list_by_ids(self, todo_ids: list[int]) -> list[Todo]:
        if not todo_ids:
            return []
        placeholders = ",".join("?" for _ in todo_ids)
        rows = self.conn.execute(
            f"SELECT * FROM todos WHERE id IN ({placeholders})",
            tuple(todo_ids),
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

    def add_after(self, content: str, iso: str, after_order: int) -> int:
        """같은 날짜에서 after_order 바로 뒤에 새 할일을 끼워 넣는다(복제용).
        뒤따르는 항목들의 sort_order 를 한 칸씩 밀어 정렬 순서를 보존한다."""
        self.conn.execute(
            "UPDATE todos SET sort_order = sort_order + 1 "
            "WHERE due_date = ? AND sort_order > ?",
            (iso, after_order),
        )
        cur = self.conn.execute(
            "INSERT INTO todos (content, due_date, sort_order, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (content, iso, after_order + 1, _now(), _now()),
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

    def complete_incomplete_for_date(self, iso: str) -> int:
        """해당 날짜의 미완료·미숨김 할일을 모두 완료 처리하고 변경 개수를 반환."""
        cur = self.conn.execute(
            "UPDATE todos SET completed = 1, updated_at = ? "
            "WHERE due_date = ? AND completed = 0 AND hidden = 0",
            (_now(), iso),
        )
        self.conn.commit()
        return cur.rowcount

    def complete_incomplete_before(self, iso: str) -> tuple[int, list[str]]:
        """주어진 날짜 이전의 미완료·미숨김 할일을 모두 완료 처리한다."""
        rows = self.conn.execute(
            "SELECT DISTINCT due_date FROM todos "
            "WHERE due_date < ? AND completed = 0 AND hidden = 0 "
            "ORDER BY due_date",
            (iso,),
        ).fetchall()
        dates = [r["due_date"] for r in rows]
        if not dates:
            return 0, []
        cur = self.conn.execute(
            "UPDATE todos SET completed = 1, updated_at = ? "
            "WHERE due_date < ? AND completed = 0 AND hidden = 0",
            (_now(), iso),
        )
        self.conn.commit()
        return cur.rowcount, dates

    def move(self, todo_id: int, new_iso: str, new_order: int | None = None) -> None:
        """날짜 간 이동(+선택적 정렬 위치)."""
        if new_order is None:
            new_order = self._next_order(new_iso)
        self.conn.execute(
            "UPDATE todos SET due_date = ?, sort_order = ?, updated_at = ? WHERE id = ?",
            (new_iso, new_order, _now(), todo_id),
        )
        self.conn.commit()

    def move_incomplete_regular_to_date(self, src_iso: str, dest_iso: str) -> int:
        """미완료 일반 할일만 dest_iso 끝으로 옮기고 변경 개수를 반환.

        반복 회차(recurring_id 있음)는 규칙과 화면 의미가 섞이지 않도록 이동하지 않는다.
        """
        rows = self.conn.execute(
            "SELECT id FROM todos "
            "WHERE due_date = ? AND completed = 0 AND hidden = 0 AND recurring_id IS NULL "
            "ORDER BY sort_order, id",
            (src_iso,),
        ).fetchall()
        if not rows:
            return 0

        next_order = self._next_order(dest_iso)
        now = _now()
        for offset, row in enumerate(rows):
            self.conn.execute(
                "UPDATE todos SET due_date = ?, sort_order = ?, updated_at = ? WHERE id = ?",
                (dest_iso, next_order + offset, now, row["id"]),
            )
        self.conn.commit()
        return len(rows)

    def move_incomplete_regular_before_to_date(self, before_iso: str, dest_iso: str) -> tuple[int, list[str]]:
        """before_iso 이전의 미완료 일반 할일을 dest_iso 끝으로 옮긴다."""
        rows = self.conn.execute(
            "SELECT id, due_date FROM todos "
            "WHERE due_date < ? AND completed = 0 AND hidden = 0 AND recurring_id IS NULL "
            "ORDER BY due_date, sort_order, id",
            (before_iso,),
        ).fetchall()
        if not rows:
            return 0, []

        dates = []
        seen = set()
        for row in rows:
            due = row["due_date"]
            if due not in seen:
                seen.add(due)
                dates.append(due)

        next_order = self._next_order(dest_iso)
        now = _now()
        for offset, row in enumerate(rows):
            self.conn.execute(
                "UPDATE todos SET due_date = ?, sort_order = ?, updated_at = ? WHERE id = ?",
                (dest_iso, next_order + offset, now, row["id"]),
            )
        self.conn.commit()
        return len(rows), dates

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

    def delete_by_recurring(self, rule_id: int) -> None:
        """해당 반복 규칙으로 생성된 모든 할일을 삭제(완료·숨김 포함)."""
        self.conn.execute("DELETE FROM todos WHERE recurring_id = ?", (rule_id,))
        self.conn.commit()

    def materialize_recurring(self, rule: RecurringRule, iso: str) -> bool:
        """반복 규칙 1회차를 todos 로 기록. 이미 존재하면(숨김 포함) 건너뛰고 False."""
        exists = self.conn.execute(
            "SELECT 1 FROM todos WHERE recurring_id = ? AND due_date = ? LIMIT 1",
            (rule.id, iso),
        ).fetchone()
        if exists:
            return False
        remind_at = f"{iso} {rule.remind_time}" if rule.remind_time else None
        self.conn.execute(
            "INSERT OR IGNORE INTO todos "
            "(content, due_date, sort_order, remind_at, recurring_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (rule.content, iso, self._next_order(iso), remind_at, rule.id, _now(), _now()),
        )
        self.conn.commit()
        return True

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

    def restore_existing(self, todos: list[Todo]) -> None:
        """undo(되돌리기)용: 살아 있는 할일 행들을 스냅샷 상태로 되돌린다."""
        now = _now()
        for todo in todos:
            self.conn.execute(
                "UPDATE todos SET content = ?, due_date = ?, completed = ?, hidden = ?, "
                "sort_order = ?, remind_at = ?, recurring_id = ?, updated_at = ? "
                "WHERE id = ?",
                (
                    todo.content,
                    todo.due_date,
                    int(todo.completed),
                    int(todo.hidden),
                    todo.sort_order,
                    todo.remind_at,
                    todo.recurring_id,
                    now,
                    todo.id,
                ),
            )
        self.conn.commit()
