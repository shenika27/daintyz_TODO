"""services/todo_service.py — 할일 응용 로직.

UI 는 이 서비스만 호출하고, 변경 후엔 EventBus.todos_changed 로 통지한다.
삭제 규칙:
  - 반복 생성분(recurring_id 있음) → 삭제 대신 hide(=1) (tombstone)
  - 일반 할일 → 진짜 DELETE, 단 직전 1건은 메모리에 보관해 revert 가능
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from domain.models import Todo

log = logging.getLogger(__name__)


class TodoService:
    def __init__(self, todo_repo, recurring_service, events):
        self._repo = todo_repo
        self._recurring = recurring_service
        self._events = events
        # 되돌리기 버퍼: ('delete', Todo) 또는 ('hide', todo_id)
        self._undo: tuple[str, object] | None = None

    # ── 조회 ────────────────────────────────────────────────
    def list_for_date(self, iso: str) -> list[Todo]:
        # 반복 할일은 '오늘'에만 생성한다(미래/과거 날짜는 박제하지 않음).
        # 오늘을 조회하는 순간 그 날 회차가 생기고, 미래 날짜는 그 날이 와야 생긴다.
        if iso == date.today().isoformat():
            self._recurring.ensure_for_date(date.today())
        return self._repo.list_for_date(iso)

    def ensure_today_recurring(self) -> None:
        """오늘 날짜의 반복 회차를 생성(앱 시작·자정 넘김 시 컨트롤러가 호출)."""
        self._recurring.ensure_for_date(date.today())

    def has_overdue(self, today_iso: str) -> bool:
        """오늘 이전에 미완료 할일이 남아 있는지(캐릭터 상태 표시용)."""
        return self._repo.has_incomplete_before(today_iso)

    def overdue_counts(self, today_iso: str) -> list[tuple[str, int]]:
        """오늘 이전 미완료 할일을 날짜별 개수로(밀린 할일 패널용)."""
        return self._repo.incomplete_counts_before(today_iso)

    def is_idle(self, hours: int) -> bool:
        """마지막 할일 활동(생성/수정)이 hours 시간 이상 지났으면 True. 0=항상 False."""
        if hours <= 0:
            return False
        latest = self._repo.latest_activity()
        if not latest:
            return False
        delta = datetime.now() - datetime.fromisoformat(latest)
        return delta.total_seconds() >= hours * 3600

    # ── 쓰기 ────────────────────────────────────────────────
    def add(self, content: str, iso: str) -> None:
        content = content.strip()
        if not content:
            return
        self._repo.add(content, iso)
        self._notify(iso)

    def toggle(self, todo_id: int) -> None:
        t = self._repo.get(todo_id)
        if not t:
            return
        now_completed = not t.completed
        self._repo.set_completed(todo_id, now_completed)
        self._notify(t.due_date)
        if now_completed:  # 미완료→완료 전환 순간만(캐릭터 리액션용)
            self._events.todo_completed.emit()

    def edit(self, todo_id: int, content: str) -> None:
        content = content.strip()
        t = self._repo.get(todo_id)
        if not t or not content:
            return
        self._repo.set_content(todo_id, content)
        self._notify(t.due_date)

    def duplicate(self, todo_id: int) -> None:
        """할일을 복제해 원본 바로 아래에 같은 내용으로 생성(미완료 상태)."""
        t = self._repo.get(todo_id)
        if not t:
            return
        self._repo.add_after(t.content, t.due_date, t.sort_order)
        self._notify(t.due_date)

    def move(self, todo_id: int, new_iso: str, new_order: int | None = None) -> None:
        t = self._repo.get(todo_id)
        if not t:
            return
        old_iso = t.due_date
        self._repo.move(todo_id, new_iso, new_order)
        self._notify(old_iso)
        if new_iso != old_iso:
            self._notify(new_iso)

    def reorder(self, iso: str, ordered_ids: list[int]) -> None:
        self._repo.reorder(iso, ordered_ids)
        self._notify(iso)

    def remove(self, todo_id: int) -> None:
        """외부 드롭/삭제. 반복 회차는 hide, 일반은 delete(+undo 보관)."""
        t = self._repo.get(todo_id)
        if not t:
            return
        if t.is_recurring_instance:
            self._repo.hide(todo_id)
            self._undo = ("hide", todo_id)
        else:
            self._repo.delete(todo_id)
            self._undo = ("delete", t)
        self._events.delete_undo_available.emit(True)
        self._notify(t.due_date)

    def undo_remove(self) -> None:
        if not self._undo:
            return
        kind, payload = self._undo
        self._undo = None
        if kind == "hide":
            self._repo.unhide(payload)  # type: ignore[arg-type]
            t = self._repo.get(payload)  # type: ignore[arg-type]
            iso = t.due_date if t else None
        else:
            t: Todo = payload  # type: ignore[assignment]
            self._repo.insert_raw(t)
            iso = t.due_date
        self._events.delete_undo_available.emit(False)
        if iso:
            self._notify(iso)

    # ── 내부 ────────────────────────────────────────────────
    def delete_recurring_todos(self, rule_id: int) -> None:
        """반복 규칙으로 생성된 할일 전체 삭제 후 화면 갱신."""
        self._repo.delete_by_recurring(rule_id)
        self._notify(date.today().isoformat())

    def _notify(self, iso: str) -> None:
        self._events.todos_changed.emit(iso)
