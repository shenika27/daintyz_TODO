"""ui/bubble/week_view.py — 주간 뷰: 일~토 7열. 셀 클릭=날짜 선택, 드롭=그 날짜로 이동."""
from __future__ import annotations

from datetime import date, timedelta

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from domain import policies
from ui.bubble.todo_item import MIME_TODO, TodoItem

_WD = ["일", "월", "화", "수", "목", "금", "토"]


class DayColumn(QFrame):
    def __init__(self, iso: str, label: str, selected: bool, service, select_cb, parent=None):
        super().__init__(parent)
        self.iso = iso
        self._service = service
        self._select_cb = select_cb
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        if selected:
            self.setStyleSheet("DayColumn { border: 2px solid #378ADD; border-radius: 6px; }")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(1)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        head = QLabel(label)
        head.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        f = head.font()
        f.setPointSize(max(7, f.pointSize() - 1))
        head.setFont(f)
        lay.addWidget(head)

        for t in service.list_for_date(iso):
            item = TodoItem(t, service, compact=True)
            item.request_remove.connect(service.remove)
            lay.addWidget(item)

    def mousePressEvent(self, _e) -> None:
        self._select_cb(self.iso)

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasFormat(MIME_TODO):
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:
        if e.mimeData().hasFormat(MIME_TODO):
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        raw = bytes(e.mimeData().data(MIME_TODO)).decode()
        tid_s, _src = raw.split("|", 1)
        self._service.move(int(tid_s), self.iso)
        e.setDropAction(Qt.DropAction.MoveAction)
        e.accept()


class WeekView(QWidget):
    def __init__(self, selected_iso: str, service, select_cb, parent=None):
        super().__init__(parent)
        anchor = date.fromisoformat(selected_iso)
        sunday, _sat = policies.week_range(anchor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(3)
        for i in range(7):
            d = sunday + timedelta(days=i)
            iso = d.isoformat()
            label = f"{_WD[i]} {d.day}"
            col = DayColumn(iso, label, iso == selected_iso, service, select_cb)
            lay.addWidget(col, 1)
