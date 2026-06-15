"""ui/bubble/overdue_panel.py — '밀린 할일' 독립 패널(말풍선 우측에 떠 있음).

말풍선과 분리된 별도 창이다. 오늘 이전에 미완료가 있는 날짜를 'M/D: n개'로 나열하고,
행을 클릭하면 그 날짜 일간 보기로 이동한다. 우측 상단 X 로 닫는다.
표시 여부는 캐릭터 우클릭 메뉴('밀린할일 표시')로 토글한다(설정에 저장).
위치/높이는 말풍선이 잡아준다(BubbleWidget._position_overdue_panel).
"""
from __future__ import annotations

from datetime import date

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from domain import policies
from ui import theme

PANEL_WIDTH = 120  # 일간(240)의 절반


class _OverdueRow(QLabel):
    def __init__(self, iso: str, count: int, open_day_cb, parent=None):
        d = date.fromisoformat(iso)
        super().__init__(f"{d.month}/{d.day}: {count}개", parent)
        self.iso = iso
        self._open_day_cb = open_day_cb
        self.setObjectName("overdueRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, _e) -> None:
        self._open_day_cb(self.iso)


class OverduePanel(QWidget):
    def __init__(self, service, events, settings_repo, open_day_cb, parent=None):
        super().__init__(parent)
        self._service = service
        self._events = events
        self._settings = settings_repo
        self._open_day_cb = open_day_cb

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(PANEL_WIDTH)

        self._root = QFrame(self)
        self._root.setObjectName("bubbleRoot")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)  # 그림자/여백(말풍선과 동일)
        outer.addWidget(self._root)

        vbox = QVBoxLayout(self._root)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(2)
        title = QLabel("밀린 할일")
        title.setObjectName("overdueTitle")
        f = title.font()
        f.setBold(True)
        title.setFont(f)
        head.addWidget(title, 1)

        close = QToolButton()
        close.setText("✕")  # ✕
        close.setToolTip("닫기")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self._close_panel)
        head.addWidget(close)
        vbox.addLayout(head)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        vbox.addWidget(self._scroll, 1)

        self._events.todos_changed.connect(self._on_data)
        self._events.theme_changed.connect(self.apply_theme)
        self.apply_theme()
        self.reload()

    def apply_theme(self) -> None:
        mode = self._settings.get(policies.KEY_THEME, "system")
        self.setStyleSheet(theme.qss(mode))

    def _on_data(self, _iso: str) -> None:
        if self.isVisible():
            self.reload()

    def _close_panel(self) -> None:
        """X 닫기: 표시 설정을 끄고 알림 → 말풍선이 패널을 숨긴다."""
        self._settings.set(policies.KEY_OVERDUE_PANEL, "0")
        self._events.overdue_panel_changed.emit(False)

    def reload(self) -> None:
        inner = QWidget()
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
