"""ui/bubble/bubble_widget.py — 말풍선: 헤더(확장/닫기/최소화) + 뷰 + 입력바.

- 확장 버튼: 일간 → 주간 → 월간 → 일간(오늘) 순환
- 닫기(✕): 할일 목록만 닫고 밀린할일·타이머 패널은 캐릭터 상단으로 남긴다(즉시)
- 최소화(–): 캐릭터 클릭과 동일하게 모든 그리드를 숨긴다(설정 유지)
- 그리드 표시 설정 저장은 여기(시그널 구독자)에서 일괄 처리한다(메뉴/✕/할일클릭 공통)
- 테마(밝게/어둡게/자동) 스타일 적용
- 배치: 캐릭터 기준으로 화면 안쪽 방향으로 펼치고 화면 밖으로 안 나가게 clamp
        (캐릭터 드래그 중에는 말풍선도 따라 이동)
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
)
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QSizeGrip,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from domain import policies
from ui import theme
from ui.bubble.day_view import DayView
from ui.bubble.input_bar import InputBar
from ui.bubble.month_view import MonthView
from ui.bubble.overdue_panel import PANEL_WIDTH, OverduePanel
from ui.bubble.timer_panel import TimerPanel
from ui.bubble.todo_item import TodoItem
from ui.bubble.week_view import WeekView
from ui.qt_helpers import make_overlay_window, set_overlay_always_on_top

class _ClickableLabel(QLabel):
    """클릭하면 콜백을 호출하는 제목 라벨(날짜 인풋박스 열기용, #4)."""

    def __init__(self, on_click, parent=None):
        super().__init__(parent)
        self._on_click = on_click
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("클릭하여 날짜 이동")

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._on_click()
        else:
            super().mousePressEvent(e)


class _ResizeGrip(QSizeGrip):
    """우하단/임의 코너 크기조절 그립. 드래그 중에는 위치 재배치를 멈춰 떨림을 막고,
    드래그가 끝났을 때만 콜백으로 크기 저장·재배치를 1회 수행한다(on_start/on_end)."""

    def __init__(self, parent, on_start, on_end):
        super().__init__(parent)
        self._on_start = on_start
        self._on_end = on_end

    def mousePressEvent(self, e) -> None:
        self._on_start()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        super().mouseReleaseEvent(e)
        self._on_end()


_ORDER = ["day", "week", "month"]
_WIDTH = {"day": 240, "week": 920, "month": 470}
_GAP = 6
# 밀린 할일 패널 ↔ 말풍선 간격. 말풍선·패널 각각 8px 투명 그림자 여백이 있어
# 음수로 그 여백을 겹치게 해야 실제 보이는 간격이 좁아진다(8 + gap + 8 = 보이는 간격).
_PANEL_GAP = -10  # 보이는 간격 ≈ 6px (기존 ≈18px의 1/3)
_STACK_GAP = -10  # 같은 컬럼에서 밀린할일 ↕ 타이머 패널 세로 간격(겹치는 그림자 보정)
_SLIDE_PX = 18  # 열기/닫기 슬라이드 이동 거리(px)
_MARGIN = 6
# ✕로 목록만 닫아 패널을 캐릭터 위로 띄울 때 밀린할일 패널 높이(말풍선 높이에 안 묶임)
_DETACHED_OVERDUE_H = 220


class BubbleWidget(QWidget):
    def __init__(self, service, events, settings_repo, timer_service=None, parent=None):
        super().__init__(parent)
        self._service = service
        self._events = events
        self._settings = settings_repo
        self._timer = timer_service
        self._char_geom: QRect | None = None
        self._screen_geom: QRect | None = None
        self._anim: QParallelAnimationGroup | None = None
        # ✕ 닫기로 말풍선만 내리고 옆 컬럼 패널(밀린할일·타이머)은 화면에 남길 때 True.
        self._panels_detached = False

        make_overlay_window(self)

        self.selected_iso = date.today().isoformat()
        self._focus_todo_id: int | None = None
        self.view_mode = self._settings.get(policies.KEY_LAST_VIEW, "day") or "day"
        if self.view_mode not in _ORDER:
            self.view_mode = "day"
        self._priority_sort = self._settings.get_bool(policies.KEY_PRIORITY_SORT, False)
        self._show_overdue = self._settings.get_bool(policies.KEY_OVERDUE_PANEL, True)
        self._show_timer = self._settings.get_bool(policies.KEY_TIMER_PANEL, False)

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
        self._view_holder.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._view_layout = QVBoxLayout(self._view_holder)
        self._view_layout.setContentsMargins(0, 0, 0, 0)
        self._vbox.addWidget(self._view_holder, 1)  # 남는 높이는 목록 영역이 흡수(리사이즈)

        # 사용자 리사이즈용 우하단 그립 + 모드별 커스텀 크기/최소높이 상태
        self._sizing = False  # 프로그램적 사이징 중에는 크기 저장 안 함
        self._user_resizing = False  # 그립 드래그 중에는 재배치/저장을 미룬다(떨림 방지)
        self._placed_side = "above"  # _placement 가 고른 배치 방향(그립 코너 결정용)
        self._min_h: dict[str, int] = {}  # 모드별 최소 높이(측정 최댓값 캐시)
        self._grip = _ResizeGrip(self, self._on_resize_start, self._on_resize_end)
        self._grip.resize(16, 16)
        self._input = InputBar(self._service, lambda: self.selected_iso, self._settings)
        self._vbox.addWidget(self._input)

        # '밀린 할일'은 말풍선과 분리된 독립 창(우측에 떠 있음)
        self._overdue_panel = OverduePanel(
            self._service, self._events, self._settings, self.open_day
        )
        # '타이머' 패널(같은 컬럼에 밀린할일과 위아래로 스택)
        self._timer_panel = (
            TimerPanel(self._service, self._events, self._settings, self._timer)
            if self._timer is not None else None
        )

        self._events.todos_changed.connect(self._on_data_changed)
        self._events.theme_changed.connect(self.apply_theme)
        self._events.overdue_panel_changed.connect(self._on_overdue_panel_changed)
        self._events.timer_panel_changed.connect(self._on_timer_panel_changed)
        if self._timer is not None:
            self._events.timer_started.connect(self._auto_open_timer_panel)
            self._events.timer_started.connect(self._on_timer_state)
            self._events.timer_stopped.connect(self._on_timer_state)
            self._events.timer_finished.connect(self._on_timer_state)
            # 정지/재개 시 패널 높이가 바뀌므로(완료/초기화 버튼 자리) 컬럼 재배치
            self._events.timer_paused.connect(self._on_timer_pause)
            self._events.timer_resumed.connect(self._on_timer_pause)

        self.apply_theme()
        self.render()

    # ── 테마 ────────────────────────────────────────────────
    def apply_theme(self) -> None:
        mode = self._settings.get(policies.KEY_THEME, "system")
        self.setStyleSheet(theme.qss(mode))

    def set_always_on_top(self, on: bool) -> None:
        set_overlay_always_on_top(self, on)
        set_overlay_always_on_top(self._overdue_panel, on)
        if self._timer_panel is not None:
            set_overlay_always_on_top(self._timer_panel, on)

    # ── 헤더 ────────────────────────────────────────────────
    def _build_header(self, target_layout) -> None:
        bar = QHBoxLayout()
        bar.setSpacing(1)  # 버튼 간격 최소화(#7) — 패딩은 headerBtn QSS 로 좁힘
        # 제목(날짜) 클릭 → 날짜 인풋박스 열기(#4)
        self._title = _ClickableLabel(self._open_date_editor)
        self._title.setObjectName("bubbleTitle")
        f = self._title.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 1)
        self._title.setFont(f)
        bar.addWidget(self._title)

        # 날짜 인풋박스(일/월/연도) — 평소 숨김, 제목 클릭 시 노출(#4)
        self._date_editor = self._build_date_editor()
        self._date_editor.setVisible(False)
        bar.addWidget(self._date_editor)

        # 주간 전/다음 주 이동 (주간 모드에서만 노출, '주간' 텍스트 우측)
        self._prev_week = self._nav_btn("‹", "이전 주", lambda: self._shift_week(-7))
        bar.addWidget(self._prev_week)
        self._next_week = self._nav_btn("›", "다음 주", lambda: self._shift_week(7))
        bar.addWidget(self._next_week)

        # 일간 전/다음 날 이동 (일간 모드에서만 노출, 날짜 우측의 ‹ ›)
        self._prev_day = self._nav_btn("‹", "이전 날", lambda: self._shift_day(-1))
        bar.addWidget(self._prev_day)
        self._next_day = self._nav_btn("›", "다음 날", lambda: self._shift_day(1))
        bar.addWidget(self._next_day)

        # 월간 전/다음 달 이동 (월간 모드에서만 노출) — 1일이 일요일이라 이전 달 진입이
        # 막히던 문제 해소(#6).
        self._prev_month = self._nav_btn("‹", "이전 달", lambda: self._shift_month(-1))
        bar.addWidget(self._prev_month)
        self._next_month = self._nav_btn("›", "다음 달", lambda: self._shift_month(1))
        bar.addWidget(self._next_month)

        bar.addStretch(1)

        # 되돌리기(↺)는 캐릭터 우클릭 메뉴로 이동(헤더 버튼 과밀 해소).

        # 오늘로 이동 (주간/월간에서만 노출, 전환버튼 왼쪽)
        self._today_btn = self._nav_btn("오늘", "오늘로 이동", self.go_today)
        bar.addWidget(self._today_btn)

        self._sort_btn = QToolButton()
        self._sort_btn.setObjectName("prioritySortBtn")
        self._sort_btn.setIcon(QIcon(_sort_pixmap()))
        self._sort_btn.setCheckable(True)
        self._sort_btn.setToolTip("중요도 높은순")
        self._sort_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sort_btn.toggled.connect(self._on_priority_sort_changed)
        bar.addWidget(self._sort_btn)

        self._expand = QToolButton()
        self._expand.setObjectName("headerBtn")
        self._expand.setText("\u26f6")  # ⛶ 확장
        self._expand.setToolTip("확장 (일→주→월)")
        self._expand.setCursor(Qt.CursorShape.PointingHandCursor)
        self._expand.clicked.connect(self.cycle_expand)
        bar.addWidget(self._expand)

        self._min = QToolButton()
        self._min.setObjectName("headerBtn")
        self._min.setText("\u2013")  # –
        self._min.setToolTip("최소화 (모두 숨김)")
        self._min.setCursor(Qt.CursorShape.PointingHandCursor)
        self._min.clicked.connect(self._minimize)
        bar.addWidget(self._min)
        # 닫기(✕) 버튼은 제거 — 목록만 닫기(패널 유지)는 우클릭 메뉴의 '할일 목록 표시'
        # 토글로 수행한다(#5). close_keep_panels() 메서드는 그 경로에서 계속 쓰인다.

        target_layout.addLayout(bar)

    def _nav_btn(self, text: str, tip: str, slot, always: bool = False) -> QToolButton:
        """헤더용 좁은 툴버튼 생성(#7: objectName=headerBtn 으로 패딩 축소).
        always=False 면 기본 숨김(모드별로 _render_body 가 표시 제어)."""
        b = QToolButton()
        b.setObjectName("headerBtn")
        b.setText(text)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if not always:
            b.setVisible(False)
        b.clicked.connect(slot)
        return b

    # ── 날짜 인풋박스(#4) ───────────────────────────────────
    def _build_date_editor(self) -> QWidget:
        """년/월/일 스핀박스 + 이동 버튼. 모드별로 '일' 입력은 _open_date_editor 가 토글."""
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)

        self._year_spin = QSpinBox()
        self._year_spin.setObjectName("dateSpin")
        self._year_spin.setRange(1970, 2100)
        self._year_spin.setSuffix("년")
        self._month_spin = QSpinBox()
        self._month_spin.setObjectName("dateSpin")
        self._month_spin.setRange(1, 12)
        self._month_spin.setSuffix("월")
        self._month_spin.setWrapping(True)
        self._day_spin = QSpinBox()
        self._day_spin.setObjectName("dateSpin")
        self._day_spin.setRange(1, 31)
        self._day_spin.setSuffix("일")
        self._day_spin.setWrapping(True)
        for sp in (self._year_spin, self._month_spin, self._day_spin):
            sp.lineEdit().returnPressed.connect(self._commit_date_editor)
        # 월/연도 변경 시 '일' 상한을 그 달 말일로 맞춘다.
        self._year_spin.valueChanged.connect(self._clamp_day_max)
        self._month_spin.valueChanged.connect(self._clamp_day_max)

        go = QToolButton()
        go.setObjectName("headerBtn")
        go.setText("이동")
        go.setToolTip("해당 날짜로 이동")
        go.setCursor(Qt.CursorShape.PointingHandCursor)
        go.clicked.connect(self._commit_date_editor)

        row.addWidget(self._year_spin)
        row.addWidget(self._month_spin)
        row.addWidget(self._day_spin)
        row.addWidget(go)
        return box

    def _clamp_day_max(self) -> None:
        last = calendar.monthrange(self._year_spin.value(), self._month_spin.value())[1]
        if self._day_spin.value() > last:
            self._day_spin.setValue(last)
        self._day_spin.setMaximum(last)

    def _open_date_editor(self) -> None:
        """제목 클릭: 현재 선택 날짜로 인풋을 채우고 노출(월간은 '일' 입력 숨김)."""
        d = date.fromisoformat(self.selected_iso)
        self._year_spin.setValue(d.year)
        self._month_spin.setValue(d.month)
        self._clamp_day_max()
        self._day_spin.setValue(d.day)
        self._day_spin.setVisible(self.view_mode != "month")  # 월간은 일 불필요
        # 일간은 폭이 좁아 스핀박스 공간 확보를 위해 나머지 버튼 숨김
        if self.view_mode == "day":
            for w in (self._prev_day, self._next_day, self._today_btn,
                      self._expand, self._min):
                w.setVisible(False)
        self._title.setVisible(False)
        self._date_editor.setVisible(True)
        self._year_spin.setFocus()
        self._year_spin.selectAll()

    def _commit_date_editor(self) -> None:
        """인풋 확정: 선택 날짜로 이동(현재 보기 모드 유지). render 가 제목을 복원."""
        if not self._date_editor.isVisible():
            return
        y, m = self._year_spin.value(), self._month_spin.value()
        last = calendar.monthrange(y, m)[1]
        d = 1 if self.view_mode == "month" else min(self._day_spin.value(), last)
        self.select_date(date(y, m, d).isoformat())

    # ── 렌더 ────────────────────────────────────────────────
    def render(self) -> None:
        # 보기 모드(일/주/월)가 바뀐 렌더면 새 뷰를 부드럽게 페이드 인(#13)
        view_changed = getattr(self, "_rendered_view", self.view_mode) != self.view_mode
        # 뷰를 헐고 다시 짓는 동안의 중간 페인트를 막아 깜빡임/버벅임을 줄인다.
        self.setUpdatesEnabled(False)
        try:
            self._render_body()
        finally:
            self.setUpdatesEnabled(True)
        self._rendered_view = self.view_mode
        if view_changed and self._anim_enabled() and self.isVisible():
            self._play_view_fade()

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

    def _play_view_fade(self) -> None:
        """일→주→월 등 보기 전환 시 새 뷰 영역을 0→1 로 부드럽게 페이드 인(#13)."""
        eff = QGraphicsOpacityEffect(self._view_holder)
        self._view_holder.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(180)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: self._view_holder.setGraphicsEffect(None))
        self._view_anim = anim  # GC 방지용 참조 유지
        anim.start()

    def _render_body(self) -> None:
        while self._view_layout.count():
            w = self._view_layout.takeAt(0).widget()
            if w:
                w.deleteLater()

        # parent 를 view_holder 로 지정해 '레이아웃 추가 전 잠깐 최상위 창이 되는' 깜빡임 방지
        holder = self._view_holder
        if self.view_mode == "day":
            focus_todo_id = self._focus_todo_id
            self._focus_todo_id = None
            view = DayView(self.selected_iso, self._service, self._timer, self._settings,
                           self._events, holder, focus_todo_id=focus_todo_id,
                           priority_sort=self._priority_sort)
        elif self.view_mode == "week":
            view = WeekView(self.selected_iso, self._service, self.select_date,
                            self.open_day, self._timer, self._settings, self._events, holder,
                            priority_sort=self._priority_sort)
        else:
            view = MonthView(self.selected_iso, self._service, self.select_date,
                             self.open_day, holder)
        self._view_layout.addWidget(view)

        # 렌더 시 날짜 인풋박스는 닫고 제목을 복원한다(편집 중 외부 갱신 대비, #4)
        self._date_editor.setVisible(False)
        self._title.setVisible(True)
        self._title.setText(self._title_text())
        # 오늘(일)/이번 주(주)/이번 달(월)이면 제목을 강조색으로
        self._title.setProperty("today", "true" if self._title_is_today() else "false")
        self._title.style().unpolish(self._title)
        self._title.style().polish(self._title)
        # 날짜 인풋 열 때 숨겼던 확장/최소화 버튼 복원(_open_date_editor 대응)
        self._expand.setVisible(True)
        self._min.setVisible(True)
        is_week = self.view_mode == "week"
        self._prev_week.setVisible(is_week)
        self._next_week.setVisible(is_week)
        is_day = self.view_mode == "day"
        self._prev_day.setVisible(is_day)
        self._next_day.setVisible(is_day)
        is_month = self.view_mode == "month"
        self._prev_month.setVisible(is_month)
        self._next_month.setVisible(is_month)
        # 주/월간은 항상, 일간은 오늘이 아닐 때만 '오늘로 이동' 노출(#1)
        self._today_btn.setVisible(
            self.view_mode in ("week", "month")
            or (self.view_mode == "day" and not self._title_is_today())
        )
        self._sort_btn.setVisible(self.view_mode in ("day", "week"))
        self._sort_btn.setChecked(self._priority_sort)
        # 콘텐츠 기준 크기를 '최소'로 두고, 그 이상은 사용자가 우하단 그립으로 키운다.
        self._sizing = True
        self.setMaximumSize(16_777_215, 16_777_215)  # 이전 고정 해제
        self.setMinimumSize(0, 0)
        self.setMinimumWidth(_WIDTH[self.view_mode])
        self.adjustSize()
        # 중첩 레이아웃(주/월)의 최소높이가 동기 반영되도록 LayoutRequest 를 즉시 처리.
        QApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
        self._update_min_height()     # 모드별 floor(과소측정 방지: 최댓값 캐시)
        self._restore_size()          # 저장된 커스텀 크기가 있으면 복원(최소 이상)
        self._sizing = False
        self.layout().activate()
        self._reposition()
        # 레이아웃 완전 확정 후(이벤트 루프 1회) 최소높이 재측정·보정 + 재배치
        QTimer.singleShot(0, self._finalize_size)

    def _title_text(self) -> str:
        d = date.fromisoformat(self.selected_iso)
        if self.view_mode == "week":
            month, wk = policies.week_of_month(d)
            return f"{month}월 {wk}주차"
        if self.view_mode == "month":
            return f"{d.month}월"
        return policies.fmt_md(d)

    def _title_is_today(self) -> bool:
        """제목을 강조색으로 칠할지: 일=오늘 날짜, 주=이번 주 포함, 월=이번 달."""
        d = date.fromisoformat(self.selected_iso)
        today = date.today()
        if self.view_mode == "week":
            s, e = policies.week_range(d)
            return s <= today <= e
        if self.view_mode == "month":
            return (today.year, today.month) == (d.year, d.month)
        return self.selected_iso == today.isoformat()

    def select_date(self, iso: str) -> None:
        self.selected_iso = iso
        self.render()

    def go_today(self) -> None:
        """현재 보기 모드를 유지한 채 오늘로 이동(일=오늘, 주=이번 주, 월=이번 달)."""
        self.selected_iso = date.today().isoformat()
        self.render()

    def _shift_week(self, days: int) -> None:
        """주간 보기에서 선택 날짜를 ±7일 이동(같은 요일 유지)해 전/다음 주로."""
        d = date.fromisoformat(self.selected_iso) + timedelta(days=days)
        self.selected_iso = d.isoformat()
        self.render()

    def _shift_day(self, days: int) -> None:
        """일간 보기에서 선택 날짜를 ±1일 이동(날짜 우측 ‹ › 버튼)."""
        d = date.fromisoformat(self.selected_iso) + timedelta(days=days)
        self.selected_iso = d.isoformat()
        self.render()

    def _shift_month(self, months: int) -> None:
        """월간 보기에서 선택 날짜를 ±N개월 이동(날짜는 말일로 clamp). 그 달 1일이
        일요일이라 그리드만으로는 이전 달로 못 넘어가던 문제를 해소한다(#6)."""
        d = date.fromisoformat(self.selected_iso)
        idx = d.year * 12 + (d.month - 1) + months
        y, m = divmod(idx, 12)
        m += 1
        day = min(d.day, calendar.monthrange(y, m)[1])
        self.selected_iso = date(y, m, day).isoformat()
        self.render()

    def open_day(self, iso: str, focus_todo_id: int | None = None) -> None:
        """월간 등에서 특정 날짜를 일간 보기로 연다."""
        self.selected_iso = iso
        self._focus_todo_id = focus_todo_id
        self.view_mode = "day"
        self._settings.set(policies.KEY_LAST_VIEW, "day")
        self.render()
        QTimer.singleShot(0, self.raise_)

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

    def _on_priority_sort_changed(self, enabled: bool) -> None:
        self._priority_sort = enabled
        self._settings.set_bool(policies.KEY_PRIORITY_SORT, enabled)
        if self.isVisible() and self.view_mode in ("day", "week"):
            self.render()

    def _on_overdue_panel_changed(self, on: bool) -> None:
        """밀린할일 표시 토글(메뉴/✕/escape 공통): 설정 저장 + 배치를 한 곳에서 처리."""
        self._settings.set_bool(policies.KEY_OVERDUE_PANEL, on)
        self._show_overdue = on
        self._position_left_column()

    def _on_timer_panel_changed(self, on: bool) -> None:
        """타이머 표시 토글(메뉴/✕/자동열기/할일클릭 공통): 설정 저장 + 배치를 한 곳에서 처리."""
        self._settings.set_bool(policies.KEY_TIMER_PANEL, on)
        self._show_timer = on
        self._position_left_column()
        if self.isVisible() or self._panels_detached:
            QTimer.singleShot(0, self._position_left_column)

    def _auto_open_timer_panel(self, tid: int) -> None:
        """할일 타이머가 닫힌 패널 상태에서 시작되면 타이머 패널을 자동으로 켠다(#B1).
        일반(상시) 타이머는 패널에서 직접 시작하므로 제외한다.
        설정 저장·배치는 _on_timer_panel_changed 가 일괄 처리한다."""
        from services.timer_service import STANDALONE_ID

        if self._timer_panel is None or tid == STANDALONE_ID or self._show_timer:
            return
        self._events.timer_panel_changed.emit(True)

    def _on_timer_state(self, *_a) -> None:
        """타이머 시작/해제/만료 → 할일 행 아이콘 교체 위해 재렌더(보이는 동안만)."""
        if self.isVisible():
            self.render()  # render → _reposition → _position_left_column

    def _on_timer_pause(self, *_a) -> None:
        """정지/재개 → 타이머 패널 높이(완료/초기화 버튼 자리)만 다시 맞춤(뷰 재구성 불필요)."""
        if self.isVisible():
            self._position_left_column()

    def _minimize(self) -> None:
        """– 최소화(헤더 버튼): 캐릭터 클릭과 동일하게 모든 그리드를 숨긴다(설정 유지, #4)."""
        self.minimize_all()

    def minimize_all(self) -> None:
        """모든 그리드(말풍선·패널)를 숨긴다 — 캐릭터 클릭/– 최소화 공통 진입점.
        설정값(체크 상태)은 건드리지 않는다(#4). 말풍선이 떠 있으면 슬라이드 애니메이션,
        detached 패널만 떠 있으면 즉시 숨긴다. 완료되면 bubble_closed 로 캐릭터를 동기화."""
        if self.isVisible():
            self.hide_animated()        # done 에서 hide + bubble_closed
        else:
            self.hide_all_panels()      # ✕로 남겨둔 패널만 즉시 숨김
            self._events.bubble_closed.emit()

    def close_keep_panels(self) -> None:
        """✕ 닫기(헤더 버튼): 할일 목록 그리드만 끄고(KEY_LIST_SHOW=0) 밀린할일·타이머
        패널은 캐릭터 상단으로 옮겨 화면에 남긴다. 즉시 처리(애니메이션 없음, #1).
        남길 패널이 없으면 전체 최소화와 동일(역시 즉시)."""
        self._settings.set_bool(policies.KEY_LIST_SHOW, False)
        self._stop_anim()
        self._panels_detached = self._show_overdue or self._show_timer
        if self._panels_detached:
            self._position_panels_detached()   # 패널을 캐릭터 상단 중앙으로 이동
        self.hide()                            # 말풍선 즉시 숨김(detached 아니면 hideEvent 가 패널도 숨김)
        self._events.bubble_closed.emit()

    # ── 슬라이드 인/아웃 애니메이션(말풍선 + 옆 컬럼 패널 함께) ──────
    # 열기=아래에서 위로 올라오며 등장, 닫기=위에서 아래로 내려가며 사라짐.
    def _anim_enabled(self) -> bool:
        return self._settings.get_bool(policies.KEY_BUBBLE_ANIMATION, True)

    def _slide_targets(self) -> list:
        """현재 보이는(또는 곧 보일) 말풍선 + 옆 컬럼 패널을 (위젯, 최종좌표)로."""
        out = [(self, self.pos())]
        if self._overdue_panel.isVisible():
            out.append((self._overdue_panel, self._overdue_panel.pos()))
        if self._timer_panel is not None and self._timer_panel.isVisible():
            out.append((self._timer_panel, self._timer_panel.pos()))
        return out

    def _stop_anim(self) -> None:
        if self._anim is not None:
            self._anim.stop()
            self._anim = None

    def _build_slide(self, targets: list, dy_from: int, dy_to: int,
                     curve: QEasingCurve.Type, dur: int) -> QParallelAnimationGroup:
        """targets: [(위젯, 최종좌표)]. 최종좌표 기준 y+dy_from → y+dy_to 로 이동."""
        grp = QParallelAnimationGroup(self)
        for w, final in targets:
            a = QPropertyAnimation(w, b"pos", grp)
            a.setDuration(dur)
            a.setStartValue(QPoint(final.x(), final.y() + dy_from))
            a.setEndValue(QPoint(final.x(), final.y() + dy_to))
            a.setEasingCurve(curve)
            grp.addAnimation(a)
        return grp

    def _play_open(self, targets: list | None = None) -> None:
        """아래(+SLIDE)에서 최종 위치로 슬라이드 인 + 짧은 페이드로 등장 보정.
        _reposition/show 가 패널·말풍선을 '최종 위치'에 먼저 띄우므로, 같은 호출 스택에서
        (이벤트 루프 복귀 전) opacity 0 으로 덮고 시작 위치로 내려둔다. 그래서 첫 페인트가
        최종 위치에서 번쩍이며 '위에서 덜컥' 떨어지는 일이 없고, 페이드가 잔여 점프를 가린다."""
        self._stop_anim()
        targets = targets or self._slide_targets()
        for w, final in targets:
            w.setWindowOpacity(0.0)                     # 최종 위치 첫 페인트를 덮음
            w.move(final.x(), final.y() + _SLIDE_PX)    # 시작 위치(아래)로
        grp = QParallelAnimationGroup(self)
        for w, final in targets:
            pa = QPropertyAnimation(w, b"pos", grp)
            pa.setDuration(220)
            pa.setStartValue(QPoint(final.x(), final.y() + _SLIDE_PX))
            pa.setEndValue(QPoint(final.x(), final.y()))
            pa.setEasingCurve(QEasingCurve.Type.OutCubic)
            grp.addAnimation(pa)
            oa = QPropertyAnimation(w, b"windowOpacity", grp)
            oa.setDuration(150)
            oa.setStartValue(0.0)
            oa.setEndValue(1.0)
            oa.setEasingCurve(QEasingCurve.Type.OutCubic)
            grp.addAnimation(oa)
        self._anim = grp
        self._anim.start()

    def hide_animated(self) -> None:
        """말풍선+패널을 아래로 슬라이드 아웃한 뒤 hide(캐릭터 클릭/– 최소화 경로).
        애니메이션이 꺼져 있으면 즉시 닫는다. 끝나면 bubble_closed 로 캐릭터를 동기화."""
        if not self._anim_enabled() or not self.isVisible():
            self.hide()
            self._events.bubble_closed.emit()
            return
        self._stop_anim()
        targets = self._slide_targets()
        self._anim = self._build_slide(
            targets, 0, _SLIDE_PX, QEasingCurve.Type.InCubic, 160
        )

        def done() -> None:
            self.hide()  # hideEvent 가 옆 컬럼 패널도 함께 숨김
            for w, final in targets:
                w.move(final)           # 다음 표시를 위해 위치 복원
                w.setWindowOpacity(1.0)  # 중단된 open 으로 반투명하게 남는 것 방지
            self._events.bubble_closed.emit()

        self._anim.finished.connect(done)
        self._anim.start()

    # ── 배치 ────────────────────────────────────────────────
    def show_for_character(self, char_geom: QRect, screen_geom: QRect) -> None:
        self._char_geom = char_geom
        self._screen_geom = screen_geom
        self._panels_detached = False  # 다시 열리면 패널은 말풍선 옆 컬럼으로 복귀
        self._settings.set_bool(policies.KEY_LIST_SHOW, True)  # 목록 그리드 ON 상태로 기록
        animate = self._anim_enabled()
        if animate:
            self._stop_anim()
            self.setWindowOpacity(0.0)
            self._overdue_panel.setWindowOpacity(0.0 if self._show_overdue else 1.0)
            if self._timer_panel is not None:
                self._timer_panel.setWindowOpacity(0.0 if self._show_timer else 1.0)
        self.render()  # 최소/저장 크기까지 여기서 확정(별도 adjustSize 금지: 커스텀 크기 덮어씀)
        # 위치를 먼저 잡고(이동) show → 첫 표시 시 엉뚱한 위치 깜빡임 방지
        self.move(self._placement(char_geom, screen_geom))
        self.show()
        self.raise_()
        # show 뒤에 패널 배치: _position_left_column 은 isVisible 가드가 있어
        # show 전에 부르면 패널을 숨기고 빠져나간다. 이제 패널들도 표시돼
        # _play_open 의 _slide_targets 에 잡혀 함께 슬라이드+페이드된다.
        self._reposition()
        self._events.bubble_opened.emit()  # 캐릭터 '목록 열림' 이미지 전환(#12)
        if animate:
            self._play_open(self._slide_targets())
        else:
            self.setWindowOpacity(1.0)
            self._overdue_panel.setWindowOpacity(1.0)
            if self._timer_panel is not None:
                self._timer_panel.setWindowOpacity(1.0)

    def reposition_for_character(self, char_geom: QRect, screen_geom: QRect) -> None:
        """캐릭터 드래그 중 말풍선만 따라 이동(뷰 재구성 없이 위치만)."""
        self._char_geom = char_geom
        self._screen_geom = screen_geom
        self._reposition()

    def _reposition(self) -> None:
        if self._char_geom is None or self._screen_geom is None:
            return
        self.move(self._placement(self._char_geom, self._screen_geom))
        self._update_grip()
        self._position_left_column()

    # ── 사용자 리사이즈(우하단 그립) + 모드별 크기 기억 ──────────
    def _saved_size(self, mode: str) -> tuple[int, int]:
        raw = self._settings.get(policies.KEY_BUBBLE_SIZE_PREFIX + mode, "") or ""
        if "x" in raw:
            try:
                w, h = raw.split("x", 1)
                return int(w), int(h)
            except ValueError:
                pass
        return 0, 0

    def _restore_size(self) -> None:
        """저장된 커스텀 크기로 복원(없거나 작으면 최소 크기 유지)."""
        w, h = self._saved_size(self.view_mode)
        self.resize(max(w, self.minimumWidth()), max(h, self.minimumHeight()))

    def _update_min_height(self) -> None:
        """모드별 최소 높이 = 현재 레이아웃의 minimumSizeHint."""
        mh = self.minimumSizeHint().height()
        self._min_h[self.view_mode] = mh
        self.setMinimumSize(_WIDTH[self.view_mode], self._min_h[self.view_mode])

    def _finalize_size(self) -> None:
        """이벤트 루프가 한 번 돈 뒤(레이아웃 확정) 최소높이를 다시 측정해 보정."""
        prev = self._min_h.get(self.view_mode, 0)
        self._update_min_height()
        if self._min_h[self.view_mode] > prev:
            self._sizing = True
            self._restore_size()
            self._sizing = False
        self._reposition()

    def _update_grip(self) -> None:
        """캐릭터 반대편 코너로 크기조절 그립을 둔다. 배치 방향(_placed_side)으로
        '캐릭터를 마주본 가장자리'를 알아내 그 반대 모서리에 그립을 두면, QSizeGrip 이
        대각선 반대(=캐릭터 쪽) 코너를 고정해 캐릭터 반대 방향으로 자란다."""
        g = getattr(self, "_grip", None)
        if g is None:
            return
        gw, gh = g.width(), g.height()
        side = self._placed_side
        char = self._char_geom
        if side == "above":      # 캐릭터가 버블 아래 → 그립 위쪽
            gy = 3
        elif side == "below":    # 캐릭터가 버블 위 → 그립 아래쪽
            gy = self.height() - gh - 3
        else:                    # 좌/우 배치: 세로는 캐릭터 중심 반대편
            below = char is not None and char.center().y() > self.y() + self.height() / 2
            gy = 3 if below else self.height() - gh - 3
        if side == "left":       # 캐릭터가 버블 오른쪽 → 그립 왼쪽
            gx = 3
        elif side == "right":    # 캐릭터가 버블 왼쪽 → 그립 오른쪽
            gx = self.width() - gw - 3
        else:                    # 위/아래 배치: 가로는 캐릭터 중심 반대편
            right = char is not None and char.center().x() > self.x() + self.width() / 2
            gx = 3 if right else self.width() - gw - 3
        g.move(gx, gy)
        g.raise_()

    def _on_resize_start(self) -> None:
        """그립 드래그 시작: 드래그 동안 재배치/저장을 멈춘다(떨림·깜빡임 방지)."""
        self._user_resizing = True

    def _on_resize_end(self) -> None:
        """그립 드래그 종료: 최종 크기를 1회 저장하고 위치를 1회 정리(A안)."""
        self._user_resizing = False
        if self._sizing or not self.isVisible():
            return
        self._save_size()
        self._reposition()  # 화면 밖 clamp + 옆 패널 재배치 1회

    def _save_size(self) -> None:
        self._settings.set(policies.KEY_BUBBLE_SIZE_PREFIX + self.view_mode,
                           f"{self.width()}x{self.height()}")

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._update_grip()
        QTimer.singleShot(0, self._refresh_todo_text_layouts)
        # 드래그 중에는 위치를 QSizeGrip 에 맡긴다(그립이 캐릭터 반대편 코너에 있어
        # 대각선=캐릭터 쪽 코너가 고정됨). move()/저장은 release 에서 1회만 → 떨림 제거.
        if self._user_resizing:
            return
        # 드래그가 아닌 비프로그램적 리사이즈(드물게): 기존처럼 저장만(재배치는 _reposition 경로가 담당)
        if not getattr(self, "_sizing", False) and self.isVisible():
            self._save_size()

    def _refresh_todo_text_layouts(self) -> None:
        for item in self.findChildren(TodoItem):
            item.refresh_text_layout()

    def _timer_active(self) -> bool:
        return self._timer is not None and self._timer.is_active()

    def timer_panel_visible(self) -> bool:
        """타이머 패널이 현재 화면에 떠 있는지(✕로 말풍선만 닫고 패널을 남긴 경우 포함)."""
        return self._timer_panel is not None and self._timer_panel.isVisible()

    def _column_x(self) -> int:
        """좌/우 컬럼 패널의 x 좌표(밀린할일·타이머 공통 폭)."""
        side = self._settings.get(policies.KEY_OVERDUE_PANEL_SIDE, "right")
        if side == "left":
            return self.x() - self._overdue_panel.width() - _PANEL_GAP
        return self.x() + self.width() + _PANEL_GAP

    def _position_left_column(self) -> None:
        """밀린 할일 + 타이머 패널을 같은 컬럼에 위아래로 배치한다.
        - 밀린할일 ON,  타이머 X  : 밀린할일 전체 높이
        - 밀린할일 ON,  타이머 O  : 밀린할일(축소) + 타이머
        - 밀린할일 OFF, 타이머 O  : 타이머 단독
        - 밀린할일 OFF, 타이머 X  : 둘 다 숨김"""
        overdue = self._overdue_panel
        timer = self._timer_panel
        # 말풍선이 숨겨졌고 ✕로 패널을 남긴 상태(_panels_detached)가 아니면 패널도 숨긴다.
        # detached 상태에선 말풍선이 hide 돼도 마지막 지오메트리로 패널 자리를 유지한다.
        if self._screen_geom is None or (not self.isVisible() and not self._panels_detached):
            overdue.hide()
            if timer is not None:
                timer.hide()
            return

        # ✕로 목록만 닫은 상태: 말풍선 옆이 아니라 캐릭터 상단 중앙으로 패널을 띄운다.
        if self._panels_detached:
            self._position_panels_detached()
            return

        # 타이머 패널 노출은 '상시 표시 설정'으로만 제어(✕ 로 확실히 닫히고, 닫혀도 타이머는 계속 진행 #10).
        # 도는 타이머는 말풍선을 내릴 때 캐릭터 옆 타이머 풍선으로 보인다.
        timer_on = self._show_timer and timer is not None
        x = self._column_x()
        top = self.y()
        col_h = self.height()

        if self._show_overdue and timer_on:
            # 타이머는 상태별 고정 높이(셀 정사각형 유지), 밀린할일이 나머지를 채운다.
            tb = timer.block_height()
            overdue_h = col_h - tb - _STACK_GAP
            overdue.setFixedHeight(overdue_h)
            overdue.move(x, top)
            overdue.reload()
            overdue.setWindowOpacity(1.0)
            overdue.show()
            overdue.raise_()
            timer.setFixedHeight(tb)
            timer.move(x, top + overdue_h + _STACK_GAP)
            timer.reload()
            timer.setWindowOpacity(1.0)
            timer.show()
            timer.raise_()
        elif timer_on:
            overdue.hide()
            timer.setFixedHeight(timer.block_height())
            timer.move(x, top)
            timer.reload()
            timer.setWindowOpacity(1.0)
            timer.show()
            timer.raise_()
        elif self._show_overdue:
            if timer is not None:
                timer.setWindowOpacity(1.0)
                timer.hide()
            overdue.setFixedHeight(col_h)
            overdue.move(x, top)
            overdue.reload()
            overdue.setWindowOpacity(1.0)
            overdue.show()
            overdue.raise_()
        else:
            overdue.hide()
            if timer is not None:
                timer.hide()

    def reposition_detached_panels(self, char_geom: QRect, screen_geom: QRect) -> None:
        """캐릭터 드래그 중, ✕로 남겨 둔 패널이 캐릭터를 따라 상단 중앙에 머물게 한다."""
        if not self._panels_detached:
            return
        self._char_geom = char_geom
        self._screen_geom = screen_geom
        self._position_panels_detached()

    def show_detached_panels(self, char_geom: QRect, screen_geom: QRect) -> None:
        """할일 목록은 닫힌 채(KEY_LIST_SHOW=0) 밀린할일·타이머 패널만 캐릭터 상단에 띄운다."""
        self._char_geom = char_geom
        self._screen_geom = screen_geom
        self._panels_detached = True
        self._overdue_panel.reload()
        if self._timer_panel is not None:
            self._timer_panel.reload()
        self._position_panels_detached()

    def hide_all_panels(self) -> None:
        """떠 있던(detached) 패널을 모두 숨긴다(전체 최소화 경로)."""
        self._panels_detached = False
        self._overdue_panel.hide()
        if self._timer_panel is not None:
            self._timer_panel.hide()

    def any_panel_visible(self) -> bool:
        """밀린할일·타이머 패널 중 하나라도 화면에 떠 있는지."""
        if self._overdue_panel.isVisible():
            return True
        return self._timer_panel is not None and self._timer_panel.isVisible()

    def any_grid_visible(self) -> bool:
        """그리드(말풍선 목록 또는 옆 패널)가 하나라도 떠 있는지 = '최소화 아님' 판정.
        캐릭터 클릭 토글·메뉴·'할일 n개' 풍선이 공통으로 쓰는 단일 술어."""
        return self.isVisible() or self.any_panel_visible()

    def grid_intent(self) -> tuple[bool, bool, bool]:
        """설정에 저장된 각 그리드(목록·밀린할일·타이머)의 표시 의도(on/off).
        캐릭터 클릭 복원(_restore_grids)·시작 복원(restore_on_startup) 공통 진실 소스."""
        s = self._settings
        return (
            s.get_bool(policies.KEY_LIST_SHOW, True),
            s.get_bool(policies.KEY_OVERDUE_PANEL, True),
            s.get_bool(policies.KEY_TIMER_PANEL, False),
        )

    def _position_panels_detached(self) -> None:
        """✕로 목록만 닫았을 때 밀린할일·타이머 패널을 캐릭터 상단 중앙에 세로로 쌓는다.
        위 공간이 부족하면 캐릭터 아래로 내린다. 컬럼 모드와 달리 말풍선 높이에 묶이지 않는다."""
        overdue = self._overdue_panel
        timer = self._timer_panel
        if self._char_geom is None or self._screen_geom is None:
            return
        timer_on = self._show_timer and timer is not None

        # 표시할 패널을 위→아래 순서로(밀린할일 위, 타이머 아래) 모으고 높이를 정한다.
        parts: list = []
        if self._show_overdue:
            overdue.setFixedHeight(_DETACHED_OVERDUE_H)
            parts.append(overdue)
        else:
            overdue.hide()
        if timer_on:
            timer.setFixedHeight(timer.block_height())
            parts.append(timer)
        elif timer is not None:
            timer.hide()
        if not parts:
            return

        char, scr = self._char_geom, self._screen_geom
        total_h = sum(p.height() for p in parts) + _STACK_GAP * (len(parts) - 1)
        x = max(scr.left() + _MARGIN,
                min(char.center().x() - PANEL_WIDTH // 2, scr.right() - PANEL_WIDTH - _MARGIN))
        top = char.top() - _GAP - total_h
        if top < scr.top() + _MARGIN:      # 위 공간 부족 → 캐릭터 아래로
            top = char.bottom() + _GAP
        y = top
        for p in parts:
            p.move(x, y)
            p.show()
            p.raise_()
            y += p.height() + _STACK_GAP

    def hideEvent(self, e) -> None:
        # 말풍선이 숨겨지면(최소화/토글) 같은 컬럼 패널들도 함께 숨긴다.
        # 단, ✕ 닫기(_panels_detached)는 패널을 화면에 남겨 둔다.
        if not self._panels_detached:
            if hasattr(self, "_overdue_panel"):
                self._overdue_panel.hide()
            if getattr(self, "_timer_panel", None) is not None:
                self._timer_panel.hide()
        super().hideEvent(e)

    def _placement(self, char: QRect, scr: QRect) -> QPoint:
        """캐릭터 위치는 그대로 두고, 캐릭터를 가리지 않는 자리에 말풍선을 둔다.
        우선순위: 위 → 아래 → 오른쪽 → 왼쪽. 모두 안 되면 화면 안으로 clamp(최후).
        밀린 할일 패널이 켜져 있으면 그 폭만큼 설정 방향에 공간을 확보해 패널도 화면 안에 둔다."""
        w, h = self.width(), self.height()
        # 패널(밀린할일 또는 타이머)이 켜져 있으면 설정 방향에 패널 폭만큼 여유 확보
        need_col = self._show_overdue or self._show_timer
        pw = (self._overdue_panel.width() + _PANEL_GAP) if need_col else 0
        side = self._settings.get(policies.KEY_OVERDUE_PANEL_SIDE, "right")
        right_reserve = pw if side == "right" else 0
        left_reserve = pw if side == "left" else 0

        # 위/아래용 가로 위치(캐릭터 중심 정렬 후 화면 안으로 clamp, 패널 공간 반영)
        hx = max(scr.left() + _MARGIN + left_reserve,
                 min(char.center().x() - w // 2, scr.right() - w - _MARGIN - right_reserve))
        # 좌/우용 세로 위치(캐릭터 중심 정렬 후 clamp)
        vy = max(scr.top() + _MARGIN, min(char.center().y() - h // 2, scr.bottom() - h - _MARGIN))

        above_y = char.top() - h - _GAP
        below_y = char.bottom() + _GAP
        right_x = char.right() + _GAP
        left_x = char.left() - w - _GAP

        if above_y >= scr.top() + _MARGIN:
            self._placed_side = "above"
            return QPoint(hx, above_y)
        if below_y + h <= scr.bottom() - _MARGIN:
            self._placed_side = "below"
            return QPoint(hx, below_y)
        if right_x + w + right_reserve <= scr.right() - _MARGIN:
            self._placed_side = "right"
            return QPoint(right_x, vy)
        if left_x - left_reserve >= scr.left() + _MARGIN:
            self._placed_side = "left"
            return QPoint(left_x, vy)
        # 최후: 화면 안으로 clamp (아주 작은 화면에서만 캐릭터와 겹칠 수 있음)
        self._placed_side = "above"
        y = max(scr.top() + _MARGIN, min(above_y, scr.bottom() - h - _MARGIN))
        return QPoint(hx, y)


def _sort_pixmap(size: int = 16, color: str = "#7F77DD") -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(max(1.4, size * 0.09))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    s = size
    for y, w in ((0.25, 0.56), (0.50, 0.40), (0.75, 0.24)):
        p.drawLine(int(s * 0.16), int(s * y), int(s * (0.16 + w)), int(s * y))
    p.drawLine(int(s * 0.78), int(s * 0.22), int(s * 0.78), int(s * 0.78))
    p.drawLine(int(s * 0.66), int(s * 0.64), int(s * 0.78), int(s * 0.78))
    p.drawLine(int(s * 0.90), int(s * 0.64), int(s * 0.78), int(s * 0.78))
    p.end()
    return pm
