"""ui/bubble/week_view.py — 주간 뷰: 일~토 7열.

각 요일 컬럼 = 헤더(요일/날짜) + 고정 높이 스크롤 목록.
드롭(다른 요일로 이동)은 컬럼 프레임(DayColumn)이 직접 처리한다.
  → 스크롤 영역이 드롭을 가로채 이동이 안 되던 문제 해결:
    안쪽 위젯들은 acceptDrops 를 끄고, 드래그 이벤트가 컬럼까지 전파되게 둔다.
컬럼/빈영역 클릭 = 날짜 선택.
"""
from __future__ import annotations

from datetime import date, timedelta

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from domain import policies
from ui.bubble.todo_item import MIME_TODO, TodoItem

_WD = ["일", "월", "화", "수", "목", "금", "토"]
LIST_HEIGHT = 240  # 요일별 목록 고정 높이(px)


class _ColList(QWidget):
    """요일 컬럼 안쪽: 그 날짜 할일 목록 + 빈영역 클릭=선택. (드롭은 상위가 처리)"""

    def __init__(self, iso: str, service, select_cb, parent=None):
        super().__init__(parent)
        self.iso = iso
        self._select_cb = select_cb

        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        for t in service.list_for_date(iso):
            item = TodoItem(t, service, compact=True)
            item.request_remove.connect(service.remove)
            lay.addWidget(item)

    def mousePressEvent(self, _e) -> None:
        self._select_cb(self.iso)


class DayColumn(QFrame):
    def __init__(self, iso: str, label: str, selected: bool, service, select_cb, parent=None):
        super().__init__(parent)
        self.iso = iso
        self._service = service
        self._select_cb = select_cb
        self.setObjectName("dayCol")
        self.setProperty("selected", "true" if selected else "false")
        self.setAcceptDrops(True)  # 드롭은 컬럼이 직접 받는다

        lay = QVBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        head = QLabel(label)
        head.setObjectName("wdHead")
        head.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        f = head.font()
        f.setPointSize(max(8, f.pointSize()))
        head.setFont(f)
        lay.addWidget(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(LIST_HEIGHT)
        scroll.setAcceptDrops(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        inner = _ColList(iso, service, select_cb)
        scroll.setWidget(inner)
        lay.addWidget(scroll)

    def mousePressEvent(self, _e) -> None:
        self._select_cb(self.iso)

    # ── 드롭(다른 요일로 이동) ──────────────────────────────
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
        lay.setSpacing(4)
        for i in range(7):
            d = sunday + timedelta(days=i)
            iso = d.isoformat()
            label = f"{_WD[i]} {d.day}"
            col = DayColumn(iso, label, iso == selected_iso, service, select_cb)
            lay.addWidget(col, 1)
