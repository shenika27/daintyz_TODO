"""ui/floating_bubble.py — 캐릭터 옆 작은 풍선(타이머/할일개수)의 공통 외형.

frameless tool 윈도우 · 둥근 몸체 + 꼬리 · 위(공간 없으면 아래) 자동 배치를 제공한다.
서브클래스는 self._root(QFrame) 안에 콘텐츠를 채우고, _chrome_theme() 으로 받은 공통
QSS 에 자기 라벨 색만 덧붙이면 된다(TimerBubble/TodoCountBubble 공유).

몸체와 꼬리는 QPainterPath.united() 로 하나로 합쳐 한 번에 칠하고 외곽선을 긋는다.
  → 꼬리만 테두리가 빠지던 문제 해결(예전엔 몸체=테두리, 꼬리=NoPen 으로 따로 그림).
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from domain import policies
from ui import theme
from ui.qt_helpers import make_overlay_window

W = 150          # 풍선 폭(px)
TAIL = 8         # 꼬리 높이
PAD = 8          # 그림자/여백
GAP = 8          # 캐릭터와의 간격
MARGIN = 6       # 화면 가장자리 여백


class FloatingBubble(QWidget):
    """캐릭터 위(공간 없으면 아래)에 뜨는 둥근 말풍선 베이스."""

    def __init__(self, settings_repo, parent=None):
        super().__init__(parent)
        self._settings = settings_repo
        self._tail_down = True   # True=꼬리 아래(풍선이 캐릭터 위)

        make_overlay_window(self)
        self.setFixedWidth(W)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._root = QFrame(self)
        self._root.setObjectName("bubbleRootMini")
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(PAD, PAD, PAD, PAD + TAIL)
        self._outer.addWidget(self._root)

    # ── 테마: _bg/_border 채우고 공통 QSS 반환(서브클래스가 라벨색 덧붙임) ──
    def _chrome_theme(self) -> str:
        mode = self._settings.get(policies.KEY_THEME, "system")
        # border_strong 은 rgba 문자열이라 QColor 파싱이 안 되므로 모드별 고정 알파 사용
        dark = theme.resolve(mode) == "dark"
        self._bg = QColor(theme.palette(mode)["bg"])
        self._border = QColor(255, 255, 255, 46) if dark else QColor(0, 0, 0, 40)
        return (
            "#bubbleRootMini { background: transparent; }"
            "#bubbleRootMini QLabel { background: transparent; }"
        )

    # ── 배치 ────────────────────────────────────────────────
    def place_for(self, char_geom: QRect, screen_geom: QRect) -> None:
        """캐릭터 위에 두되 공간 없으면 아래로(꼬리 방향도 반전)."""
        self.adjustSize()
        h = self.height()
        w = self.width()
        above_y = char_geom.top() - h - GAP + TAIL  # 꼬리만큼 가깝게
        below_y = char_geom.bottom() + GAP - TAIL
        if above_y >= screen_geom.top() + MARGIN:
            self._set_tail(True)
            y = above_y
        else:
            self._set_tail(False)
            y = below_y
        x = char_geom.center().x() - w // 2
        x = max(screen_geom.left() + MARGIN, min(x, screen_geom.right() - w - MARGIN))
        self.move(x, y)

    def _set_tail(self, down: bool) -> None:
        if down == self._tail_down:
            return
        self._tail_down = down
        if down:
            self._outer.setContentsMargins(PAD, PAD, PAD, PAD + TAIL)
        else:
            self._outer.setContentsMargins(PAD, PAD + TAIL, PAD, PAD)
        self.adjustSize()
        self.update()

    # ── 그리기: 둥근 몸체 + 꼬리를 한 경로로 합쳐 외곽선을 끊김 없이 ──
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._root.geometry()
        cx = r.center().x()

        if self._tail_down:
            ty = r.bottom()
            tail = QPolygonF([
                QPointF(cx - TAIL, ty - 1),   # 몸체와 1px 겹쳐 union 시 이음매 제거
                QPointF(cx + TAIL, ty - 1),
                QPointF(cx, ty + TAIL),
            ])
        else:
            ty = r.top()
            tail = QPolygonF([
                QPointF(cx - TAIL, ty + 1),
                QPointF(cx + TAIL, ty + 1),
                QPointF(cx, ty - TAIL),
            ])

        body = QPainterPath()
        body.addRoundedRect(QRectF(r), 12, 12)
        tail_path = QPainterPath()
        tail_path.addPolygon(tail)
        tail_path.closeSubpath()
        shape = body.united(tail_path)

        p.setBrush(QBrush(self._bg))
        p.setPen(QPen(self._border, 1))
        p.drawPath(shape)
