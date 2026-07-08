"""ui/bubble/day_view.py — 일간 뷰: 선택 날짜의 할일 리스트.

높이를 고정하고, 항목이 넘치면 세로 스크롤한다(드롭 정렬/이동 유지).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QMenu, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from ui.bubble.todo_clipboard import add_paste_action
from ui.bubble.todo_item import MIME_TODO, TodoItem
from ui.bubble.todo_sections import PinnedTodoSection, pin_separator
from ui.bubble.week_view import LIST_HEIGHT  # 일간 목록 높이를 주간과 동일하게 공유


class _DropList(QWidget):
    """실제 할일 행들을 담고 드롭(정렬/이동)을 처리하는 안쪽 위젯."""

    def __init__(self, iso: str, service, timer_service=None, settings_repo=None,
                 events=None, parent=None, priority_sort: bool = False,
                 show_empty: bool = True):
        super().__init__(parent)
        self.iso = iso
        self._service = service
        self._timer = timer_service
        self._settings = settings_repo
        self._events = events
        self._priority_sort = priority_sort
        self._show_empty = show_empty
        self.setAcceptDrops(not priority_sort)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(2, 2, 2, 2)
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

        todos = self._service.unpinned_for_date(
            self.iso,
            priority_sort=self._priority_sort,
        )
        if not todos:
            if not self._show_empty:
                return
            empty = QLabel("할 일이 없습니다")
            empty.setObjectName("emptyText")
            empty.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            empty.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._lay.addWidget(empty)
            return
        for t in todos:
            item = TodoItem(t, self._service, timer_service=self._timer,
                            settings_repo=self._settings, events=self._events,
                            priority_sort=self._priority_sort)
            item.request_remove.connect(self._service.remove)
            self._lay.addWidget(item)
            self._items.append(item)

    def dragEnterEvent(self, e) -> None:
        if self._priority_sort:
            return
        if e.mimeData().hasFormat(MIME_TODO):
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:
        if self._priority_sort:
            return
        if e.mimeData().hasFormat(MIME_TODO):
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        if self._priority_sort:
            e.ignore()
            return
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

    def contextMenuEvent(self, e) -> None:
        menu = QMenu(self)
        add_paste_action(menu, self._service, self._settings, self.iso)
        menu.exec(e.globalPos())
        e.accept()

    def _drop_index(self, y: int) -> int:
        for i, it in enumerate(self._items):
            mid = it.y() + it.height() / 2
            if y < mid:
                return i
        return len(self._items)

    def item_by_id(self, todo_id: int) -> TodoItem | None:
        for item in self._items:
            if item.todo.id == todo_id:
                return item
        return None


class DayView(QWidget):
    def __init__(self, iso: str, service, timer_service=None, settings_repo=None,
                 events=None, parent=None, focus_todo_id: int | None = None,
                 priority_sort: bool = False):
        super().__init__(parent)
        self._service = service
        self._timer = timer_service
        self._settings = settings_repo
        self._events = events
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        pinned = self._service.pinned_for_date(iso)
        if pinned:
            outer.addWidget(PinnedTodoSection(
                pinned,
                self._service,
                timer_service=self._timer,
                settings_repo=self._settings,
                events=self._events,
                margins=(4, 2, 4, 0),
            ))
            outer.addWidget(pin_separator())

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        # 고정 대신 최소 높이 + 세로 확장 → 말풍선을 키우면 목록 영역이 늘어난다
        self._scroll.setMinimumHeight(LIST_HEIGHT)
        self._scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._list = _DropList(
            iso, service, timer_service, settings_repo, events,
            priority_sort=priority_sort,
            show_empty=not pinned,
        )
        self._scroll.setWidget(self._list)
        outer.addWidget(self._scroll)

        if focus_todo_id is not None:
            QTimer.singleShot(0, lambda: self._focus_todo(focus_todo_id))

    def _focus_todo(self, todo_id: int) -> None:
        item = self._list.item_by_id(todo_id)
        if item is None:
            return
        self._scroll.ensureWidgetVisible(item, 0, 16)
        item.flash_focus()
