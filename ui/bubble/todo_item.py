"""ui/bubble/todo_item.py — 할일 한 줄 위젯.

상호작용
  - 왼쪽 체크박스 클릭        → 완료 토글 / 취소선
  - hover 시 우측 연필 클릭   → 인라인 편집 (Enter 확정 / Esc·포커스아웃 해제)
  - 본문 누른 채 이동         → 드래그 (정렬/날짜이동/외부드롭 삭제)
"""
from __future__ import annotations

from PyQt6.QtCore import QMimeData, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QDrag, QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QWidget,
)

from domain.models import Todo

MIME_TODO = "application/x-character-todo"


class TodoItem(QWidget):
    # 외부 드롭 등으로 삭제 요청 시 (todo_id)
    request_remove = pyqtSignal(int)

    def __init__(self, todo: Todo, service, compact: bool = False, parent=None):
        super().__init__(parent)
        self.todo = todo
        self._service = service
        self._compact = compact
        self._press_pos: QPoint | None = None
        self._editing = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 1, 2, 1)
        lay.setSpacing(4)

        self.check = QCheckBox()
        self.check.setChecked(todo.completed)
        self.check.stateChanged.connect(self._on_toggle)
        lay.addWidget(self.check)

        self.label = QLabel(todo.content)
        self.label.setWordWrap(False)
        self._apply_strike()
        lay.addWidget(self.label, 1)

        self.editor = QLineEdit(todo.content)
        self.editor.setVisible(False)
        self.editor.returnPressed.connect(self._commit_edit)
        self.editor.editingFinished.connect(self._commit_edit)
        lay.addWidget(self.editor, 1)

        self.pencil = QToolButton()
        self.pencil.setText("\u270e")  # ✎
        self.pencil.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pencil.setAutoRaise(True)
        self.pencil.setVisible(False)
        self.pencil.clicked.connect(self._enter_edit)
        if not compact:
            lay.addWidget(self.pencil)

        self.setMouseTracking(True)

    # ── 완료 토글 ───────────────────────────────────────────
    def _on_toggle(self, _state: int) -> None:
        if self._editing:
            return
        self._service.toggle(self.todo.id)

    def _apply_strike(self) -> None:
        f: QFont = self.label.font()
        f.setStrikeOut(self.todo.completed)
        self.label.setFont(f)
        self.label.setEnabled(not self.todo.completed)

    # ── 편집 ────────────────────────────────────────────────
    def _enter_edit(self) -> None:
        self._editing = True
        self.editor.setText(self.todo.content)
        self.label.setVisible(False)
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
        # 실제 갱신은 todos_changed 시그널로 다시 그려진다

    # ── hover 연필 ──────────────────────────────────────────
    def enterEvent(self, _e) -> None:
        if not self._compact and not self._editing:
            self.pencil.setVisible(True)

    def leaveEvent(self, _e) -> None:
        self.pencil.setVisible(False)

    # ── 드래그 ──────────────────────────────────────────────
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_pos = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
        if self._press_pos is None or self._editing:
            return
        from PyQt6.QtWidgets import QApplication

        dist = (e.position().toPoint() - self._press_pos).manhattanLength()
        if dist < QApplication.startDragDistance():
            return
        self._start_drag()

    def _start_drag(self) -> None:
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME_TODO, f"{self.todo.id}|{self.todo.due_date}".encode())
        drag.setMimeData(mime)
        result = drag.exec(Qt.DropAction.MoveAction)
        self._press_pos = None
        # 어떤 위젯도 받지 않았다면(앱 외부 드롭) 삭제
        if result == Qt.DropAction.IgnoreAction:
            self.request_remove.emit(self.todo.id)
