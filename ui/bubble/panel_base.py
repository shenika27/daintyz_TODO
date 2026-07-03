"""ui/bubble/panel_base.py — 밀린할일/타이머 독립 패널의 공통 베이스.

말풍선과 분리된 프레임리스 오버레이 창의 공통 틀(헤더 title+✕, bubbleRoot 프레임,
apply_theme)을 제공한다. 위치/높이는 말풍선이 잡아준다(BubbleWidget._position_left_column).
자식은 본문 위젯을 self._vbox 에 추가하고 reload()/_close_panel() 을 구현한다.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from domain import policies
from ui import theme
from ui.qt_helpers import make_overlay_window

PANEL_WIDTH = 156  # 밀린할일·타이머 공통 패널 폭(헤더 버튼 2개까지 수용)
_OUTER_MARGIN = 8
_CONTENT_MARGIN = 8
_CONTENT_SPACING = 6
_HEADER_HEIGHT = 22
_HEADER_BUTTON_SIZE = 22
_HEADER_BUTTON_SPACING = 2


class _PanelBase(QWidget):
    """프레임리스 오버레이 패널 베이스: 헤더(제목+✕) + bubbleRoot 틀 + 테마."""

    def __init__(self, settings_repo, events, title: str, parent=None):
        super().__init__(parent)
        self._settings = settings_repo
        self._events = events

        make_overlay_window(self)
        self.setFixedWidth(PANEL_WIDTH)

        self._root = QFrame(self)
        self._root.setObjectName("bubbleRoot")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(_OUTER_MARGIN, _OUTER_MARGIN, _OUTER_MARGIN, _OUTER_MARGIN)
        outer.addWidget(self._root)

        self._root_lay = QVBoxLayout(self._root)
        self._root_lay.setContentsMargins(
            _CONTENT_MARGIN, _CONTENT_MARGIN, _CONTENT_MARGIN, _CONTENT_MARGIN
        )
        self._root_lay.setSpacing(_CONTENT_SPACING)

        self._header = QWidget(self._root)
        self._header.setFixedHeight(_HEADER_HEIGHT)
        self._head = QHBoxLayout(self._header)
        self._head.setContentsMargins(0, 0, 0, 0)
        self._head.setSpacing(_HEADER_BUTTON_SPACING)
        self._title_lbl = QLabel(title)
        self._title_lbl.setObjectName("overdueTitle")
        self._title_lbl.setFixedHeight(_HEADER_HEIGHT)
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._title_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        f = self._title_lbl.font()
        f.setBold(True)
        self._title_lbl.setFont(f)
        self._head.addWidget(self._title_lbl, 1)
        self._root_lay.addWidget(self._header)

        self._body = QWidget(self._root)
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(0, 0, 0, 0)
        self._body_lay.setSpacing(_CONTENT_SPACING)
        self._root_lay.addWidget(self._body, 1)

        # 자식 패널은 본문만 다룬다. 헤더 여백과 기준선은 이 베이스가 고정한다.
        self._vbox = self._body_lay

        self._events.theme_changed.connect(self.apply_theme)

    def _set_title(self, text: str) -> None:
        self._title_lbl.setText(text)

    def _add_header_button(self, text: str, tooltip: str, on_click) -> QToolButton:
        """헤더 우측에 툴버튼 추가(✕ 포함). 추가 순서대로 우측에 배치된다."""
        b = QToolButton()
        b.setObjectName("headerBtn")
        b.setText(text)
        b.setToolTip(tooltip)
        b.setFixedSize(_HEADER_BUTTON_SIZE, _HEADER_BUTTON_SIZE)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(on_click)
        self._head.addWidget(b)
        return b

    def apply_theme(self) -> None:
        mode = self._settings.get(policies.KEY_THEME, "system")
        self.setStyleSheet(theme.qss(mode))

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.WindowActivate:
            self._request_companion_raise()
        return super().event(e)

    def mousePressEvent(self, e) -> None:
        self._request_companion_raise()
        super().mousePressEvent(e)

    def _request_companion_raise(self) -> None:
        self._events.grid_attention_requested.emit()
        QTimer.singleShot(0, self.raise_)

    def reload(self) -> None:  # pragma: no cover - 자식이 구현
        raise NotImplementedError

    def _close_panel(self) -> None:  # pragma: no cover - 자식이 구현
        raise NotImplementedError
