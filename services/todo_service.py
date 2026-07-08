"""services/todo_service.py — 할일 응용 로직.

UI 는 이 서비스만 호출하고, 변경 후엔 EventBus.todos_changed 로 통지한다.
삭제 규칙:
  - 반복 생성분(recurring_id 있음) → 삭제 대신 hide(=1) (tombstone)
  - 일반 할일 → 진짜 DELETE
  - 삭제/밀린할일 일괄 작업은 직전 1건을 메모리에 보관해 revert 가능
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from domain.models import Todo

log = logging.getLogger(__name__)
MAX_PINNED_PER_DAY = 2


class TodoService:
    def __init__(self, todo_repo, recurring_service, events):
        self._repo = todo_repo
        self._recurring = recurring_service
        self._events = events
        # 되돌리기 버퍼: ('delete', Todo) / ('hide', todo_id) / ('restore', list[Todo])
        self._undo: tuple[str, object] | None = None

    # ── 조회 ────────────────────────────────────────────────
    def list_for_date(self, iso: str, priority_sort: bool = False) -> list[Todo]:
        # 반복 할일은 '오늘'에만 생성한다(미래/과거 날짜는 박제하지 않음).
        # 오늘을 조회하는 순간 그 날 회차가 생기고, 미래 날짜는 그 날이 와야 생긴다.
        self._ensure_recurring_if_today(iso)
        return self._repo.list_for_date(iso, priority_sort=priority_sort)

    def pinned_for_date(self, iso: str) -> list[Todo]:
        self._ensure_recurring_if_today(iso)
        return self._repo.pinned_for_date(iso)

    def unpinned_for_date(self, iso: str, priority_sort: bool = False) -> list[Todo]:
        self._ensure_recurring_if_today(iso)
        return self._repo.unpinned_for_date(iso, priority_sort=priority_sort)

    def total_incomplete_count(self) -> int:
        """날짜와 무관하게 미완료 할일 전체 개수('할일 n개' 풍선용).
        오늘 회차 반복 할일이 빠지지 않도록 먼저 생성한 뒤 센다."""
        self._recurring.ensure_for_date(date.today())
        return self._repo.count_incomplete()

    def ensure_today_recurring(self) -> None:
        """오늘 날짜의 반복 회차를 생성(앱 시작·자정 넘김 시 컨트롤러가 호출)."""
        self._recurring.ensure_for_date(date.today())

    def has_overdue(self, today_iso: str) -> bool:
        """오늘 이전에 미완료 할일이 남아 있는지(캐릭터 상태 표시용)."""
        return self._repo.has_incomplete_before(today_iso)

    def overdue_counts(self, today_iso: str) -> list[tuple[str, int]]:
        """오늘 이전 미완료 할일을 날짜별 개수로(밀린 할일 패널용)."""
        return self._repo.incomplete_counts_before(today_iso)

    def completed_items(self, query: str = "") -> list[Todo]:
        """완료한 할일 목록(완료 조회 패널용)."""
        return self._repo.completed_items(query)

    def completed_counts(self, query: str = "") -> list[tuple[str, int]]:
        """완료한 할일을 날짜별 개수로(완료 조회 패널 날짜별 보기용)."""
        return self._repo.completed_counts(query)

    def movable_overdue_count(self, today_iso: str) -> int:
        """오늘로 옮길 수 있는 미완료 일반 할일 개수(반복 회차 제외)."""
        return self._repo.count_incomplete_regular_before(today_iso)

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
    def add(self, content: str, iso: str, priority: int = 0) -> None:
        content = content.strip()
        if not content:
            return
        priority = max(0, min(3, int(priority)))
        self._repo.add(content, iso, priority)
        self._notify(iso)
        self._events.todo_added.emit()

    def add_many(self, contents: list[str], iso: str, priority: int = 0) -> int:
        priority = max(0, min(3, int(priority)))
        count = self._repo.add_many(contents, iso, priority)
        if count:
            self._notify(iso)
            self._events.todo_added.emit()
        return count

    def toggle(self, todo_id: int) -> None:
        t = self._repo.get(todo_id)
        if not t:
            return
        now_completed = not t.completed
        self._repo.set_completed(todo_id, now_completed)
        if now_completed and t.pinned:
            self._repo.set_pinned(todo_id, False)
        self._notify(t.due_date)
        if now_completed:  # 미완료→완료 전환 순간만(캐릭터 리액션용)
            self._events.todo_completed.emit()

    def edit(self, todo_id: int, content: str) -> None:
        content = content.strip()
        t = self._repo.get(todo_id)
        if not t or not content:
            return
        if content == t.content:
            return
        self._set_restore_undo([t])
        self._repo.set_content(todo_id, content)
        self._notify(t.due_date)

    def set_priority(self, todo_id: int, priority: int, notify: bool = True) -> None:
        priority = max(0, min(3, int(priority)))
        t = self._repo.get(todo_id)
        if not t or t.priority == priority:
            return
        self._set_restore_undo([t])
        self._repo.set_priority(todo_id, priority)
        if notify:
            self._notify(t.due_date)

    def set_pinned(self, todo_id: int, pinned: bool) -> bool:
        t = self._repo.get(todo_id)
        if not t or t.hidden:
            return False
        if pinned:
            if t.completed:
                return False
            if not t.pinned and self._repo.pinned_count_for_date(t.due_date) >= MAX_PINNED_PER_DAY:
                return False
        if t.pinned == pinned:
            return True
        self._set_restore_undo([t])
        self._repo.set_pinned(todo_id, pinned)
        self._notify(t.due_date)
        return True

    def duplicate(self, todo_id: int) -> None:
        """할일을 복제해 원본 바로 아래에 같은 내용으로 생성(미완료 상태)."""
        t = self._repo.get(todo_id)
        if not t:
            return
        self._repo.add_after(t.content, t.due_date, t.sort_order, t.priority)
        self._notify(t.due_date)

    def duplicate_completed_to_today(self, todo_id: int) -> int:
        """완료 조회 패널용: 완료 할일 1건을 오늘 미완료 일반 할일로 복제."""
        todo = self._repo.get(todo_id)
        if not todo or not todo.completed or todo.hidden:
            return 0
        today_iso = date.today().isoformat()
        count = self._repo.add_many([todo.content], today_iso)
        if count:
            self._notify(today_iso)
            self._events.todo_added.emit()
        return count

    def duplicate_completed_date_to_today(self, iso: str) -> int:
        """완료 조회 패널용: 해당 날짜의 완료 할일 전체를 오늘 미완료 일반 할일로 복제."""
        snapshot = self._repo.completed_for_date(iso)
        if not snapshot:
            return 0
        today_iso = date.today().isoformat()
        count = self._repo.add_many([t.content for t in snapshot], today_iso)
        if count:
            self._notify(today_iso)
            self._events.todo_added.emit()
        return count

    def move(self, todo_id: int, new_iso: str, new_order: int | None = None) -> None:
        t = self._repo.get(todo_id)
        if not t:
            return
        old_iso = t.due_date
        self._repo.move(todo_id, new_iso, new_order)
        self._notify(old_iso)
        if new_iso != old_iso:
            self._notify(new_iso)

    def complete_incomplete_for_date(self, iso: str) -> int:
        """밀린할일 패널용: 해당 날짜의 미완료 할일을 모두 완료 처리."""
        snapshot = self._repo.incomplete_for_date(iso)
        if not snapshot:
            return 0
        count = self._repo.complete_incomplete_for_date(iso)
        if count:
            self._set_restore_undo(snapshot)
            self._notify(iso)
            self._events.todo_completed.emit()
        return count

    def complete_all_overdue(self) -> int:
        """밀린할일 패널용: 오늘 이전 미완료 할일을 모두 완료 처리."""
        today_iso = date.today().isoformat()
        snapshot = self._repo.incomplete_before(today_iso)
        if not snapshot:
            return 0
        count, changed_dates = self._repo.complete_incomplete_before(today_iso)
        if count:
            self._set_restore_undo(snapshot)
            self._notify_many(changed_dates)
            self._events.todo_completed.emit()
        return count

    def move_incomplete_regular_to_today(self, iso: str) -> int:
        """밀린할일 패널용: 해당 날짜의 미완료 일반 할일만 오늘로 옮긴다."""
        today_iso = date.today().isoformat()
        snapshot = self._repo.incomplete_regular_for_date(iso)
        if not snapshot:
            return 0
        count = self._repo.move_incomplete_regular_to_date(iso, today_iso)
        if count:
            self._set_restore_undo(snapshot)
            self._notify(iso)
            if today_iso != iso:
                self._notify(today_iso)
        return count

    def move_all_overdue_regular_to_today(self) -> int:
        """밀린할일 패널용: 오늘 이전 미완료 일반 할일을 모두 오늘로 옮긴다."""
        today_iso = date.today().isoformat()
        snapshot = self._repo.incomplete_regular_before(today_iso)
        if not snapshot:
            return 0
        count, changed_dates = self._repo.move_incomplete_regular_before_to_date(
            today_iso, today_iso
        )
        if count:
            self._set_restore_undo(snapshot)
            self._notify_many(changed_dates)
            self._notify(today_iso)
        return count

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
        self._events.todo_removed.emit()

    def undo_remove(self) -> None:
        if not self._undo:
            return
        kind, payload = self._undo
        self._undo = None
        if kind == "hide":
            self._repo.unhide(payload)  # type: ignore[arg-type]
            t = self._repo.get(payload)  # type: ignore[arg-type]
            iso = t.due_date if t else None
            if iso:
                self._notify(iso)
        elif kind == "delete":
            t: Todo = payload  # type: ignore[assignment]
            self._repo.insert_raw(t)
            self._notify(t.due_date)
        elif kind == "restore":
            snapshot: list[Todo] = payload  # type: ignore[assignment]
            current = self._repo.list_by_ids([t.id for t in snapshot])
            self._repo.restore_existing(snapshot)
            dates = {t.due_date for t in snapshot}
            dates.update(t.due_date for t in current)
            self._notify_many(sorted(dates))
        self._events.delete_undo_available.emit(False)

    # ── 내부 ────────────────────────────────────────────────
    def delete_recurring_todos(self, rule_id: int) -> None:
        """반복 규칙으로 생성된 할일 전체 삭제 후 화면 갱신."""
        self._repo.delete_by_recurring(rule_id)
        self._notify(date.today().isoformat())

    def _set_restore_undo(self, snapshot: list[Todo]) -> None:
        self._undo = ("restore", snapshot)
        self._events.delete_undo_available.emit(True)

    def _ensure_recurring_if_today(self, iso: str) -> None:
        today = date.today()
        if iso == today.isoformat():
            self._recurring.ensure_for_date(today)

    def _notify_many(self, dates) -> None:
        for iso in dict.fromkeys(dates):
            self._notify(iso)

    def _notify(self, iso: str) -> None:
        self._events.todos_changed.emit(iso)
