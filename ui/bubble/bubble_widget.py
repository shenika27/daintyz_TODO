"""ui/bubble/bubble_widget.py — 말풍선: 헤더(확장/최소화/되돌리기) + 뷰 + 입력바.

- 확장 버튼: 일간 → 주간 → 월간 → 일간(오늘) 순환
- 되돌리기: 화살표 아이콘(↺) 버튼, 삭제 직후에만 노출
- 테마(밝게/어둡게/자동) 스타일 적용
- 배치: 캐릭터 기준으로 화면 안쪽 방향으로 펼치고 화면 밖으로 안 나가게 clamp
        (캐릭터 드래그 중에는 말풍선도 따라 이동)
"""
from __future__ import annotations

from datetime import date, timedelta

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from domain import policies
from ui import theme
from ui.bubble.day_view import DayView
from ui.bubble.input_bar import InputBar
from ui.bubble.month_view import MonthView
from ui.bubble.overdue_panel import OverduePanel
from ui.bubble.week_view import WeekView

_ORDER = ["day", "week", "month"]
_WIDTH = {"day": 240, "week": 920, "month": 470}
_GAP = 10
_PANEL_GAP = 2  # 밀린 할일 패널 ↔ 말풍선 간격
_MARGIN = 6
_WD_KR = ["일", "월", "화", "수", "목", "금", "토"]


