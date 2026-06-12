"""ui/bubble/day_view.py — 일간 뷰: 선택 날짜의 할일 리스트 (드롭으로 정렬/이동)."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ui.bubble.todo_item import MIME_TODO, TodoItem


class DayView(QWidget):
    def __init__(self, iso: str, service, parent=None):
        super().__init__(parent)
        self.iso = iso
        self._service = service
        self.setAcceptDrops(True)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(6, 4, 6, 4)
        self._lay.setSpacing(2)
        self._lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._items: list[TodoItem] = []
        self._reload()

    def _reload(self) -> None:
        while self._lay.count():
            w = self._lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._items.clear()

        todos = self._service.list_for_date(self.iso)
        if not todos:
            self._lay.addWidget(QLabel("할 일이 없습니다"))
            return
        for t in todos:
            item = TodoItem(t, self._service)
            item.request_remove.connect(self._service.remove)
            self._lay.addWidget(item)
            self._items.append(item)

    # ── 드롭 ────────────────────────────────────────────────
    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasFormat(MIME_TODO):
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:
        if e.mimeData().hasFormat(MIME_TODO):
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        raw = bytes(e.mimeData().data(MIME_TODO)).decode()
        tid_s, src_iso = raw.split("|", 1)
        tid = int(tid_s)
        index = self._drop_index(int(e.position().y()))

        if src_iso == self.iso:
            ids = [it.todo.id for it in self._items if it.todo.id != tid]
            ids.insert(min(index, len(ids)), tid)
            self._service.reorder(self.iso, ids)
        else:
            self._service.move(tid, self.iso, index)
        e.setDropAction(Qt.DropAction.MoveAction)
        e.accept()

    def _drop_index(self, y: int) -> int:
        for i, it in enumerate(self._items):
            mid = it.y() + it.height() / 2
            if y < mid:
                return i
        return len(self._items)
