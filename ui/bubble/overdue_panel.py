"""ui/bubble/overdue_panel.py — '밀린 할일' 독립 패널(말풍선 우측에 떠 있음).

말풍선과 분리된 별도 창이다. 오늘 이전에 미완료가 있는 날짜를 'M/D(요일): n개'로 나열하고,
행을 클릭하면 그 날짜 일간 보기로 이동한다. 우측 상단 X 로 닫는다.
표시 여부는 캐릭터 우클릭 메뉴('밀린할일 표시')로 토글한다(설정에 저장).
위치/높이는 말풍선이 잡아준다(BubbleWidget._position_overdue_panel).
"""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from domain import policies
from ui.bubble.panel_base import PANEL_WIDTH, _PanelBase

__all__ = ["PANEL_WIDTH", "OverduePanel"]


class _OverdueRow(QLabel):
    def __init__(self, iso: str, count: int, open_day_cb, parent=None):
        d = date.fromisoformat(iso)
        super().__init__(f"{policies.fmt_md(d)}: {count}개", parent)
        self.iso = iso
        self._open_day_cb = open_day_cb
        self.setObjectName("overdueRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, _e) -> None:
        self._open_day_cb(self.iso)


class OverduePanel(_PanelBase):
    def __init__(self, service, events, settings_repo, open_day_cb, parent=None):
        super().__init__(settings_repo, events, "밀린 할일", parent)
        self._service = service
        self._open_day_cb = open_day_cb

        self._add_header_button("✕", "닫기", self._close_panel)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._vbox.addWidget(self._scroll, 1)

        self._events.todos_changed.connect(self._on_data)
        self.apply_theme()
        self.reload()

    def _on_data(self, _iso: str) -> None:
        if self.isVisible():
            self.reload()

    def _close_panel(self) -> None:
        """✕ 닫기: 표시 끄기 알림만 보낸다. 설정 저장·패널 숨김은 BubbleWidget 이 처리(#1)."""
        self._events.overdue_panel_changed.emit(False)

    def reload(self) -> None:
        inner = QWidget(self._scroll)  # 부모 지정: 잠깐 최상위 창이 되는 깜빡임 방지
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 2, 2, 2)
        lay.setSpacing(3)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        rows = self._service.overdue_counts(date.today().isoformat())
        if not rows:
            empty = QLabel("없음")
            empty.setObjectName("emptyText")
            empty.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lay.addWidget(empty)
        else:
            for iso, cnt in rows:
                lay.addWidget(_OverdueRow(iso, cnt, self._open_day_cb))
        self._scroll.setWidget(inner)
