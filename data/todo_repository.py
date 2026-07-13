"""data/todo_repository.py — todos 테이블 전담. SQLite 만 아는 곳."""
from __future__ import annotations

import re
from datetime import date, datetime

from domain.models import RecurringRule, Todo


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class TodoRepository:
    def __init__(self, db):
        self._db = db
        self.conn = db.conn

    def _todos_from_db_rows(self, rows) -> list[Todo]:
        return [Todo.from_row(r) for r in rows]

    def _virtual_deadline_previews(self, iso: str, pinned: bool | None = None) -> list[Todo]:
        where = (
            "hidden = 0 AND completed = 0 "
            "AND deadline_date IS NOT NULL "
            "AND visible_from_date IS NOT NULL "
            "AND visible_from_date <= ? AND deadline_date > ?"
        )
        params: list[object] = [iso, iso]
        if pinned is not None:
            where += " AND pinned = ?"
            params.append(1 if pinned else 0)
        rows = self.conn.execute(
            f"SELECT * FROM todos WHERE {where}",
            tuple(params),
        ).fetchall()
        todos = self._todos_from_db_rows(rows)
        for todo in todos:
            todo.is_virtual_deadline_preview = True
        return todos

    def _actual_rows_for_date(
        self,
        iso: str,
        pinned: bool | None = None,
        incomplete_only: bool = False,
    ):
        where = "due_date = ? AND hidden = 0"
        params: list[object] = [iso]
        if pinned is not None:
            where += " AND pinned = ?"
            params.append(1 if pinned else 0)
        if incomplete_only:
            where += " AND completed = 0"
        return self.conn.execute(
            f"SELECT * FROM todos WHERE {where}",
            tuple(params),
        ).fetchall()

    def _visible_for_date(
        self,
        iso: str,
        *,
        pinned: bool | None = None,
        priority_sort: bool = False,
        incomplete_actual_only: bool = False,
    ) -> list[Todo]:
        todos = self._todos_from_db_rows(
            self._actual_rows_for_date(
                iso,
                pinned=pinned,
                incomplete_only=incomplete_actual_only,
            )
        )
        todos.extend(self._virtual_deadline_previews(iso, pinned=pinned))
        return self._sort_visible_todos(todos, pinned=pinned, priority_sort=priority_sort)

    def _sort_visible_todos(
        self,
        todos: list[Todo],
        *,
        pinned: bool | None = None,
        priority_sort: bool = False,
    ) -> list[Todo]:
        if pinned is not None:
            if priority_sort:
                return sorted(todos, key=lambda t: (-t.priority, t.sort_order, t.id))
            return sorted(todos, key=lambda t: (t.sort_order, t.id))
        if priority_sort:
            return sorted(todos, key=lambda t: (-int(t.pinned), -t.priority, t.sort_order, t.id))
        return sorted(todos, key=lambda t: (-int(t.pinned), t.sort_order, t.id))

    # ── 조회 ────────────────────────────────────────────────
    def list_for_date(self, iso: str, priority_sort: bool = False) -> list[Todo]:
        return self._visible_for_date(iso, priority_sort=priority_sort)

    def pinned_for_date(self, iso: str) -> list[Todo]:
        return self._visible_for_date(
            iso,
            pinned=True,
            incomplete_actual_only=True,
        )

    def unpinned_for_date(self, iso: str, priority_sort: bool = False) -> list[Todo]:
        return self._visible_for_date(
            iso,
            pinned=False,
            priority_sort=priority_sort,
        )

    def pinned_count_for_date(self, iso: str) -> int:
        r = self.conn.execute(
            "SELECT COUNT(*) FROM todos "
            "WHERE due_date = ? AND hidden = 0 AND completed = 0 AND pinned = 1",
            (iso,),
        ).fetchone()
        return r[0] if r else 0

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

    def count_visible_incomplete_for_today(self, today_iso: str) -> int:
        """캐릭터 말풍선용: 오늘 이후 실제 할일 + 미래 마감 + 마감 없는 밀린 할일."""
        r = self.conn.execute(
            "SELECT COUNT(*) FROM todos "
            "WHERE completed = 0 AND hidden = 0 AND ("
            "due_date >= ? OR deadline_date >= ? "
            "OR (due_date < ? AND deadline_date IS NULL)"
            ")",
            (today_iso, today_iso, today_iso),
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

    def completed_items(self, query: str = "") -> list[Todo]:
        """완료·미숨김 할일 전체를 최근 날짜 우선으로 반환."""
        clause, params = self._completed_search_clause(query)
        where = "WHERE completed = 1 AND hidden = 0"
        if clause:
            where += f" AND ({clause})"
        rows = self.conn.execute(
            "SELECT * FROM todos "
            f"{where} "
            "ORDER BY due_date DESC, sort_order, id",
            params,
        ).fetchall()
        return [Todo.from_row(r) for r in rows]

    def completed_counts(self, query: str = "") -> list[tuple[str, int]]:
        """완료·미숨김 할일이 있는 날짜별 개수(최근 날짜 우선)."""
        clause, params = self._completed_search_clause(query)
        where = "WHERE completed = 1 AND hidden = 0"
        if clause:
            where += f" AND ({clause})"
        rows = self.conn.execute(
            "SELECT due_date, COUNT(*) AS c FROM todos "
            f"{where} "
            "GROUP BY due_date ORDER BY due_date DESC",
            params,
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

    def completed_for_date(self, iso: str) -> list[Todo]:
        """해당 날짜의 완료·미숨김 할일 스냅샷."""
        rows = self.conn.execute(
            "SELECT * FROM todos WHERE due_date = ? AND completed = 1 AND hidden = 0 "
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

    def _completed_search_clause(self, query: str) -> tuple[str, tuple]:
        query = query.strip()
        if not query:
            return "", ()

        date_clause = self._completed_date_search_clause(query)
        if date_clause is not None:
            return date_clause

        return "content LIKE ? ESCAPE '\\'", (self._like_pattern(query),)

    def _completed_date_search_clause(self, query: str) -> tuple[str, tuple] | None:
        if re.fullmatch(r"\d{4}", query):
            year = int(query)
            if year < 1:
                return None
            return "due_date >= ? AND due_date < ?", (
                f"{year:04d}-01-01",
                f"{year + 1:04d}-01-01",
            )

        if re.fullmatch(r"\d{4}-\d{2}", query):
            year_text, month_text = query.split("-")
            year = int(year_text)
            month = int(month_text)
            if year < 1 or not 1 <= month <= 12:
                return None
            start = date(year, month, 1)
            if month == 12:
                end = date(year + 1, 1, 1)
            else:
                end = date(year, month + 1, 1)
            return "due_date >= ? AND due_date < ?", (
                start.isoformat(),
                end.isoformat(),
            )

        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", query):
            try:
                exact = date.fromisoformat(query)
            except ValueError:
                return None
            return "due_date = ?", (exact.isoformat(),)

        return None

    def _like_pattern(self, text: str) -> str:
        escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    # ── 쓰기 ────────────────────────────────────────────────
    def add(
        self,
        content: str,
        iso: str,
        priority: int = 0,
        deadline_date: str | None = None,
        visible_from_date: str | None = None,
    ) -> int:
        due_iso = deadline_date or iso
        visible_iso = visible_from_date or (iso if deadline_date else None)
        order = self._next_order(due_iso)
        cur = self.conn.execute(
            "INSERT INTO todos (content, due_date, sort_order, priority, "
            "deadline_date, visible_from_date, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                content,
                due_iso,
                order,
                priority,
                deadline_date,
                visible_iso,
                _now(),
                _now(),
            ),
        )
        self.conn.commit()
        return cur.lastrowid

    def add_after(
        self,
        content: str,
        iso: str,
        after_order: int,
        priority: int = 0,
    ) -> int:
        """같은 날짜에서 after_order 바로 뒤에 새 할일을 끼워 넣는다(복제용).
        뒤따르는 항목들의 sort_order 를 한 칸씩 밀어 정렬 순서를 보존한다."""
        self.conn.execute(
            "UPDATE todos SET sort_order = sort_order + 1 "
            "WHERE due_date = ? AND sort_order > ?",
            (iso, after_order),
        )
        cur = self.conn.execute(
            "INSERT INTO todos (content, due_date, sort_order, priority, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (content, iso, after_order + 1, priority, _now(), _now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def add_many(self, contents: list[str], iso: str, priority: int = 0) -> int:
        """같은 날짜 끝에 여러 일반 할일을 미완료 상태로 추가하고 개수를 반환."""
        cleaned = [c.strip() for c in contents if c.strip()]
        if not cleaned:
            return 0
        next_order = self._next_order(iso)
        now = _now()
        for offset, content in enumerate(cleaned):
            self.conn.execute(
                "INSERT INTO todos (content, due_date, sort_order, priority, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (content, iso, next_order + offset, priority, now, now),
            )
        self.conn.commit()
        return len(cleaned)

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

    def set_priority(self, todo_id: int, priority: int) -> None:
        self.conn.execute(
            "UPDATE todos SET priority = ?, updated_at = ? WHERE id = ?",
            (priority, _now(), todo_id),
        )
        self.conn.commit()

    def set_pinned(self, todo_id: int, pinned: bool) -> None:
        self.conn.execute(
            "UPDATE todos SET pinned = ?, updated_at = ? WHERE id = ?",
            (1 if pinned else 0, _now(), todo_id),
        )
        self.conn.commit()

    def set_deadline(self, todo_id: int, visible_from_iso: str, deadline_iso: str) -> None:
        self.conn.execute(
            "UPDATE todos SET due_date = ?, deadline_date = ?, visible_from_date = ?, "
            "sort_order = ?, updated_at = ? WHERE id = ?",
            (
                deadline_iso,
                deadline_iso,
                visible_from_iso,
                self._next_order(deadline_iso),
                _now(),
                todo_id,
            ),
        )
        self.conn.commit()

    def clear_deadline(self, todo_id: int) -> None:
        self.conn.execute(
            "UPDATE todos SET deadline_date = NULL, visible_from_date = NULL, "
            "updated_at = ? WHERE id = ?",
            (_now(), todo_id),
        )
        self.conn.commit()

    def complete_incomplete_for_date(self, iso: str) -> int:
        """해당 날짜의 미완료·미숨김 할일을 모두 완료 처리하고 변경 개수를 반환."""
        cur = self.conn.execute(
            "UPDATE todos SET completed = 1, pinned = 0, updated_at = ? "
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
            "UPDATE todos SET completed = 1, pinned = 0, updated_at = ? "
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
            "UPDATE todos SET due_date = ?, "
            "deadline_date = CASE WHEN deadline_date IS NOT NULL THEN ? ELSE deadline_date END, "
            "visible_from_date = CASE "
            "WHEN deadline_date IS NOT NULL AND visible_from_date > ? THEN ? "
            "ELSE visible_from_date END, "
            "sort_order = ?, updated_at = ? WHERE id = ?",
            (new_iso, new_iso, new_iso, new_iso, new_order, _now(), todo_id),
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
            "priority, pinned, remind_at, recurring_id, deadline_date, visible_from_date, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                todo.content, todo.due_date, int(todo.completed), int(todo.hidden),
                todo.sort_order, todo.priority, int(todo.pinned), todo.remind_at, todo.recurring_id,
                todo.deadline_date, todo.visible_from_date,
                _now(), _now(),
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
                "sort_order = ?, priority = ?, pinned = ?, remind_at = ?, recurring_id = ?, "
                "deadline_date = ?, visible_from_date = ?, updated_at = ? "
                "WHERE id = ?",
                (
                    todo.content,
                    todo.due_date,
                    int(todo.completed),
                    int(todo.hidden),
                    todo.sort_order,
                    todo.priority,
                    int(todo.pinned),
                    todo.remind_at,
                    todo.recurring_id,
                    todo.deadline_date,
                    todo.visible_from_date,
                    now,
                    todo.id,
                ),
            )
        self.conn.commit()
