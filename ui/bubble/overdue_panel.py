"""ui/bubble/overdue_panel.py — '밀린 할일' 독립 패널(말풍선 우측에 떠 있음).

말풍선과 분리된 별도 창이다. 오늘 이전에 미완료가 있는 날짜를 'M/D(요일): n개'로 나열하고,
행을 클릭하면 그 날짜 일간 보기로 이동한다. 우측 상단 X 로 닫는다.
표시 여부는 캐릭터 우클릭 메뉴('밀린할일 표시')로 토글한다(설정에 저장).
위치/높이는 말풍선이 잡아준다(BubbleWidget._position_overdue_panel).
"""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from domain import policies
from ui.bubble.panel_base import PANEL_WIDTH, _PanelBase

__all__ = ["PANEL_WIDTH", "OverduePanel"]


class _OverdueRow(QLabel):
    def __init__(
        self,
        iso: str,
        count: int,
        open_day_cb,
        complete_cb,
        move_today_cb,
        parent=None,
    ):
        d = date.fromisoformat(iso)
        super().__init__(f"{policies.fmt_md(d)}: {count}개", parent)
        self.iso = iso
        self._open_day_cb = open_day_cb
        self._complete_cb = complete_cb
        self._move_today_cb = move_today_cb
        self.setObjectName("overdueRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._show_action_menu(e.globalPosition().toPoint())
            return
        super().mousePressEvent(e)

    def contextMenuEvent(self, e) -> None:
        self._show_action_menu(e.globalPos())

    def _show_action_menu(self, global_pos) -> None:
        menu = QMenu(self)
        open_day = menu.addAction("날짜 보기")
        complete = menu.addAction("완료 처리")
        move_today = menu.addAction("오늘로 옮기기")
        chosen = menu.exec(global_pos)
        if chosen == open_day:
            self._open_day_cb(self.iso)
        elif chosen == complete:
            self._complete_cb(self.iso)
        elif chosen == move_today:
            self._move_today_cb(self.iso)


class OverduePanel(_PanelBase):
    def __init__(self, service, events, settings_repo, open_day_cb, parent=None):
        super().__init__(settings_repo, events, "밀린 할일", parent)
        self._service = service
        self._open_day_cb = open_day_cb

        self._add_header_button("✕", "닫기", self._close_panel)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._vbox.addWidget(self._scroll, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        self._complete_all_btn = QPushButton("모두 완료")
        self._complete_all_btn.setToolTip("오늘 이전 미완료 할일을 모두 완료 처리합니다.")
        self._complete_all_btn.clicked.connect(self._complete_all)
        btn_row.addWidget(self._complete_all_btn)
        self._move_all_btn = QPushButton("모두 오늘로")
        self._move_all_btn.setToolTip("반복할일을 제외한 밀린 일반 할일을 오늘로 옮깁니다.")
        self._move_all_btn.clicked.connect(self._move_all_to_today)
        btn_row.addWidget(self._move_all_btn)
        self._vbox.addLayout(btn_row)

        self._events.todos_changed.connect(self._on_data)
        self.apply_theme()
        self.reload()

    def _on_data(self, _iso: str) -> None:
        if self.isVisible():
            self.reload()

    def _close_panel(self) -> None:
        """✕ 닫기: 표시 끄기 알림만 보낸다. 설정 저장·패널 숨김은 BubbleWidget 이 처리(#1)."""
        self._events.overdue_panel_changed.emit(False)

    def reload(self) -> None:
        inner = QWidget(self._scroll)  # 부모 지정: 잠깐 최상위 창이 되는 깜빡임 방지
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 2, 2, 2)
        lay.setSpacing(3)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        today_iso = date.today().isoformat()
        rows = self._service.overdue_counts(today_iso)
        movable_count = self._service.movable_overdue_count(today_iso)
        self._complete_all_btn.setEnabled(bool(rows))
        self._move_all_btn.setEnabled(movable_count > 0)
        if not rows:
            empty = QLabel("없음")
            empty.setObjectName("emptyText")
            empty.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lay.addWidget(empty)
        else:
            for iso, cnt in rows:
                lay.addWidget(
                    _OverdueRow(
                        iso,
                        cnt,
                        self._open_day_cb,
                        self._complete_date,
                        self._move_date_to_today,
                    )
                )
        self._scroll.setWidget(inner)

    def _complete_date(self, iso: str) -> None:
        self._service.complete_incomplete_for_date(iso)

    def _move_date_to_today(self, iso: str) -> None:
        self._service.move_incomplete_regular_to_today(iso)

    def _complete_all(self) -> None:
        self._service.complete_all_overdue()

    def _move_all_to_today(self) -> None:
        self._service.move_all_overdue_regular_to_today()
