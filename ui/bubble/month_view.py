"""ui/bubble/month_view.py — 월간 뷰: 7x6 고정. 셀 클릭=날짜 선택, 드롭=그 날짜로 이동."""
from __future__ import annotations

from datetime import date, timedelta

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from domain import policies
from ui.bubble.todo_item import MIME_TODO

_WD = ["일", "월", "화", "수", "목", "금", "토"]


class MonthCell(QFrame):
    def __init__(self, d: date, anchor_month: int, selected: bool,
                 count: int, service, select_cb, parent=None):
        super().__init__(parent)
        self.iso = d.isoformat()
        self._service = service
        self._select_cb = select_cb
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumSize(40, 38)

        border = "2px solid #378ADD" if selected else "1px solid rgba(0,0,0,0.15)"
        dim = "" if d.month == anchor_month else "color: rgba(0,0,0,0.35);"
        self.setStyleSheet(f"MonthCell {{ border: {border}; border-radius: 4px; }}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(3, 2, 3, 2)
        lay.setSpacing(0)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        # 1일이거나 그리드 시작이면 '월'도 함께 표기
        text = f"{d.month}/{d.day}" if d.day == 1 else str(d.day)
        head = QLabel(text)
        f = head.font()
        f.setPointSize(max(7, f.pointSize() - 2))
        head.setFont(f)
        head.setStyleSheet(dim)
        lay.addWidget(head)

        if count > 0:
            badge = QLabel(f"\u2022 {count}")
            bf = badge.font()
            bf.setPointSize(max(7, bf.pointSize() - 2))
            badge.setFont(bf)
            badge.setStyleSheet("color: #378ADD;")
            lay.addWidget(badge)

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


class MonthView(QWidget):
    def __init__(self, selected_iso: str, service, select_cb, parent=None):
        super().__init__(parent)
        anchor = date.fromisoformat(selected_iso)
        grid_start, grid_end = policies.month_grid_range(anchor)
        counts = service.counts_in_range(grid_start.isoformat(), grid_end.isoformat())

        lay = QGridLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)

        for c in range(7):
            wd = QLabel(_WD[c])
            wd.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            f = wd.font()
            f.setPointSize(max(7, f.pointSize() - 2))
            wd.setFont(f)
            lay.addWidget(wd, 0, c)

        for i in range(42):  # 7 x 6 고정
            d = grid_start + timedelta(days=i)
            iso = d.isoformat()
            cell = MonthCell(
                d, anchor.month, iso == selected_iso,
                counts.get(iso, 0), service, select_cb,
            )
            lay.addWidget(cell, 1 + i // 7, i % 7)
