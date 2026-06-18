"""ui/bubble/timer_panel.py — '타이머' 독립 패널(밀린 할일 패널과 같은 컬럼에 떠 있음).

말풍선과 분리된 별도 창이다. 현재 실행 중인 할일 타이머를 정사각형 셀로 보여준다.
  상단: 타이머 아이콘(크게) / 중앙: 남은 시간(mm:ss) / 하단: 할일명
셀을 클릭하면 타이머를 정지/재개한다(완전 해제는 패널 우상단 ✕).
표시 여부·위치·높이는 말풍선이 잡아준다(BubbleWidget._position_left_column).
"""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
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
from ui.bubble.overdue_panel import PANEL_WIDTH
from ui.bubble.todo_item import _clock_pixmap
from ui.qt_helpers import make_overlay_window

CELL_HEIGHT = 108  # 정사각형 셀: 패널 폭 140 − 외부/루트 여백(8+8)*2 = 셀 너비 108
BLOCK_BASE = 172    # 패널 고정 높이(평상시): 헤더 + 정사각형 셀
BLOCK_PAUSED = 210  # 할일 타이머 정지 시: + 셀↔버튼 공백 + 완료/초기화 버튼 자리
_PAUSE_COLOR = "#7F77DD"  # 정지(⏸) 강조색(보라) — 호버 안내용
_PAUSED_RED = "#D85A30"   # 정지 '상태' 표시용 붉은 ‖ (#3)
_RESUME_COLOR = "#2E9E5B"  # 재개(▶) 강조색(초록)


def _pause_pixmap(size: int, color: str) -> QPixmap:
    """정지용 ⏸ 아이콘(세로 막대 2개)."""
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    s = size
    bar_w = s * 0.18
    p.drawRoundedRect(int(s * 0.30 - bar_w / 2), int(s * 0.26),
                      int(bar_w), int(s * 0.48), 2, 2)
    p.drawRoundedRect(int(s * 0.70 - bar_w / 2), int(s * 0.26),
                      int(bar_w), int(s * 0.48), 2, 2)
    p.end()
    return pm


def _play_pixmap(size: int, color: str) -> QPixmap:
    """재개용 ▶ 아이콘(삼각형)."""
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QPolygonF

    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    s = size
    pts = [QPointF(s * 0.32, s * 0.26), QPointF(s * 0.32, s * 0.74),
           QPointF(s * 0.74, s * 0.50)]
    p.drawPolygon(QPolygonF(pts))
    p.end()
    return pm


class _TimerCell(QFrame):
    """타이머 셀: 평소엔 남은 시간을 보여주고, 마우스오버 시 정지/재개 안내로
    내용을 바꾼다(위젯 재생성 없이 라벨만 교체 → 깜빡임 없음).
    클릭하면 정지/재개 토글(완전 해제는 패널 우상단 ✕)."""

    def __init__(self, on_toggle, parent=None):
        super().__init__(parent)
        self._on_toggle = on_toggle
        self._content = ""
        self._hover = False
        self._paused = False
        self.setObjectName("timerCell")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("클릭하면 정지/재개")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 8, 6, 8)
        lay.setSpacing(2)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._clock_pm = _clock_pixmap(40, "#7F77DD")
        self._pause_pm = _pause_pixmap(40, _PAUSE_COLOR)
        self._pause_red_pm = _pause_pixmap(40, _PAUSED_RED)
        self._play_pm = _play_pixmap(40, _RESUME_COLOR)
        self._icon = QLabel()
        self._icon.setPixmap(self._clock_pm)
        self._icon.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self._icon)

        self._time = QLabel("00:00")
        self._time.setObjectName("timerTime")
        self._time.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        f = self._time.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 3)
        self._time.setFont(f)
        lay.addWidget(self._time)

        self._name = QLabel("")
        self._name.setObjectName("timerName")
        self._name.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._name.setWordWrap(False)
        lay.addWidget(self._name)

    def set_time(self, seconds: int) -> None:
        self._time.setText(policies.fmt_hms(seconds))

    def set_name(self, content: str) -> None:
        self._content = content
        if not self._hover:
            self._show_normal_name()

    def set_paused(self, paused: bool) -> None:
        """정지 상태 반영: 정지 중엔 ▶ 아이콘으로 '재개 가능'을 표시."""
        self._paused = paused
        self._refresh_idle_view() if not self._hover else self._refresh_hover_view()

    def _show_normal_name(self) -> None:
        fm = QFontMetrics(self._name.font())
        self._name.setText(
            fm.elidedText(self._content, Qt.TextElideMode.ElideRight, PANEL_WIDTH - 28)
        )

    def _refresh_idle_view(self) -> None:
        """호버 아님: 실행중=시계, 정지중=‖(붉은) 정지 아이콘 + 멈춘 시간 유지(#3)."""
        self._icon.setPixmap(self._pause_red_pm if self._paused else self._clock_pm)
        self._time.setVisible(True)
        self._name.setStyleSheet("")
        self._show_normal_name()

    def _refresh_hover_view(self) -> None:
        """호버: 실행중=⏸'정지', 정지중=▶'재개'."""
        if self._paused:
            self._icon.setPixmap(self._play_pm)
            self._name.setText("재개")
            self._name.setStyleSheet(f"color: {_RESUME_COLOR};")
        else:
            self._icon.setPixmap(self._pause_pm)
            self._name.setText("정지")
            self._name.setStyleSheet(f"color: {_PAUSE_COLOR};")
        self._time.setVisible(False)

    # ── 마우스오버: 정지/재개 안내로 전환 ──────────────────────
    def enterEvent(self, _e) -> None:
        self._hover = True
        self._refresh_hover_view()

    def leaveEvent(self, _e) -> None:
        self._hover = False
        self._refresh_idle_view()

    def mousePressEvent(self, _e) -> None:
        self._on_toggle()


