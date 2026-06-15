"""ui/bubble/day_view.py — 일간 뷰: 선택 날짜의 할일 리스트.

높이를 고정하고, 항목이 넘치면 세로 스크롤한다(드롭 정렬/이동 유지).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from ui.bubble.todo_item import MIME_TODO, TodoItem
from ui.bubble.week_view import LIST_HEIGHT  # 일간 목록 높이를 주간과 동일하게 공유


class _DropList(QWidget):
    """실제 할일 행들을 담고 드롭(정렬/이동)을 처리하는 안쪽 위젯."""

    def __init__(self, iso: str, service, parent=None):
        super().__init__(parent)
        self.iso = iso
        self._service = service
        self.setAcceptDrops(True)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(4, 2, 4, 2)
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
            empty = QLabel("할 일이 없습니다")
            empty.setObjectName("emptyText")
            empty.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            self._lay.addWidget(empty)
            return
        for t in todos:
            item = TodoItem(t, self._service)
            item.request_remove.connect(self._service.remove)
            self._lay.addWidget(item)
            self._items.append(item)

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


class DayView(QWidget):
    def __init__(self, iso: str, service, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFixedHeight(LIST_HEIGHT)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setWidget(_DropList(iso, service))
        outer.addWidget(self._scroll)
