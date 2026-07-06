from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractButton, QFrame, QVBoxLayout

from domain import policies
from domain.models import PRIORITY_HIGH, PRIORITY_LOW, PRIORITY_NONE, PRIORITY_NORMAL
from ui import theme

DOT_SIZE = 14

PRIORITY_CHOICES = (
    (PRIORITY_NONE, "없음"),
    (PRIORITY_LOW, "낮음"),
    (PRIORITY_NORMAL, "중간"),
    (PRIORITY_HIGH, "높음"),
)

PRIORITY_DOTS_LIGHT = {
    PRIORITY_NONE: ("#FFFFFF", "#C2BFB8"),
    PRIORITY_LOW: ("#4FA866", "#4FA866"),
    PRIORITY_NORMAL: ("#D8A530", "#D8A530"),
    PRIORITY_HIGH: ("#E5484D", "#E5484D"),
}
PRIORITY_DOTS_DARK = {
    PRIORITY_NONE: ("#000000", "#FFFFFF"),
    PRIORITY_LOW: ("#78C58B", "#78C58B"),
    PRIORITY_NORMAL: ("#E0B84D", "#E0B84D"),
    PRIORITY_HIGH: ("#FF7A7A", "#FF7A7A"),
}
DONE_CHECK = {
    "light": "#74736E",
    "dark": "#8A8992",
}


def theme_mode(settings_repo=None) -> str:
    if settings_repo is None:
        return "light"
    return theme.resolve(settings_repo.get(policies.KEY_THEME, "system"))


def priority_dot_colors(priority: int, mode: str) -> tuple[str, str]:
    colors = PRIORITY_DOTS_DARK if mode == "dark" else PRIORITY_DOTS_LIGHT
    return colors.get(priority, colors[PRIORITY_NONE])


class PriorityDotButton(QAbstractButton):
    def __init__(
        self,
        priority: int,
        settings_repo=None,
        size: int = DOT_SIZE,
        parent=None,
        visual_size: int | None = None,
        fixed_width: int | None = None,
        fixed_height: int | None = None,
    ):
        super().__init__(parent)
        self._priority = priority
        self._settings = settings_repo
        self._size = size
        self._visual_size = visual_size if visual_size is not None else min(size, DOT_SIZE)
        self._fixed_width = fixed_width if fixed_width is not None else size
        self._fixed_height = fixed_height if fixed_height is not None else size
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(self._fixed_width, self._fixed_height)
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet("background: transparent; border: none; padding: 0px;")

    def sizeHint(self) -> QSize:
        return QSize(self._fixed_width, self._fixed_height)

    def set_priority(self, priority: int) -> None:
        if self._priority == priority:
            return
        self._priority = priority
        self.update()

    def priority(self) -> int:
        return self._priority

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_dot(p, theme_mode(self._settings))
        p.end()

    def _paint_dot(self, painter: QPainter, mode: str) -> None:
        fill, border = priority_dot_colors(self._priority, mode)
        painter.setBrush(QColor(fill))
        pen = QPen(QColor(border))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        s = self._visual_size
        ribbon_w = s * 0.68
        notch_h = s * 0.28
        x = (self.width() - ribbon_w) / 2
        y = (self.height() - s) / 2
        left = x + 0.5
        right = x + ribbon_w - 0.5
        top = y + 0.5
        bottom = y + s - 0.5
        center = (left + right) / 2

        path = QPainterPath()
        path.moveTo(left, top)
        path.lineTo(right, top)
        path.lineTo(right, bottom)
        path.lineTo(center, bottom - notch_h)
        path.lineTo(left, bottom)
        path.closeSubpath()
        painter.drawPath(path)

    def _paint_done_check(self, painter: QPainter, mode: str) -> None:
        pen = QPen(QColor(DONE_CHECK[mode]))
        pen.setWidthF(max(1.7, self._visual_size * 0.14))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        s = self._visual_size
        x = (self.width() - s) / 2
        y = (self.height() - s) / 2
        path = QPainterPath()
        path.moveTo(x + s * 0.22, y + s * 0.54)
        path.lineTo(x + s * 0.42, y + s * 0.74)
        path.lineTo(x + s * 0.78, y + s * 0.28)
        painter.drawPath(path)


class PriorityToggleButton(PriorityDotButton):
    def __init__(
        self,
        priority: int,
        completed: bool,
        settings_repo=None,
        size: int = DOT_SIZE,
        parent=None,
        visual_size: int | None = None,
    ):
        super().__init__(priority, settings_repo, size, parent, visual_size)
        self._completed = completed

    def set_completed(self, completed: bool) -> None:
        if self._completed == completed:
            return
        self._completed = completed
        self.update()

    def paintEvent(self, _event) -> None:
        mode = theme_mode(self._settings)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self._completed:
            self._paint_dot(p, mode)
        else:
            self._paint_done_check(p, mode)
        p.end()


class PriorityPickerPopup(QFrame):
    selected = Signal(int)
    closed = Signal()

    def __init__(self, settings_repo=None, parent=None):
        super().__init__(
            parent,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self._settings = settings_repo
        self._anim: QPropertyAnimation | None = None
        self._close_geometry: QRect | None = None
        self._closing = False
        self._really_closing = False
        self.setObjectName("priorityPopup")
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("QFrame#priorityPopup { background: transparent; border: none; }")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        for priority in (PRIORITY_HIGH, PRIORITY_NORMAL, PRIORITY_LOW):
            btn = PriorityDotButton(priority, self._settings)
            btn.clicked.connect(lambda _checked=False, p=priority: self.selected.emit(p))
            lay.addWidget(btn)

    def show_above(self, anchor: QAbstractButton, gap: int = 8) -> None:
        self.adjustSize()
        pos = anchor.mapToGlobal(anchor.rect().topLeft())
        final = QRect(pos.x(), pos.y() - self.height() - gap, self.width(), self.height())
        start = QRect(pos.x(), pos.y(), self.width(), 1)
        self._close_geometry = start
        self.setGeometry(start)
        self.show()

        anim = QPropertyAnimation(self, b"geometry", self)
        anim.setDuration(150)
        anim.setStartValue(start)
        anim.setEndValue(final)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._anim = anim

    def close_animated(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.closed.emit()

        if self._anim is not None:
            self._anim.stop()

        end = self._close_geometry
        if end is None:
            end = QRect(self.x(), self.y() + self.height(), self.width(), 1)

        anim = QPropertyAnimation(self, b"geometry", self)
        anim.setDuration(120)
        anim.setStartValue(self.geometry())
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)

        def done() -> None:
            self._really_closing = True
            self.close()
            self.deleteLater()

        anim.finished.connect(done)
        anim.start()
        self._anim = anim

    def closeEvent(self, event) -> None:
        if self._really_closing:
            super().closeEvent(event)
            return
        event.ignore()
        self.close_animated()


def menu_qss(mode: str) -> str:
    if mode == "dark":
        bg = "#2A2A30"
        text = "#ECEAF0"
        hover = "#3C3489"
        border = "rgba(255,255,255,0.18)"
    else:
        bg = "#FFFFFF"
        text = "#2C2C2A"
        hover = "#EEEDFE"
        border = "rgba(0,0,0,0.16)"
    return f"""
QMenu {{
    background: {bg};
    color: {text};
    border: 1px solid {border};
    padding: 4px;
}}
QMenu::item {{
    padding: 4px 18px 4px 10px;
    background: transparent;
}}
QMenu::item:selected {{
    background: {hover};
}}
QMenu::separator {{
    height: 1px;
    background: {border};
    margin: 4px 6px;
}}
"""