class _IdleControl(QFrame):
    """할일 없이 타이머를 직접 설정·시작하는 idle 컨트롤(▶ + 시간 + −/+).
    타이머가 비활성일 때 셀 대신 표시된다.

    증감 규칙(#1): 1분 이상에서는 설정된 간격(KEY_TIMER_STEP)으로, 1분 미만에서는
    설정과 무관하게 5초 단위로 −/+ 한다(최소 5초). 큰 간격으로 1분 아래로 내려갈 땐
    먼저 1분에 멈춘 뒤 5초 단위로 넘어간다."""

    _MIN = 5             # 최소 5초
    _MAX = 99 * 60 + 59  # 최대 99:59
    _SUB_MINUTE_STEP = 5  # 1분 미만 고정 간격

    def __init__(self, on_start, settings_repo=None, parent=None):
        super().__init__(parent)
        self._on_start = on_start
        self._settings = settings_repo
        self._secs = policies.DEFAULT_STANDALONE_SECONDS
        self.setObjectName("timerCell")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(2)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._play = QToolButton()
        self._play.setObjectName("timerPlay")
        self._play.setIcon(QIcon(_play_pixmap(30, _RESUME_COLOR)))
        self._play.setIconSize(QSize(30, 30))
        self._play.setAutoRaise(True)
        self._play.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play.setToolTip("타이머 시작")
        self._play.clicked.connect(lambda: self._on_start(self._secs))
        lay.addWidget(self._play, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._time = QLabel(policies.fmt_hms(self._secs))
        self._time.setObjectName("timerTime")
        self._time.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        f = self._time.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 3)
        self._time.setFont(f)
        lay.addWidget(self._time)

        # −/+ : 셀 폭을 반씩 채우는 가로로 긴 직사각형(클릭범위 넓게)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self._make_adjust_btn("−", "시간 감소", going_down=True), 1)
        row.addWidget(self._make_adjust_btn("+", "시간 증가", going_down=False), 1)
        lay.addLayout(row)

    def _make_adjust_btn(self, text: str, tip: str, going_down: bool) -> QToolButton:
        b = QToolButton()
        b.setText(text)
        b.setObjectName("timerAdjBtn")
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFixedHeight(28)
        b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        b.clicked.connect(lambda: self._adjust(going_down))
        return b

    def _configured_step(self) -> int:
        """설정된 증감 간격(초). 1분 이상에서만 사용(미만은 5초 고정)."""
        if self._settings is None:
            return policies.DEFAULT_TIMER_STEP
        return self._settings.get_int(
            policies.KEY_TIMER_STEP, policies.DEFAULT_TIMER_STEP
        ) or policies.DEFAULT_TIMER_STEP

    def _adjust(self, going_down: bool) -> None:
        if going_down:
            step = self._SUB_MINUTE_STEP if self._secs <= 60 else self._configured_step()
            new = self._secs - step
            if self._secs > 60 and new < 60:
                new = 60  # 큰 간격으로 내려갈 땐 1분에 한 번 멈춤(이후 5초 단위)
        else:
            step = self._SUB_MINUTE_STEP if self._secs < 60 else self._configured_step()
            new = self._secs + step
        self._secs = max(self._MIN, min(self._MAX, new))
        self._time.setText(policies.fmt_hms(self._secs))

    def set_seconds(self, secs: int) -> None:
        """idle 진입 시 기본값(직전 설정 시간)으로 맞춘다."""
        self._secs = max(self._MIN, min(self._MAX, int(secs)))
        self._time.setText(policies.fmt_hms(self._secs))


