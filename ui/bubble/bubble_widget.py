"""ui/bubble/bubble_widget.py — 말풍선: 헤더(확장/최소화/되돌리기) + 뷰 + 입력바.

확장 버튼: 일간 → 주간 → 월간 → 일간(오늘) 순환.
캐릭터 위치 기준으로 화면 밖으로 나가지 않게 방향을 뒤집어 배치한다.
"""
from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from domain import policies
from ui.bubble.day_view import DayView
from ui.bubble.input_bar import InputBar
from ui.bubble.month_view import MonthView
from ui.bubble.week_view import WeekView

_ORDER = ["day", "week", "month"]
_WIDTH = {"day": 280, "week": 560, "month": 400}


class BubbleWidget(QWidget):
    def __init__(self, service, events, settings_repo, parent=None):
        super().__init__(parent)
        self._service = service
        self._events = events
        self._settings = settings_repo

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self.selected_iso = date.today().isoformat()
        self.view_mode = self._settings.get(policies.KEY_LAST_VIEW, "day") or "day"
        if self.view_mode not in _ORDER:
            self.view_mode = "day"

        root = QFrame(self)
        root.setObjectName("bubbleRoot")
        root.setStyleSheet(
            "#bubbleRoot { background: palette(window); border: 1px solid rgba(0,0,0,0.25);"
            " border-radius: 10px; }"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

        self._vbox = QVBoxLayout(root)
        self._vbox.setContentsMargins(6, 6, 6, 6)
        self._vbox.setSpacing(4)

        self._build_header()
        self._view_holder = QWidget()
        self._view_layout = QVBoxLayout(self._view_holder)
        self._view_layout.setContentsMargins(0, 0, 0, 0)
        self._vbox.addWidget(self._view_holder)

        self._input = InputBar(self._service, lambda: self.selected_iso)
        self._vbox.addWidget(self._input)

        self._events.todos_changed.connect(self._on_data_changed)
        self._events.delete_undo_available.connect(self._set_revert_visible)

        self.render()

    # ── 헤더 ────────────────────────────────────────────────
    def _build_header(self) -> None:
        bar = QHBoxLayout()
        self._title = QLabel()
        f = self._title.font()
        f.setBold(True)
        self._title.setFont(f)
        bar.addWidget(self._title, 1)

        self._revert = QPushButton("되돌리기")
        self._revert.setVisible(False)
        self._revert.clicked.connect(self._on_revert)
        bar.addWidget(self._revert)

        self._expand = QToolButton()
        self._expand.setText("\u25a3")  # ▣
        self._expand.setToolTip("확장 (일→주→월)")
        self._expand.clicked.connect(self.cycle_expand)
        bar.addWidget(self._expand)

        self._min = QToolButton()
        self._min.setText("\u2013")  # –
        self._min.setToolTip("최소화")
        self._min.clicked.connect(self.hide)
        bar.addWidget(self._min)

        self._vbox.addLayout(bar)

    # ── 렌더 ────────────────────────────────────────────────
    def render(self) -> None:
        while self._view_layout.count():
            w = self._view_layout.takeAt(0).widget()
            if w:
                w.deleteLater()

        if self.view_mode == "day":
            view = DayView(self.selected_iso, self._service)
        elif self.view_mode == "week":
            view = WeekView(self.selected_iso, self._service, self.select_date)
        else:
            view = MonthView(self.selected_iso, self._service, self.select_date)
        self._view_layout.addWidget(view)

        self._title.setText(self._title_text())
        self.setFixedWidth(_WIDTH[self.view_mode])
        self.adjustSize()

    def _title_text(self) -> str:
        d = date.fromisoformat(self.selected_iso)
        return f"{d.year}-{d.month:02d}-{d.day:02d} ({self.view_mode})"

    def select_date(self, iso: str) -> None:
        self.selected_iso = iso
        self.render()

    def cycle_expand(self) -> None:
        idx = (_ORDER.index(self.view_mode) + 1) % len(_ORDER)
        self.view_mode = _ORDER[idx]
        # 월간에서 재확장 → 일간(오늘)로
        if self.view_mode == "day":
            self.selected_iso = date.today().isoformat()
        self._settings.set(policies.KEY_LAST_VIEW, self.view_mode)
        self.render()

    # ── 이벤트 ──────────────────────────────────────────────
    def _on_data_changed(self, _iso: str) -> None:
        if self.isVisible():
            self.render()

    def _set_revert_visible(self, v: bool) -> None:
        self._revert.setVisible(v)

    def _on_revert(self) -> None:
        self._service.undo_remove()

    # ── 배치 ────────────────────────────────────────────────
    def show_for_character(self, char_geom: QRect, screen_geom: QRect) -> None:
        self.render()
        self.adjustSize()
        w, h = self.width(), self.height()

        # 기본: 캐릭터 위쪽에 띄움
        x = char_geom.center().x() - w // 2
        y = char_geom.top() - h - 8
        # 위 공간 부족 → 아래로
        if y < screen_geom.top():
            y = char_geom.bottom() + 8
        # 좌우 화면 밖 → clamp
        x = max(screen_geom.left() + 4, min(x, screen_geom.right() - w - 4))
        y = max(screen_geom.top() + 4, min(y, screen_geom.bottom() - h - 4))

        self.move(x, y)
        self.show()
        self.raise_()
