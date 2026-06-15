"""core/events.py — 전역 시그널 허브.

UI 와 Service 가 서로를 직접 호출하지 않고 이 허브의 시그널로만 통신한다.
한 인스턴스를 DI 컨테이너가 만들어 양쪽에 주입한다.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal


class EventBus(QObject):
    # 데이터가 바뀌어 특정 날짜를 다시 그려야 할 때 (ISO 'YYYY-MM-DD')
    todos_changed = pyqtSignal(str)
    # 캐릭터 이미지 경로가 바뀌었을 때
    character_image_changed = pyqtSignal(str)
    # 방금 삭제한 항목을 되돌릴 수 있게 됨 (revert 버튼 노출용)
    delete_undo_available = pyqtSignal(bool)
    # 테마(밝게/어둡게/자동)가 바뀌었을 때
    theme_changed = pyqtSignal()
    # 밀린 할일 패널 표시 여부가 바뀌었을 때 (True=표시)
    overdue_panel_changed = pyqtSignal(bool)