class TimerPanel(QWidget):
    def __init__(self, service, events, settings_repo, timer_service, parent=None):
        super().__init__(parent)
        self._service = service
        self._events = events
        self._settings = settings_repo
        self._timer = timer_service

        make_overlay_window(self)
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
        title = QLabel("타이머")
        title.setObjectName("overdueTitle")
        f = title.font()
        f.setBold(True)
        title.setFont(f)
        head.addWidget(title, 1)

        # 초기화(↺): 진행 중 일반 타이머를 직전 설정 시간으로(#9). 일반 타이머일 때만 노출.
        self._reset_btn = QToolButton()
        self._reset_btn.setText("↺")
        self._reset_btn.setToolTip("직전 설정 시간으로 초기화")
        self._reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset_btn.clicked.connect(self._timer.reset_standalone)
        self._reset_btn.setVisible(False)
        head.addWidget(self._reset_btn)

        close = QToolButton()
        close.setText("✕")
        close.setToolTip("닫기")
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self._close_panel)
        head.addWidget(close)
        vbox.addLayout(head)

        # 활성 타이머용 셀 + 비활성 시 직접 설정 idle 컨트롤(둘 중 하나만 표시)
        self._cell = _TimerCell(self._timer.toggle_pause)
        self._cell.setFixedHeight(CELL_HEIGHT)
        vbox.addWidget(self._cell)
        self._idle = _IdleControl(self._start_standalone, self._settings)
        self._idle.setFixedHeight(CELL_HEIGHT)
        vbox.addWidget(self._idle)

        # 할일 타이머 정지(일시정지) 중 하단 버튼 2개: 완료 / 초기화(#8)
        self._paused_actions = QWidget()
        pa = QHBoxLayout(self._paused_actions)
        pa.setContentsMargins(0, 8, 0, 0)  # 셀(보라색)과 버튼 사이 공백(#2)
        pa.setSpacing(6)
        self._done_btn = QToolButton()
        self._done_btn.setText("완료")
        self._done_btn.setObjectName("timerActionBtn")
        self._done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._done_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._done_btn.clicked.connect(self._complete_current)
        self._reset_todo_btn = QToolButton()
        self._reset_todo_btn.setText("초기화")
        self._reset_todo_btn.setObjectName("timerActionBtn")
        self._reset_todo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset_todo_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._reset_todo_btn.clicked.connect(self._timer.reset_to_total)
        pa.addWidget(self._done_btn)
        pa.addWidget(self._reset_todo_btn)
        self._paused_actions.setVisible(False)
        vbox.addWidget(self._paused_actions)

        self._events.timer_tick.connect(self._on_tick)
        self._events.timer_started.connect(lambda _id: self._sync_view())
        self._events.timer_stopped.connect(self._sync_view)
        self._events.timer_finished.connect(lambda _id: self._sync_view())
        self._events.timer_paused.connect(lambda _id: self._sync_view())
        self._events.timer_resumed.connect(lambda _id: self._sync_view())
        self._events.theme_changed.connect(self.apply_theme)
        self.apply_theme()
        self._sync_view()

    def apply_theme(self) -> None:
        mode = self._settings.get(policies.KEY_THEME, "system")
        self.setStyleSheet(theme.qss(mode))

    def block_height(self) -> int:
        """현재 상태에 맞는 패널 고정 높이(평상시 축소, 할일 타이머 정지 시 버튼 자리 확보)."""
        snap = self._timer.snapshot()
        if snap is not None and snap.paused and not self._timer.is_standalone():
            return BLOCK_PAUSED
        return BLOCK_BASE

    def _start_standalone(self, seconds: int) -> None:
        self._timer.start_standalone(seconds)

    def _close_panel(self) -> None:
        """✕ 닫기: 진행 중 타이머는 그대로 두고(#10) 패널 상시 표시만 끈다.
        설정 저장·패널 숨김은 BubbleWidget 이 처리(#1). 타이머가 도는 중이면
        말풍선을 내릴 때 캐릭터 옆 타이머 풍선으로 계속 보인다."""
        self._events.timer_panel_changed.emit(False)

    def _complete_current(self) -> None:
        """완료(#8): 할일 타이머 대상 할일을 완료 처리하고 타이머 해제."""
        tid = self._timer.active_todo_id
        self._timer.cancel()
        if tid is not None and self._service is not None:
            self._service.toggle(tid)

    def reload(self) -> None:
        self._sync_view()

    def _sync_view(self) -> None:
        """타이머 활성=셀, 비활성=idle 컨트롤. (둘 중 하나만 보이게)"""
        snap = self._timer.snapshot()
        if snap is not None:
            self._idle.setVisible(False)
            self._cell.setVisible(True)
            self._cell.set_name(snap.content)
            self._cell.set_time(snap.remaining_seconds)
            self._cell.set_paused(snap.paused)
            standalone = self._timer.is_standalone()
            self._reset_btn.setVisible(standalone)
            # 할일 타이머가 '정지' 중일 때만 완료/초기화 버튼 노출(#8)
            self._paused_actions.setVisible(snap.paused and not standalone)
        else:
            self._cell.setVisible(False)
            self._reset_btn.setVisible(False)
            self._paused_actions.setVisible(False)
            # idle 로 처음 전환될 때만 직전 설정 시간으로 채운다(사용자 ±조정 보존)
            if not self._idle.isVisible():
                self._idle.set_seconds(self._timer.last_standalone_seconds)
            self._idle.setVisible(True)

    def _on_tick(self, _id: int, remaining: int) -> None:
        if self.isVisible():
            self._cell.set_time(remaining)
