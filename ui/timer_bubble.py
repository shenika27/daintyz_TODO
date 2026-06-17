"""ui/timer_bubble.py — 캐릭터 옆에 떠 있는 작은 타이머 풍선.

말풍선이 닫혀 있고 타이머가 도는 동안 캐릭터 위(공간 없으면 아래)에 표시된다.
  - 남은 시간(mm:ss) + 할일명
  - 클릭하면 말풍선을 연다(clicked 시그널)
  - 캐릭터 드래그 시 함께 따라온다(place_for 재호출)
  - 트레이 최소화 중에도 단독으로 남을 수 있다(소유는 컨트롤러/캐릭터가 관리)
독립 top-level 위젯이라 캐릭터가 hide 돼도 살아남는다.
"""
from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPolygon
from PyQt6.QtWidgets import QApplication, QFrame, QLabel, QVBoxLayout, QWidget

from domain import policies
from ui import theme

_W = 150          # 풍선 폭(px)
_TAIL = 8         # 꼬리 높이
_PAD = 8          # 그림자/여백
_GAP = 8          # 캐릭터와의 간격
_MARGIN = 6       # 화면 가장자리 여백


def _fmt(seconds: int) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class TimerBubble(QWidget):
    clicked = pyqtSignal()

    def __init__(self, events, settings_repo, parent=None):
        super().__init__(parent)
        self._events = events
        self._settings = settings_repo
        self._tail_down = True   # True=꼬리 아래(풍선이 캐릭터 위)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(_W)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # 드래그 허용 여부: 캐릭터가 내려간(트레이 최소화) 단독 표시일 때만 True.
        # 부착 모드(캐릭터+풍선)에선 위치는 캐릭터를 따라가고, 클릭으로 투두를 연다.
        self._draggable = False
        self._press_global: QPoint | None = None
        self._press_frame: QPoint | None = None
        self._moved = False
        self._update_hint()

        self._root = QFrame(self)
        self._root.setObjectName("timerBubbleRoot")
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(_PAD, _PAD, _PAD, _PAD + _TAIL)
        self._outer.addWidget(self._root)

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
        mode = self._settings.get(policies.KEY_THEME, "system")
        c = theme.palette(mode)
        self._bg = QColor(c["bg"])
        # border_strong 은 rgba 문자열이라 QColor 파싱이 안 되므로 모드별 고정 알파 사용
        dark = theme.resolve(mode) == "dark"
        self._border = QColor(255, 255, 255, 46) if dark else QColor(0, 0, 0, 40)
        self.setStyleSheet(
            f"""
            #timerBubbleRoot {{ background: transparent; }}
            #timerBubbleRoot QLabel {{ background: transparent; }}
            #timerBubbleRoot QLabel#tbTime {{ color: {c['accent_text']}; }}
            #timerBubbleRoot QLabel#tbName {{ color: {c['sub']}; }}
            """
        )
        self.update()

    # ── 갱신 ────────────────────────────────────────────────
    def set_content(self, content: str, remaining: int) -> None:
        from PyQt6.QtGui import QFontMetrics

        fm = QFontMetrics(self._name.font())
        self._name.setText(fm.elidedText(content, Qt.TextElideMode.ElideRight, _W - 28))
        self._time.setText(_fmt(remaining))

    def _on_tick(self, _todo_id: int, remaining: int) -> None:
        if self.isVisible():
            self._time.setText(_fmt(remaining))

    # ── 배치 ────────────────────────────────────────────────
    def place_for(self, char_geom: QRect, screen_geom: QRect) -> None:
        """캐릭터 위에 두되 공간 없으면 아래로(꼬리 방향도 반전)."""
        self.adjustSize()
        h = self.height()
        w = self.width()
        above_y = char_geom.top() - h - _GAP + _TAIL  # 꼬리만큼 가깝게
        below_y = char_geom.bottom() + _GAP - _TAIL
        if above_y >= screen_geom.top() + _MARGIN:
            self._set_tail(True)
            y = above_y
        else:
            self._set_tail(False)
            y = below_y
        x = char_geom.center().x() - w // 2
        x = max(screen_geom.left() + _MARGIN, min(x, screen_geom.right() - w - _MARGIN))
        self.move(x, y)

    def _set_tail(self, down: bool) -> None:
        if down == self._tail_down:
            return
        self._tail_down = down
        if down:
            self._outer.setContentsMargins(_PAD, _PAD, _PAD, _PAD + _TAIL)
        else:
            self._outer.setContentsMargins(_PAD, _PAD + _TAIL, _PAD, _PAD)
        self.adjustSize()
        self.update()

    # ── 그리기: 둥근 풍선 몸체 + 꼬리 ───────────────────────
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._root.geometry()
        p.setBrush(QBrush(self._bg))
        p.setPen(QPen(self._border, 1))
        p.drawRoundedRect(r, 12, 12)

        cx = r.center().x()
        if self._tail_down:
            ty = r.bottom()
            tail = QPolygon([
                QPoint(cx - _TAIL, ty - 1),
                QPoint(cx + _TAIL, ty - 1),
                QPoint(cx, ty + _TAIL),
            ])
        else:
            ty = r.top()
            tail = QPolygon([
                QPoint(cx - _TAIL, ty + 1),
                QPoint(cx + _TAIL, ty + 1),
                QPoint(cx, ty - _TAIL),
            ])
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(tail)

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
