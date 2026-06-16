"""ui/bubble/todo_item.py — 할일 한 줄 위젯.

상호작용
  - 체크박스 / 본문 클릭        → 완료 토글
  - hover 시 연필(편집)·휴지통(삭제) 아이콘 노출 (오른쪽 끝 고정, 휴지통이 맨 오른쪽)
  - 본문 누른 채 이동           → 드래그 (요일/날짜 간 이동, 캐릭터에 드롭=삭제)
  - 텍스트가 길면 말줄임표(…), 1.5초 이상 hover 시 전체 텍스트 툴팁
"""
from __future__ import annotations

from PyQt6.QtCore import QMimeData, QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QDrag,
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QToolTip,
    QWidget,
)

from domain.models import Todo

MIME_TODO = "application/x-character-todo"
_TOOLTIP_DELAY_MS = 500


class TodoItem(QWidget):
    request_remove = pyqtSignal(int)

    def __init__(self, todo: Todo, service, compact: bool = False, parent=None):
        super().__init__(parent)
        self.todo = todo
        self._service = service
        self._compact = compact
        self._press_pos: QPoint | None = None
        self._dragged = False
        self._editing = False

        self.setObjectName("todoRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 6, 4)
        lay.setSpacing(6)

        self.check = QCheckBox()
        self.check.setChecked(todo.completed)
        self.check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.check.stateChanged.connect(self._on_checkbox)
        lay.addWidget(self.check)

        self.label = QLabel()
        self.label.setObjectName("todoLabel")
        self.label.setProperty("state", "done" if todo.completed else "active")
        self.label.setWordWrap(False)
        self.label.setMinimumWidth(0)
        self._apply_strike()
        lay.addWidget(self.label, 1)

        self.editor = QLineEdit(todo.content)
        self.editor.setVisible(False)
        self.editor.returnPressed.connect(self._commit_edit)
        self.editor.editingFinished.connect(self._commit_edit)
        lay.addWidget(self.editor, 1)

        # hover 편집/삭제 (오른쪽 끝 고정: 연필 → 휴지통 순, 간격 좁게)
        self.pencil = QToolButton()
        self.pencil.setObjectName("pencilBtn")
        self.pencil.setIcon(QIcon(_pencil_pixmap()))
        self.pencil.setAutoRaise(True)
        self.pencil.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pencil.setFixedSize(20, 20)
        self.pencil.setVisible(False)
        self.pencil.clicked.connect(self._enter_edit)

        self.xbtn = QToolButton()
        self.xbtn.setObjectName("xBtn")
        self.xbtn.setIcon(QIcon(_trash_pixmap(16, "#D85A30")))
        self.xbtn.setAutoRaise(True)
        self.xbtn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.xbtn.setFixedSize(20, 20)
        self.xbtn.setVisible(False)
        self.xbtn.clicked.connect(lambda: self.request_remove.emit(self.todo.id))

        if not compact:
            lay.addSpacing(2)
            lay.addWidget(self.pencil)
            lay.addWidget(self.xbtn)

        self.setMouseTracking(True)
        self.setToolTip("")  # 기본 툴팁 끔 (직접 1.5초 후 표시)
        self._tip_timer = QTimer(self)
        self._tip_timer.setSingleShot(True)
        self._tip_timer.setInterval(_TOOLTIP_DELAY_MS)
        self._tip_timer.timeout.connect(self._show_tooltip)

    # ── 완료 토글 ───────────────────────────────────────────
    def _on_checkbox(self, _state: int) -> None:
        if self._editing:
            return
        self._service.toggle(self.todo.id)

    def _apply_strike(self) -> None:
        f: QFont = self.label.font()
        f.setStrikeOut(self.todo.completed)
        self.label.setFont(f)
        self._update_elision()

    # ── 말줄임 ──────────────────────────────────────────────
    def _update_elision(self) -> None:
        fm = QFontMetrics(self.label.font())
        w = max(10, self.label.width())
        self.label.setText(fm.elidedText(self.todo.content, Qt.TextElideMode.ElideRight, w))

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if not self._editing:
            self._update_elision()

    # ── 편집 ────────────────────────────────────────────────
    def _enter_edit(self) -> None:
        self._editing = True
        self.editor.setText(self.todo.content)
        self.label.setVisible(False)
        self.pencil.setVisible(False)
        self.xbtn.setVisible(False)
        self.editor.setVisible(True)
        self.editor.setFocus()
        self.editor.selectAll()

    def _commit_edit(self) -> None:
        if not self._editing:
            return
        self._editing = False
        text = self.editor.text().strip()
        self.editor.setVisible(False)
        self.label.setVisible(True)
        if text and text != self.todo.content:
            self._service.edit(self.todo.id, text)

    # ── hover: 아이콘 + 1.5초 툴팁 ──────────────────────────
    def enterEvent(self, _e) -> None:
        if not self._compact and not self._editing:
            self.pencil.setVisible(True)
            self.xbtn.setVisible(True)
        self._tip_timer.start()

    def leaveEvent(self, _e) -> None:
        self.pencil.setVisible(False)
        self.xbtn.setVisible(False)
        self._tip_timer.stop()
        QToolTip.hideText()

    def _show_tooltip(self) -> None:
        if self.underMouse() and not self._editing:
            QToolTip.showText(QCursor.pos(), self.todo.content, self)

    # ── 마우스: 클릭=토글 / 드래그=이동 ─────────────────────
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_pos = e.position().toPoint()
            self._dragged = False
            e.accept()        # 이 위젯이 마우스를 잡아야 move 이벤트가 들어와 드래그가 시작됨
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
        if self._press_pos is None or self._editing:
            return
        dist = (e.position().toPoint() - self._press_pos).manhattanLength()
        if dist < QApplication.startDragDistance():
            return
        self._start_drag()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if not self._dragged and not self._editing and self._press_pos is not None:
            self._service.toggle(self.todo.id)   # 본문 클릭 = 완료 토글
        self._press_pos = None

    def _start_drag(self) -> None:
        self._dragged = True
        self._tip_timer.stop()
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME_TODO, f"{self.todo.id}|{self.todo.due_date}".encode())
        drag.setMimeData(mime)
        # 마우스 아래에 끌고 있는 할일을 반투명 미리보기로 표시
        pm = self._drag_preview()
        drag.setPixmap(pm)
        lw = int(pm.width() / pm.devicePixelRatio())
        drag.setHotSpot(QPoint(lw // 2, -8))  # 커서 살짝 아래·가운데
        # 캐릭터(휴지통) 위 = Copy 액션 → 휴지통 커서. 날짜 칸 = Move → 기본 커서.
        drag.setDragCursor(_trash_pixmap(30, "#E5484D"), Qt.DropAction.CopyAction)
        drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction)
        self._press_pos = None
        # 삭제는 캐릭터에 드롭 시 캐릭터 쪽에서 처리.

    def _drag_preview(self) -> QPixmap:
        """드래그 미리보기: 연필/휴지통 숨기고 캡처 후 반투명 처리.
        너비는 이 항목의 텍스트 길이 기준으로 고정(같은 컬럼 최장 텍스트에 끌려가지 않도록)."""
        pencil_v, x_v = self.pencil.isVisible(), self.xbtn.isVisible()
        self.pencil.setVisible(False)
        self.xbtn.setVisible(False)
        src = self.grab()
        self.pencil.setVisible(pencil_v)
        self.xbtn.setVisible(x_v)

        dpr = src.devicePixelRatio()
        # 이 항목 텍스트 길이 기반 목표 너비(논리 픽셀)
        fm = self.label.fontMetrics()
        text_w = fm.horizontalAdvance(self.todo.content)
        check_w = self.check.sizeHint().width()
        # layout: left(8) + checkbox + spacing(6) + text + right(8) + 여유(8)
        target_w = min(8 + check_w + 6 + text_w + 16, int(src.width() / dpr))

        pm = QPixmap(int(target_w * dpr), src.height())
        pm.setDevicePixelRatio(dpr)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setOpacity(0.7)
        p.drawPixmap(0, 0, src)
        p.end()
        return pm


# ── 아이콘 그리기 (테마 무관, 직접 렌더) ────────────────────
def _trash_pixmap(size: int, color: str) -> QPixmap:
    """휴지통 아이콘 픽스맵."""
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(max(1.4, size * 0.07))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    s = size
    # 손잡이
    p.drawLine(int(s * 0.40), int(s * 0.22), int(s * 0.60), int(s * 0.22))
    # 뚜껑
    p.drawLine(int(s * 0.24), int(s * 0.32), int(s * 0.76), int(s * 0.32))
    # 통 몸체
    p.drawLine(int(s * 0.30), int(s * 0.32), int(s * 0.34), int(s * 0.80))
    p.drawLine(int(s * 0.70), int(s * 0.32), int(s * 0.66), int(s * 0.80))
    p.drawLine(int(s * 0.34), int(s * 0.80), int(s * 0.66), int(s * 0.80))
    # 세로 줄
    p.drawLine(int(s * 0.50), int(s * 0.40), int(s * 0.50), int(s * 0.72))
    p.end()
    return pm


def _pencil_pixmap() -> QPixmap:
    size = 16
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#8A8A86"))
    pen.setWidthF(1.4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    s = size
    p.drawLine(int(s * 0.30), int(s * 0.72), int(s * 0.72), int(s * 0.30))
    p.drawLine(int(s * 0.30), int(s * 0.72), int(s * 0.24), int(s * 0.78))
    p.drawLine(int(s * 0.66), int(s * 0.24), int(s * 0.78), int(s * 0.36))
    p.end()
    return pm
