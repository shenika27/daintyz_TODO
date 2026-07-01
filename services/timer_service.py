"""services/timer_service.py — 할일 집중 타이머(메모리 단일 타이머).

한 번에 하나의 할일만 타이머를 가진다. 상태는 메모리에만 두므로 앱 재시작 시 소멸.
1초마다 카운트다운하며 EventBus 로 상태를 통지한다.
  - timer_started(todo_id)        : 새 타이머 시작
  - timer_tick(todo_id, 남은초)    : 매초 갱신
  - timer_finished(todo_id)       : 시간 만료(자연 종료)
  - timer_stopped()               : 해제/완료로 중단
완료 처리(할일 체크)는 TodoService.toggle 이 담당하고, 이 서비스는 타이머 상태만 관리한다.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QTimer

from domain import policies


@dataclass
class TimerSnapshot:
    todo_id: int | None  # None = 할일 없는 일반(상시) 타이머
    content: str
    total_seconds: int
    remaining_seconds: int
    paused: bool = False


# 할일 없는 일반 타이머의 시그널 id(시그널은 int 만 받으므로 센티넬 사용)
STANDALONE_ID = -1


class TimerService(QObject):
    def __init__(self, events, parent=None):
        super().__init__(parent)
        self._events = events
        self._active: bool = False           # 타이머가 살아있는지(할일/일반 공통)
        self._todo_id: int | None = None     # None = 할일 없는 일반 타이머
        self._content: str = ""
        self._total: int = 0
        self._remaining: int = 0
        self._paused: bool = False
        self._auto_complete: bool = False    # 만료 시 할일 자동 완료 여부
        self._last_standalone_secs: int = policies.DEFAULT_STANDALONE_SECONDS  # #9 초기화용

        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._on_tick)

    # ── 조회 ────────────────────────────────────────────────
    def is_active(self, todo_id: int | None = None) -> bool:
        """타이머 실행 중인지. todo_id 를 주면 그 할일이 활성 대상인지
        (일반 타이머는 todo_id 가 None 이라 특정 할일과는 매칭되지 않음)."""
        if not self._active:
            return False
        return todo_id is None or todo_id == self._todo_id

    def is_standalone(self) -> bool:
        """할일 없는 일반(상시) 타이머가 도는 중인지."""
        return self._active and self._todo_id is None

    @property
    def active_todo_id(self) -> int | None:
        return self._todo_id

    @property
    def auto_complete(self) -> bool:
        """현재(또는 마지막) 타이머의 '완료 시 자동 완료' 설정."""
        return self._auto_complete

    @property
    def last_standalone_seconds(self) -> int:
        """직전에 시작한 일반 타이머의 설정 시간(초). idle 컨트롤 기본값/초기화용."""
        return self._last_standalone_secs

    def is_paused(self) -> bool:
        return self._paused

    def snapshot(self) -> TimerSnapshot | None:
        if not self._active:
            return None
        return TimerSnapshot(
            self._todo_id, self._content, self._total, self._remaining, self._paused
        )

    def _emit_id(self) -> int:
        """시그널용 id: 할일 타이머는 todo_id, 일반 타이머는 센티넬."""
        return self._todo_id if self._todo_id is not None else STANDALONE_ID

    # ── 제어 ────────────────────────────────────────────────
    def start(self, todo_id: int, content: str, seconds: int,
              auto_complete: bool = False) -> None:
        """할일 타이머 시작(기존 타이머가 있으면 교체). seconds 는 시·분·초 합산값."""
        secs = max(1, int(seconds))
        self._active = True
        self._todo_id = todo_id
        self._content = content
        self._total = secs
        self._remaining = secs
        self._paused = False
        self._auto_complete = bool(auto_complete)
        self._tick.start()
        self._events.timer_started.emit(todo_id)
        self._events.timer_tick.emit(todo_id, self._remaining)

    def start_standalone(self, seconds: int) -> None:
        """할일 없는 일반 타이머 시작(기존 타이머가 있으면 교체)."""
        secs = max(1, int(seconds))
        self._last_standalone_secs = secs
        self._active = True
        self._todo_id = None
        self._content = "타이머"
        self._total = secs
        self._remaining = secs
        self._paused = False
        self._auto_complete = False
        self._tick.start()
        self._events.timer_started.emit(STANDALONE_ID)
        self._events.timer_tick.emit(STANDALONE_ID, self._remaining)

    def reset_standalone(self) -> None:
        """진행 중 일반 타이머를 멈추고 '시작 전' 초기 설정 화면으로 되돌린다(#9).
        직전 설정 시간(_last_standalone_secs)은 cancel 후에도 유지되어 idle 컨트롤이 그 값으로
        다시 채워지고, timer_stopped 로 캐릭터도 기본 이미지로 복귀한다."""
        if not self.is_standalone():
            return
        self.cancel()

    def reset_to_total(self) -> None:
        """진행 중 할일 타이머를 그 타이머의 초기 설정 시간으로 되돌린다(#8). 타이머/정지 상태 유지."""
        if not self._active or self._todo_id is None:
            return
        self._remaining = self._total
        self._events.timer_tick.emit(self._emit_id(), self._remaining)

    def pause(self) -> None:
        """카운트다운만 멈추고 남은 시간·대상은 유지(타이머는 살아 있음)."""
        if not self._active or self._paused:
            return
        self._paused = True
        self._tick.stop()
        self._events.timer_paused.emit(self._emit_id())

    def resume(self) -> None:
        if not self._active or not self._paused:
            return
        self._paused = False
        self._tick.start()
        self._events.timer_resumed.emit(self._emit_id())

    def toggle_pause(self) -> None:
        self.resume() if self._paused else self.pause()

    def cancel(self) -> None:
        """사용자 해제 또는 완료 처리로 타이머 제거."""
        if not self._active:
            return
        self._tick.stop()
        self._active = False
        self._todo_id = None
        self._content = ""
        self._total = self._remaining = 0
        self._paused = False
        self._auto_complete = False
        self._events.timer_stopped.emit()

    def cancel_for(self, todo_id: int) -> None:
        """특정 할일이 활성 타이머일 때만 해제(완료/삭제 연동용)."""
        if self._active and self._todo_id == todo_id:
            self.cancel()

    # ── 내부 ────────────────────────────────────────────────
    def _on_tick(self) -> None:
        if not self._active:
            self._tick.stop()
            return
        self._remaining -= 1
        if self._remaining <= 0:
            finished_id = self._emit_id()
            self._tick.stop()
            self._active = False
            self._todo_id = None
            self._content = ""
            self._total = self._remaining = 0
            self._paused = False
            # _auto_complete 는 만료 핸들러(main)가 읽도록 다음 start/cancel 까지 유지
            self._events.timer_finished.emit(finished_id)
        else:
            self._events.timer_tick.emit(self._emit_id(), self._remaining)
