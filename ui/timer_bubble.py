"""ui/timer_bubble.py — 캐릭터 옆에 떠 있는 작은 타이머 풍선.

말풍선이 닫혀 있고 타이머가 도는 동안 캐릭터 위(공간 없으면 아래)에 표시된다.
  - 남은 시간(mm:ss) + 할일명
  - 클릭하면 말풍선을 연다(clicked 시그널)
  - 캐릭터 드래그 시 함께 따라온다(place_for 재호출)
  - 트레이 최소화 중에도 단독으로 남을 수 있다(소유는 컨트롤러/캐릭터가 관리)
독립 top-level 위젯이라 캐릭터가 hide 돼도 살아남는다.
외형(둥근 몸체+꼬리·배치·테마 골격)은 FloatingBubble 베이스가 담당한다.
"""
from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout

from domain import policies
from ui import theme
from ui.floating_bubble import W, FloatingBubble


def _fmt(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class TimerBubble(FloatingBubble):
    clicked = pyqtSignal()

    def __init__(self, events, settings_repo, parent=None):
        super().__init__(settings_repo, parent)
        self._events = events
        # 드래그 허용 여부: 캐릭터가 내려간(트레이 최소화) 단독 표시일 때만 True.
        # 부착 모드(캐릭터+풍선)에선 위치는 캐릭터를 따라가고, 클릭으로 투두를 연다.
        self._draggable = False
        self._press_global: QPoint | None = None
        self._press_frame: QPoint | None = None
        self._moved = False
        self._update_hint()

        v = QVBoxLayout(self._root)
        v.setContentsMargins(10, 6, 10, 6)
        v.setSpacing(1)

        self._time = QLabel("00:00")
        self._time.setObjectName("tbTime")
        self._time.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        f = self._time.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 3)
        self._time.setFont(f)
        v.addWidget(self._time)

        self._name = QLabel("")
        self._name.setObjectName("tbName")
        self._name.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        v.addWidget(self._name)

        self._events.timer_tick.connect(self._on_tick)
        self._events.theme_changed.connect(self.apply_theme)
        self.apply_theme()

    # ── 스타일 ──────────────────────────────────────────────
    def apply_theme(self) -> None:
        c = theme.palette(self._settings.get(policies.KEY_THEME, "system"))
        self.setStyleSheet(
            self._chrome_theme()
            + f"#bubbleRootMini QLabel#tbTime {{ color: {c['accent_text']}; }}"
            + f"#bubbleRootMini QLabel#tbName {{ color: {c['sub']}; }}"
        )
        self.update()

    # ── 갱신 ────────────────────────────────────────────────
    def set_content(self, content: str, remaining: int) -> None:
        fm = QFontMetrics(self._name.font())
        self._name.setText(fm.elidedText(content, Qt.TextElideMode.ElideRight, W - 28))
        self._time.setText(_fmt(remaining))

    def _on_tick(self, _todo_id: int, remaining: int) -> None:
        if self.isVisible():
            self._time.setText(_fmt(remaining))

    # ── 드래그 가능 여부 ────────────────────────────────────
    def set_draggable(self, on: bool) -> None:
        """단독 표시(트레이 최소화)면 True → 드래그로 이동.
        부착 모드면 False → 이동 없이 클릭으로 투두를 연다."""
        if on != self._draggable:
            self._draggable = on
            self._update_hint()

    def _update_hint(self) -> None:
        self.setToolTip("드래그하여 이동" if self._draggable else "클릭하면 할 일 열기")

    # ── 마우스 ──────────────────────────────────────────────
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_global = e.globalPosition().toPoint()
            self._press_frame = self.frameGeometry().topLeft()
            self._moved = False

    def mouseMoveEvent(self, e) -> None:
        if self._press_global is None or not self._draggable:
            return
        delta = e.globalPosition().toPoint() - self._press_global
        if delta.manhattanLength() >= QApplication.startDragDistance():
            self._moved = True
        self.move(self._press_frame + delta)

    def mouseReleaseEvent(self, e) -> None:
        was_click = (
            e.button() == Qt.MouseButton.LeftButton
            and self._press_global is not None
            and not self._moved
        )
        self._press_global = None
        # 부착 모드: 단일 클릭으로 투두 열기. 단독(드래그) 모드: 클릭은 무동작.
        if was_click and not self._draggable:
            self.clicked.emit()

    def mouseDoubleClickEvent(self, _e) -> None:
        # 단독(드래그) 모드에서도 더블클릭이면 투두를 연다.
        if self._draggable:
            self.clicked.emit()
