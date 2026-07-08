"""ui/bubble/overdue_panel.py — '밀린 할일' 독립 패널(말풍선 우측에 떠 있음).

말풍선과 분리된 별도 창이다. 오늘 이전에 미완료가 있는 날짜를 'M/D(요일): n개'로 나열하고,
행을 클릭하면 그 날짜 일간 보기로 이동한다. 우측 상단 X 로 닫는다.
표시 여부는 캐릭터 우클릭 메뉴('밀린할일 표시')로 토글한다(설정에 저장).
위치/높이는 말풍선이 잡아준다(BubbleWidget._position_overdue_panel).
"""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from domain import policies
from ui.bubble.panel_base import PANEL_WIDTH, _PanelBase

__all__ = ["PANEL_WIDTH", "OverduePanel"]

_MODE_OVERDUE = "overdue"
_MODE_COMPLETED = "completed"
_COMPACT_PANEL_HEIGHT = 250


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


class _CompletedRow(QLabel):
    def __init__(
        self,
        todo,
        open_day_cb,
        duplicate_today_cb,
        parent=None,
    ):
        super().__init__("", parent)
        self.todo = todo
        self._content = todo.content
        self._open_day_cb = open_day_cb
        self._duplicate_today_cb = duplicate_today_cb
        self.setObjectName("overdueRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(todo.content)
        self.setWordWrap(False)
        self._sync_text()

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._open_day_cb(self.todo.due_date, self.todo.id)
            return
        super().mousePressEvent(e)

    def contextMenuEvent(self, e) -> None:
        menu = QMenu(self)
        move = menu.addAction("이동하기")
        duplicate = menu.addAction("복제하기")
        chosen = menu.exec(e.globalPos())
        if chosen == move:
            self._open_day_cb(self.todo.due_date, self.todo.id)
        elif chosen == duplicate:
            self._duplicate_today_cb(self.todo.id)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._sync_text()

    def _sync_text(self) -> None:
        fm = QFontMetrics(self.font())
        self.setText(fm.elidedText(self._content, Qt.TextElideMode.ElideRight, max(20, self.width())))


class _CompletedDateRow(QLabel):
    def __init__(
        self,
        iso: str,
        count: int,
        open_day_cb,
        duplicate_date_cb,
        parent=None,
    ):
        d = date.fromisoformat(iso)
        super().__init__(f"{policies.fmt_md(d)}: {count}개", parent)
        self.iso = iso
        self._open_day_cb = open_day_cb
        self._duplicate_date_cb = duplicate_date_cb
        self.setObjectName("overdueRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._open_day_cb(self.iso)
            return
        super().mousePressEvent(e)

    def contextMenuEvent(self, e) -> None:
        menu = QMenu(self)
        move = menu.addAction("이동하기")
        duplicate = menu.addAction("복제하기")
        chosen = menu.exec(e.globalPos())
        if chosen == move:
            self._open_day_cb(self.iso)
        elif chosen == duplicate:
            self._duplicate_date_cb(self.iso)


class OverduePanel(_PanelBase):
    def __init__(self, service, events, settings_repo, open_day_cb, parent=None):
        super().__init__(settings_repo, events, "밀린 할일", parent)
        self._service = service
        self._open_day_cb = open_day_cb
        self._mode = _MODE_OVERDUE
        self._compact_actions = False

        self._switch_btn = self._add_header_button("", "완료한 일 보기", self._toggle_mode)
        self._switch_btn.setIcon(QIcon(_switch_pixmap(16, "#6F6A64")))
        self._switch_btn.setIconSize(QSize(16, 16))
        self._add_header_button("✕", "닫기", self._close_panel)

        self._completed_search = QLineEdit()
        self._completed_search.setPlaceholderText("완료한 일 검색")
        self._completed_search.setClearButtonEnabled(True)
        self._completed_search.setObjectName("completedSearch")
        self._completed_search.textChanged.connect(self.reload)
        self._vbox.addWidget(self._completed_search)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._vbox.addWidget(self._scroll, 1)

        self._actions = QWidget()
        btn_row = QVBoxLayout(self._actions)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(4)
        self._action_lay = btn_row
        self._complete_all_btn = QPushButton("모두 완료")
        self._complete_all_btn.setToolTip("오늘 이전 미완료 할일을 모두 완료 처리합니다.")
        self._complete_all_btn.setMinimumHeight(28)
        self._complete_all_btn.clicked.connect(self._complete_all)
        btn_row.addWidget(self._complete_all_btn)
        self._move_all_btn = QPushButton("모두 오늘로")
        self._move_all_btn.setToolTip("반복할일을 제외한 밀린 일반 할일을 오늘로 옮깁니다.")
        self._move_all_btn.setMinimumHeight(28)
        self._move_all_btn.clicked.connect(self._move_all_to_today)
        btn_row.addWidget(self._move_all_btn)
        self._vbox.addWidget(self._actions)

        self._events.todos_changed.connect(self._on_data)
        self.apply_theme()
        self.reload()

    def _on_data(self, _iso: str) -> None:
        if self.isVisible():
            self.reload()

    def _close_panel(self) -> None:
        """✕ 닫기: 표시 끄기 알림만 보낸다. 설정 저장·패널 숨김은 BubbleWidget 이 처리(#1)."""
        self._events.overdue_panel_changed.emit(False)

    def _toggle_mode(self) -> None:
        self._mode = _MODE_COMPLETED if self._mode == _MODE_OVERDUE else _MODE_OVERDUE
        self.reload()

    def reload(self) -> None:
        scroll_value = self._scroll.verticalScrollBar().value()
        inner = QWidget(self._scroll)  # 부모 지정: 잠깐 최상위 창이 되는 깜빡임 방지
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(0, 2, 2, 2)
        lay.setSpacing(3)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        today_iso = date.today().isoformat()
        query = ""
        self._completed_search.setVisible(self._mode == _MODE_COMPLETED)
        if self._mode == _MODE_OVERDUE:
            rows = self._service.overdue_counts(today_iso)
            total = sum(cnt for _iso, cnt in rows)
            movable_count = self._service.movable_overdue_count(today_iso)
            self._set_title(f"밀린 할일({total})")
            self._switch_btn.setToolTip("완료한 일 보기")
            self._actions.setVisible(True)
            self._complete_all_btn.setEnabled(bool(rows))
            self._move_all_btn.setEnabled(movable_count > 0)
        else:
            completed_view = self._completed_view_mode()
            query = self._completed_search.text().strip()
            rows = (
                self._service.completed_items(query)
                if completed_view == "detail"
                else self._service.completed_counts(query)
            )
            total = (
                len(rows)
                if completed_view == "detail"
                else sum(cnt for _iso, cnt in rows)
            )
            self._set_title(f"완료한 일({total})")
            self._switch_btn.setToolTip("밀린 할일 보기")
            self._actions.setVisible(False)

        if not rows:
            empty_text = "검색 결과 없음" if self._mode == _MODE_COMPLETED and query else "없음"
            empty = QLabel(empty_text)
            empty.setObjectName("emptyText")
            empty.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lay.addWidget(empty)
        else:
            if self._mode == _MODE_OVERDUE:
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
            else:
                if self._completed_view_mode() == "detail":
                    for todo in rows:
                        lay.addWidget(
                            _CompletedRow(
                                todo,
                                self._open_day_cb,
                                self._duplicate_completed_to_today,
                            )
                        )
                else:
                    for iso, cnt in rows:
                        lay.addWidget(
                            _CompletedDateRow(
                                iso,
                                cnt,
                                self._open_day_cb,
                                self._duplicate_completed_date_to_today,
                            )
                        )
        self._scroll.setWidget(inner)
        QTimer.singleShot(0, lambda v=scroll_value: self._scroll.verticalScrollBar().setValue(v))
        self._sync_action_density()

    def _completed_view_mode(self) -> str:
        mode = self._settings.get(policies.KEY_COMPLETED_VIEW_MODE, "summary") or "summary"
        return "detail" if mode == "detail" else "summary"

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._sync_action_density()

    def _sync_action_density(self) -> None:
        compact = self._mode == _MODE_OVERDUE and self.height() < _COMPACT_PANEL_HEIGHT
        if compact == self._compact_actions:
            return
        self._compact_actions = compact
        if compact:
            self._vbox.setSpacing(4)
            self._action_lay.setSpacing(2)
            min_h = 24
        else:
            self._vbox.setSpacing(6)
            self._action_lay.setSpacing(4)
            min_h = 28
        self._complete_all_btn.setMinimumHeight(min_h)
        self._move_all_btn.setMinimumHeight(min_h)

    def _complete_date(self, iso: str) -> None:
        self._service.complete_incomplete_for_date(iso)

    def _move_date_to_today(self, iso: str) -> None:
        self._service.move_incomplete_regular_to_today(iso)

    def _duplicate_completed_to_today(self, todo_id: int) -> None:
        self._service.duplicate_completed_to_today(todo_id)

    def _duplicate_completed_date_to_today(self, iso: str) -> None:
        self._service.duplicate_completed_date_to_today(iso)

    def _complete_all(self) -> None:
        self._service.complete_all_overdue()

    def _move_all_to_today(self) -> None:
        self._service.move_all_overdue_regular_to_today()


def _switch_pixmap(size: int, color: str) -> QPixmap:
    """90도 회전한 전환 느낌의 작은 아이콘."""
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(max(1.5, size * 0.11))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)

    s = size
    p.drawLine(int(s * 0.25), int(s * 0.30), int(s * 0.76), int(s * 0.30))
    p.drawLine(int(s * 0.76), int(s * 0.30), int(s * 0.76), int(s * 0.56))
    p.drawLine(int(s * 0.76), int(s * 0.56), int(s * 0.62), int(s * 0.44))
    p.drawLine(int(s * 0.76), int(s * 0.56), int(s * 0.90), int(s * 0.44))

    p.drawLine(int(s * 0.75), int(s * 0.70), int(s * 0.24), int(s * 0.70))
    p.drawLine(int(s * 0.24), int(s * 0.70), int(s * 0.24), int(s * 0.44))
    p.drawLine(int(s * 0.24), int(s * 0.44), int(s * 0.10), int(s * 0.56))
    p.drawLine(int(s * 0.24), int(s * 0.44), int(s * 0.38), int(s * 0.56))
    p.end()
    return pm
