"""ui/bubble/month_view.py — 월간 뷰: 7x6 정사각형 그리드.

각 날짜 셀(정사각형) = 날짜 숫자 + 할일 개수 뱃지.
  - 단일 클릭  → 날짜 선택
  - 더블 클릭  → 그 날짜의 일간 보기로 전환
  - 항목 드롭  → 그 날짜로 이동
"""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from domain import policies
from ui.bubble.todo_item import MIME_TODO

CELL = 58  # 월간 셀 기본 한 변(px)
MIN_CELL = 34
COLS = 7
ROWS = 6


def _count_text(label: str, n: int) -> str:
    """3자리 이하면 '라벨 N', 4자리 이상이면 'N'만(셀이 좁아 텍스트 생략)."""
    return f"{label} {n}" if n < 1000 else str(n)


def _stat_badge(obj_name: str, text: str) -> QLabel:
    """배경색으로 구분되는 둥근 배지 라벨(스타일은 theme.qss)."""
    lbl = QLabel(text)
    lbl.setObjectName(obj_name)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return lbl


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
        self.setMinimumSize(MIN_CELL, MIN_CELL)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAcceptDrops(True)

        lay = QVBoxLayout(self)
        self._layout = lay
        lay.setContentsMargins(4, 3, 4, 3)
        lay.setSpacing(2)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        text = f"{d.month}/{d.day}" if d.day == 1 else str(d.day)
        head = QLabel(text)
        head.setObjectName("dimDay" if d.month != anchor_month else "todoLabel")
        f = head.font()
        f.setPointSize(max(7, f.pointSize() - 2))
        head.setFont(f)
        self._head = head
        self._badge_labels: list[QLabel] = []
        lay.addWidget(head)

        # '할일' 배지 = 아직 안 한(밀린) 할일 = 전체 − 완료, '완료' 배지 = 완료 수
        remaining = total - done
        if total > 0:
            badges = QVBoxLayout()
            badges.setContentsMargins(0, 0, 0, 0)
            badges.setSpacing(2)
            if remaining > 0:
                badge = _stat_badge("badgeTotal", _count_text("할일", remaining))
                badges.addWidget(badge)
                self._badge_labels.append(badge)
            if done > 0:
                badge = _stat_badge("badgeDone", _count_text("완료", done))
                badges.addWidget(badge)
                self._badge_labels.append(badge)
            lay.addLayout(badges)
        self._sync_metrics()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._sync_metrics()

    def _sync_metrics(self) -> None:
        w = max(MIN_CELL, self.width())
        h = max(MIN_CELL, self.height())
        mx = max(4, min(10, w // 18))
        my = max(3, min(8, h // 22))
        gap = max(2, min(6, h // 28))
        self._layout.setContentsMargins(mx, my, mx, my)
        self._layout.setSpacing(gap)

        head_font = self._head.font()
        head_font.setPointSize(max(7, min(13, h // 8)))
        self._head.setFont(head_font)

        badge_h = max(13, min(26, h // 5))
        badge_px = max(9, min(15, h // 8))
        badge_pad_x = max(4, min(10, w // 22))
        badge_radius = max(4, min(8, badge_h // 3))
        for badge in self._badge_labels:
            badge.setMinimumWidth(24)
            badge.setFixedHeight(badge_h)
            badge.setStyleSheet(
                f"font-size: {badge_px}px; "
                f"padding: 0px {badge_pad_x}px; "
                f"border-radius: {badge_radius}px;"
            )

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

        # 날짜별 (전체, 달성) 개수. 반복 할일은 미래를 미리 만들지 않으므로(당일 생성)
        # 여기서 범위 구체화는 하지 않는다 — 이미 생성된 회차만 집계된다.
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
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        for c in range(COLS):
            lay.setColumnMinimumWidth(c, MIN_CELL)
            lay.setColumnStretch(c, 1)
            wd = QLabel(policies.WEEKDAYS_KR[c])
            wd.setObjectName("wdHead")
            wd.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            f = wd.font()
            f.setPointSize(max(7, f.pointSize() - 2))
            wd.setFont(f)
            lay.addWidget(wd, 0, c)

        lay.setRowStretch(0, 0)
        for r in range(ROWS):
            lay.setRowMinimumHeight(r + 1, MIN_CELL)
            lay.setRowStretch(r + 1, 1)

        for i in range(COLS * ROWS):
            d = grid_start + timedelta(days=i)
            iso = d.isoformat()
            total, done = counts.get(iso, (0, 0))
            cell = MonthCell(
                d, anchor.month, iso == selected_iso,
                total, done, service, select_cb, open_day_cb,
            )
            lay.addWidget(cell, 1 + i // COLS, i % COLS)

    def sizeHint(self) -> QSize:
        return QSize(CELL * COLS + 32, CELL * ROWS + 36)

    def minimumSizeHint(self) -> QSize:
        return QSize(MIN_CELL * COLS + 32, MIN_CELL * ROWS + 36)