class BubbleWidget(QWidget):
    def __init__(self, service, events, settings_repo, parent=None):
        super().__init__(parent)
        self._service = service
        self._events = events
        self._settings = settings_repo
        self._char_geom: QRect | None = None
        self._screen_geom: QRect | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.selected_iso = date.today().isoformat()
        self.view_mode = self._settings.get(policies.KEY_LAST_VIEW, "day") or "day"
        if self.view_mode not in _ORDER:
            self.view_mode = "day"
        self._show_overdue = (self._settings.get(policies.KEY_OVERDUE_PANEL, "1") or "1") == "1"

        self._root = QFrame(self)
        self._root.setObjectName("bubbleRoot")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)  # 그림자/여백
        outer.addWidget(self._root)

        self._vbox = QVBoxLayout(self._root)
        self._vbox.setContentsMargins(8, 8, 8, 8)
        self._vbox.setSpacing(6)

        self._build_header(self._vbox)
        self._view_holder = QWidget()
        self._view_layout = QVBoxLayout(self._view_holder)
        self._view_layout.setContentsMargins(0, 0, 0, 0)
        self._vbox.addWidget(self._view_holder)
        self._input = InputBar(self._service, lambda: self.selected_iso)
        self._vbox.addWidget(self._input)

        # '밀린 할일'은 말풍선과 분리된 독립 창(우측에 떠 있음)
        self._overdue_panel = OverduePanel(
            self._service, self._events, self._settings, self.open_day
        )

        self._events.todos_changed.connect(self._on_data_changed)
        self._events.delete_undo_available.connect(self._set_revert_visible)
        self._events.theme_changed.connect(self.apply_theme)
        self._events.overdue_panel_changed.connect(self._on_overdue_panel_changed)

        self.apply_theme()
        self.render()

    # ── 테마 ────────────────────────────────────────────────
    def apply_theme(self) -> None:
        mode = self._settings.get(policies.KEY_THEME, "system")
        self.setStyleSheet(theme.qss(mode))

    # ── 헤더 ────────────────────────────────────────────────
    def _build_header(self, target_layout) -> None:
        bar = QHBoxLayout()
        bar.setSpacing(2)
        self._title = QLabel()
        f = self._title.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 1)
        self._title.setFont(f)
        bar.addWidget(self._title)

        # 주간 전/다음 주 이동 (주간 모드에서만 노출, '주간' 텍스트 우측)
        self._prev_week = QToolButton()
        self._prev_week.setText("‹")  # ‹
        self._prev_week.setToolTip("이전 주")
        self._prev_week.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_week.setVisible(False)
        self._prev_week.clicked.connect(lambda: self._shift_week(-7))
        bar.addWidget(self._prev_week)

        self._next_week = QToolButton()
        self._next_week.setText("›")  # ›
        self._next_week.setToolTip("다음 주")
        self._next_week.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_week.setVisible(False)
        self._next_week.clicked.connect(lambda: self._shift_week(7))
        bar.addWidget(self._next_week)

        bar.addStretch(1)

        self._revert = QToolButton()
        self._revert.setObjectName("undoBtn")
        self._revert.setText("\u21ba")  # ↺
        self._revert.setToolTip("되돌리기")
        self._revert.setCursor(Qt.CursorShape.PointingHandCursor)
        self._revert.setVisible(False)
        self._revert.clicked.connect(self._on_revert)
        bar.addWidget(self._revert)

        self._expand = QToolButton()
        self._expand.setText("\u26f6")  # ⛶ 확장
        self._expand.setToolTip("확장 (일→주→월)")
        self._expand.setCursor(Qt.CursorShape.PointingHandCursor)
        self._expand.clicked.connect(self.cycle_expand)
        bar.addWidget(self._expand)

        self._min = QToolButton()
        self._min.setText("\u2013")  # –
        self._min.setToolTip("최소화")
        self._min.setCursor(Qt.CursorShape.PointingHandCursor)
        self._min.clicked.connect(self.hide)
        bar.addWidget(self._min)

        target_layout.addLayout(bar)

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
            view = MonthView(self.selected_iso, self._service, self.select_date, self.open_day)
        self._view_layout.addWidget(view)

        self._title.setText(self._title_text())
        is_week = self.view_mode == "week"
        self._prev_week.setVisible(is_week)
        self._next_week.setVisible(is_week)
        self.setFixedWidth(_WIDTH[self.view_mode])
        self.adjustSize()
        self.layout().activate()      # 레이아웃 즉시 확정 시도
        self._reposition()
        # 확장으로 높이가 커지는 경우, 레이아웃이 완전히 확정된 다음 한 번 더 재배치
        # (안 그러면 옛 높이로 계산되어 말풍선이 캐릭터를 덮는 문제)
        QTimer.singleShot(0, self._reposition)

    def _title_text(self) -> str:
        d = date.fromisoformat(self.selected_iso)
        wd = _WD_KR[policies.app_weekday(d)]
        label = {"day": "", "week": "  · 주간", "month": "  · 월간"}[self.view_mode]
        return f"{d.month}월 {d.day}일 ({wd}){label}"

    def select_date(self, iso: str) -> None:
        self.selected_iso = iso
        self.render()

    def _shift_week(self, days: int) -> None:
        """주간 보기에서 선택 날짜를 ±7일 이동(같은 요일 유지)해 전/다음 주로."""
        d = date.fromisoformat(self.selected_iso) + timedelta(days=days)
        self.selected_iso = d.isoformat()
        self.render()

    def open_day(self, iso: str) -> None:
        """월간 등에서 특정 날짜를 일간 보기로 연다."""
        self.selected_iso = iso
        self.view_mode = "day"
        self._settings.set(policies.KEY_LAST_VIEW, "day")
        self.render()

    def cycle_expand(self) -> None:
        idx = (_ORDER.index(self.view_mode) + 1) % len(_ORDER)
        self.view_mode = _ORDER[idx]
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

    def _on_overdue_panel_changed(self, on: bool) -> None:
        self._show_overdue = on
        self._position_overdue_panel()

    def _on_revert(self) -> None:
        self._service.undo_remove()

    # ── 배치 ────────────────────────────────────────────────
    def show_for_character(self, char_geom: QRect, screen_geom: QRect) -> None:
        self._char_geom = char_geom
        self._screen_geom = screen_geom
        self.render()
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()

    def reposition_for_character(self, char_geom: QRect, screen_geom: QRect) -> None:
        """캐릭터 드래그 중 말풍선만 따라 이동(뷰 재구성 없이 위치만)."""
        self._char_geom = char_geom
        self._screen_geom = screen_geom
        self._reposition()

    def _reposition(self) -> None:
        if self._char_geom is None or self._screen_geom is None:
            return
        self.move(self._placement(self._char_geom, self._screen_geom))
        self._position_overdue_panel()

    def _position_overdue_panel(self) -> None:
        """밀린 할일 패널을 설정된 방향(좌/우)에 붙여서 띄운다."""
        panel = self._overdue_panel
        if not self._show_overdue or not self.isVisible() or self._screen_geom is None:
            panel.hide()
            return
        panel.setFixedHeight(self.height())
        side = self._settings.get(policies.KEY_OVERDUE_PANEL_SIDE, "right")
        if side == "left":
            x = self.x() - panel.width() - _PANEL_GAP
        else:
            x = self.x() + self.width() + _PANEL_GAP
        panel.move(x, self.y())
        panel.reload()
        panel.show()
        panel.raise_()

    def hideEvent(self, e) -> None:
        # 말풍선이 숨겨지면(최소화/토글) 밀린 할일 패널도 함께 숨긴다.
        if hasattr(self, "_overdue_panel"):
            self._overdue_panel.hide()
        super().hideEvent(e)

    def _placement(self, char: QRect, scr: QRect) -> QPoint:
        """캐릭터 위치는 그대로 두고, 캐릭터를 가리지 않는 자리에 말풍선을 둔다.
        우선순위: 위 → 아래 → 오른쪽 → 왼쪽. 모두 안 되면 화면 안으로 clamp(최후)."""
        w, h = self.width(), self.height()
        # 위/아래용 가로 위치(캐릭터 중심 정렬 후 화면 안으로 clamp)
        hx = max(scr.left() + _MARGIN, min(char.center().x() - w // 2, scr.right() - w - _MARGIN))
        # 좌/우용 세로 위치(캐릭터 중심 정렬 후 clamp)
        vy = max(scr.top() + _MARGIN, min(char.center().y() - h // 2, scr.bottom() - h - _MARGIN))

        above_y = char.top() - h - _GAP
        below_y = char.bottom() + _GAP
        right_x = char.right() + _GAP
        left_x = char.left() - w - _GAP

        if above_y >= scr.top() + _MARGIN:
            return QPoint(hx, above_y)
        if below_y + h <= scr.bottom() - _MARGIN:
            return QPoint(hx, below_y)
        if right_x + w <= scr.right() - _MARGIN:
            return QPoint(right_x, vy)
        if left_x >= scr.left() + _MARGIN:
            return QPoint(left_x, vy)
        # 최후: 화면 안으로 clamp (아주 작은 화면에서만 캐릭터와 겹칠 수 있음)
        y = max(scr.top() + _MARGIN, min(above_y, scr.bottom() - h - _MARGIN))
        return QPoint(hx, y)
