"""core/events.py — 전역 시그널 허브.

UI 와 Service 가 서로를 직접 호출하지 않고 이 허브의 시그널로만 통신한다.
한 인스턴스를 DI 컨테이너가 만들어 양쪽에 주입한다.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class EventBus(QObject):
    # 데이터가 바뀌어 특정 날짜를 다시 그려야 할 때 (ISO 'YYYY-MM-DD')
    todos_changed = Signal(str)
    # 캐릭터 이미지 경로가 바뀌었을 때
    character_image_changed = Signal(str)
    # 방금 삭제한 항목을 되돌릴 수 있게 됨 (revert 버튼 노출용)
    delete_undo_available = Signal(bool)
    # 테마(밝게/어둡게/자동)가 바뀌었을 때
    theme_changed = Signal()
    # 밀린 할일 패널 표시 여부가 바뀌었을 때 (True=표시)
    overdue_panel_changed = Signal(bool)
    # 타이머 패널 상시 표시 여부가 바뀌었을 때 (True=표시)
    timer_panel_changed = Signal(bool)
    # 할일을 '완료'로 체크한 순간(캐릭터 완료 리액션용)
    todo_completed = Signal()
    # 할일이 새로 추가된 순간(캐릭터 추가 리액션용)
    todo_added = Signal()
    # 할일이 삭제된 순간(캐릭터 삭제 리액션용)
    todo_removed = Signal()
    # 캐릭터 크기(%)가 바뀌었을 때
    character_scale_changed = Signal()
    # 글로벌 단축키 설정이 바뀌었을 때(재등록 트리거)
    hotkeys_changed = Signal()
    # 할일 타이머 시작 (todo_id)
    timer_started = Signal(int)
    # 타이머 매초 갱신 (todo_id, 남은 초)
    timer_tick = Signal(int, int)
    # 타이머 시간 만료 (todo_id)
    timer_finished = Signal(int)
    # 타이머 해제/중단 (사용자 취소 또는 완료 처리)
    timer_stopped = Signal()
    # 타이머 정지(일시정지) (todo_id)
    timer_paused = Signal(int)
    # 타이머 재개 (todo_id)
    timer_resumed = Signal(int)
    # 말풍선(투두)이 닫혔을 때(– 최소화 등) — 타이머 풍선 재표시 트리거
    bubble_closed = Signal()
    # 말풍선(투두)이 열렸을 때 — 캐릭터 목록-열림 이미지 전환 트리거
    bubble_opened = Signal()
    # '할일 n개' 풍선 표시 설정이 바뀌었을 때 (True=표시) — 즉시 동기화 트리거
    todo_count_bubble_changed = Signal(bool)
