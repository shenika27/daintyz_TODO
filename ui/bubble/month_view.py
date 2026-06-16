"""ui/bubble/month_view.py — 월간 뷰: 7x6 정사각형 그리드.

각 날짜 셀(정사각형) = 날짜 숫자 + 할일 개수 뱃지.
  - 단일 클릭  → 날짜 선택
  - 더블 클릭  → 그 날짜의 일간 보기로 전환
  - 항목 드롭  → 그 날짜로 이동
"""
from __future__ import annotations

from datetime import date, timedelta

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from domain import policies
from ui.bubble.todo_item import MIME_TODO

_WD = ["일", "월", "화", "수", "목", "금", "토"]
CELL = 58  # 정사각형 셀 한 변(px)


def _count_text(label: str, n: int) -> str:
    """3자리 이하면 '라벨 N', 4자리 이상이면 'N'만(셀이 좁아 텍스트 생략)."""
    return f"{label} {n}" if n < 1000 else str(n)


class MonthCell(QFrame):
    def __init__(self, d: date, anchor_month: int, selected: bool,
                 total: int, done: int, service, select_cb, open_day_cb, parent=None):
        super().__init__(parent)
        self.iso = d.isoformat()
        self._service = service
        self._select_cb = select_cb
        self._open_day_cb = open_day_cb
        self.setObjectName("monthCell")
        self.setProperty("selected", "true" if selected else "false")
        self.setFixedSize(CELL, CELL)
        self.setAcceptDrops(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 3, 4, 3)
        lay.setSpacing(2)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        text = f"{d.month}/{d.day}" if d.day == 1 else str(d.day)
        head = QLabel(text)
        head.setObjectName("dimDay" if d.month != anchor_month else "todoLabel")
        f = head.font()
        f.setPointSize(max(7, f.pointSize() - 2))
        head.setFont(f)
        lay.addWidget(head)

        # 둥근 직사각형 뱃지 안에 '할일 N'(옅은 빨강) / '완료 N'(연두) 표기
        if total > 0:
            badge = QWidget()
            badge.setObjectName("statBadge")
            badge.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
            blay = QVBoxLayout(badge)
            blay.setContentsMargins(5, 2, 5, 2)
            blay.setSpacing(0)

            l_total = QLabel(_count_text("할일", total))
            l_total.setObjectName("badgeTotal")
            l_total.setAlignment(Qt.AlignmentFlag.AlignCenter)
            blay.addWidget(l_total)

            if done > 0:
                l_done = QLabel(_count_text("완료", done))
                l_done.setObjectName("badgeDone")
                l_done.setAlignment(Qt.AlignmentFlag.AlignCenter)
                blay.addWidget(l_done)

            lay.addWidget(badge, alignment=Qt.AlignmentFlag.AlignHCenter)

    def mousePressEvent(self, _e) -> None:
        self._select_cb(self.iso)

    def mouseDoubleClickEvent(self, _e) -> None:
        self._open_day_cb(self.iso)

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
    def __init__(self, selected_iso: str, service, select_cb, open_day_cb, parent=None):
        super().__init__(parent)
        anchor = date.fromisoformat(selected_iso)
        grid_start, grid_end = policies.month_grid_range(anchor)

        # 날짜별 (전체, 달성) 개수
        service.ensure_range(grid_start.isoformat(), grid_end.isoformat())
        counts: dict[str, tuple[int, int]] = {}
        cur = grid_start
        while cur <= grid_end:
            iso = cur.isoformat()
            todos = service.list_for_date(iso)
            done = sum(1 for t in todos if t.completed)
            counts[iso] = (len(todos), done)
            cur += timedelta(days=1)

        lay = QGridLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(3)

        for c in range(7):
            wd = QLabel(_WD[c])
            wd.setObjectName("wdHead")
            wd.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            f = wd.font()
            f.setPointSize(max(7, f.pointSize() - 2))
            wd.setFont(f)
            lay.addWidget(wd, 0, c)

        for i in range(42):
            d = grid_start + timedelta(days=i)
            iso = d.isoformat()
            total, done = counts.get(iso, (0, 0))
            cell = MonthCell(
                d, anchor.month, iso == selected_iso,
                total, done, service, select_cb, open_day_cb,
            )
            lay.addWidget(cell, 1 + i // 7, i % 7, Qt.AlignmentFlag.AlignCenter)
