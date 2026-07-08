"""ui/bubble/todo_item.py — 할일 한 줄 위젯.

상호작용
  - 체크박스 / 본문 클릭        → 완료 토글
  - hover 시 연필(편집)·휴지통(삭제) 아이콘 노출 (오른쪽 끝 고정, 휴지통이 맨 오른쪽)
  - 본문 누른 채 이동           → 드래그 (요일/날짜 간 이동, 캐릭터에 드롭=삭제)
  - 텍스트가 길면 말줄임표(…), 1.5초 이상 hover 시 전체 텍스트 툴팁
"""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import (
    QEasingCurve,
    QMimeData,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QCursor,
    QDrag,
    QFont,
    QFontMetrics,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QSizePolicy,
    QToolButton,
    QToolTip,
    QWidget,
)

from domain import policies
from domain.models import (
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NONE,
    PRIORITY_NORMAL,
    Todo,
)
from ui.bubble.priority_ui import PRIORITY_CHOICES, PriorityDotButton, menu_qss, theme_mode
from ui.bubble.todo_clipboard import copy_todo_to_clipboard
from ui.qt_helpers import show_korean_text_menu

MIME_TODO = "application/x-character-todo"
_TOOLTIP_DELAY_MS = 500
_ACTION_WIDTH = 46
_PRIORITY_CYCLE = (PRIORITY_NONE, PRIORITY_LOW, PRIORITY_NORMAL, PRIORITY_HIGH)
_PRIORITY_MENU_CHOICES = tuple(reversed(PRIORITY_CHOICES))


def _next_priority(priority: int) -> int:
    try:
        idx = _PRIORITY_CYCLE.index(priority)
    except ValueError:
        return PRIORITY_NONE
    return _PRIORITY_CYCLE[(idx + 1) % len(_PRIORITY_CYCLE)]


class _TodoEditor(QPlainTextEdit):
    submitted = Signal()

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("todoEditor")
        self.setPlainText(text)
        self.setTabChangesFocus(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.textChanged.connect(self._sync_height)
        self._sync_height()

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(e)
            else:
                self.submitted.emit()
            return
        super().keyPressEvent(e)

    def focusOutEvent(self, e) -> None:
        # 우클릭 메뉴 팝업이 포커스를 가져갈 때는 편집을 닫지 않는다.
        if e.reason() == Qt.FocusReason.PopupFocusReason:
            super().focusOutEvent(e)
            return
        self.submitted.emit()
        super().focusOutEvent(e)

    def contextMenuEvent(self, e) -> None:
        show_korean_text_menu(self, e.globalPos())

    def _sync_height(self) -> None:
        lines = int(round(self.document().size().height())) or 1
        lines = max(1, min(2, lines))
        line_h = self.fontMetrics().lineSpacing()
        pad = 18
        self.setFixedHeight(line_h * lines + pad)


class TodoItem(QWidget):
    request_remove = Signal(int)

    def __init__(self, todo: Todo, service, compact: bool = False,
                  timer_service=None, settings_repo=None, events=None, parent=None,
                  allow_drag: bool = True, allow_week_move: bool = False,
                  priority_sort: bool = False):
        super().__init__(parent)
        self.todo = todo
        self._service = service
        self._timer = timer_service
        self._settings = settings_repo
        self._events = events
        self._compact = compact
        self._allow_drag = allow_drag
        self._allow_week_move = allow_week_move
        self._priority_sort = priority_sort
        self._press_pos: QPoint | None = None
        self._dragged = False
        self._editing = False
        self._timer_active = bool(timer_service and timer_service.is_active(todo.id))

        self.setObjectName("todoRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 6, 4)
        lay.setSpacing(6)

        self.priority_btn = PriorityDotButton(
            todo.priority,
            self._settings,
            size=19,
            visual_size=14,
            fixed_width=10,
            fixed_height=19,
        )
        self.priority_btn.setToolTip("중요도")
        self.priority_btn.clicked.connect(self._cycle_priority)
        lay.addWidget(self.priority_btn)

        self.check = QCheckBox()
        self.check.setChecked(todo.completed)
        self.check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.check.setToolTip("완료")
        self.check.clicked.connect(self._on_checkbox_clicked)
        lay.addWidget(self.check)
        # setVisible 은 반드시 addWidget(부모 지정) 뒤에. 부모 없는 위젯에 setVisible(True)
        # 를 하면 잠깐 독립 최상위 창으로 떴다 사라지는 깜빡임이 생긴다.
        self.check.setVisible(not self._timer_active)

        # 타이머 실행 중인 항목은 체크박스 대신 타이머 아이콘(클릭=완료) 표시
        self.timer_btn = QToolButton()
        self.timer_btn.setObjectName("timerBtn")
        self.timer_btn.setIcon(QIcon(_clock_pixmap(16, "#7F77DD")))
        self.timer_btn.setAutoRaise(True)
        self.timer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.timer_btn.setFixedSize(20, 20)
        self.timer_btn.setToolTip("타이머 중 · 클릭하면 완료")
        self.timer_btn.clicked.connect(self._complete_and_clear_timer)
        lay.addWidget(self.timer_btn)
        self.timer_btn.setVisible(self._timer_active)  # addWidget 뒤에(최상위 창 깜빡임 방지)

        self.label = QLabel()
        self.label.setObjectName("todoLabel")
        self.label.setProperty("state", "done" if todo.completed else "active")
        self.label.setWordWrap(False)
        self.label.setMinimumWidth(0)
        self.label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._apply_strike()
        lay.addWidget(self.label, 1)

        self.editor = _TodoEditor(todo.content)
        self.editor.setVisible(False)
        self.editor.submitted.connect(self._commit_edit)
        lay.addWidget(self.editor, 1)

        # 반복 규칙으로 자동 생성된 항목 표시 뱃지
        self.recur_badge = QLabel("반복")
        self.recur_badge.setObjectName("recurBadge")
        self.recur_badge.setVisible(self.todo.is_recurring_instance)
        lay.addWidget(self.recur_badge)

        # hover 편집/삭제 (오른쪽 끝 고정: 연필 → 휴지통 순, 간격 좁게)
        self.pencil = QToolButton()
        self.pencil.setObjectName("pencilBtn")
        self.pencil.setIcon(QIcon(_pencil_pixmap()))
        self.pencil.setAutoRaise(True)
        self.pencil.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pencil.setFixedSize(20, 20)
        self.pencil.setVisible(False)
        self.pencil.setToolTip("편집")
        self.pencil.clicked.connect(self._enter_edit)

        self.xbtn = QToolButton()
        self.xbtn.setObjectName("xBtn")
        self.xbtn.setIcon(QIcon(_trash_pixmap(16, "#D85A30")))
        self.xbtn.setAutoRaise(True)
        self.xbtn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.xbtn.setFixedSize(20, 20)
        self.xbtn.setVisible(False)
        self.xbtn.setToolTip("삭제")
        self.xbtn.clicked.connect(lambda: self.request_remove.emit(self.todo.id))

        if not compact:
            self._actions = QWidget()
            # 평소엔 폭 0으로 접어 텍스트가 오른쪽 여백까지 쓰게 하고, hover 때만 펼친다.
            self._actions.setFixedWidth(0)
            self._actions.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            action_lay = QHBoxLayout(self._actions)
            action_lay.setContentsMargins(0, 0, 0, 0)
            action_lay.setSpacing(2)
            action_lay.addWidget(self.pencil)
            action_lay.addWidget(self.xbtn)
            lay.addWidget(self._actions)

        self.setMouseTracking(True)
        self.setToolTip("")  # 기본 툴팁 끔 (직접 1.5초 후 표시)
        self._tip_timer = QTimer(self)
        self._tip_timer.setSingleShot(True)
        self._tip_timer.setInterval(_TOOLTIP_DELAY_MS)
        self._tip_timer.timeout.connect(self._show_tooltip)

    def flash_focus(self) -> None:
        """외부 패널에서 이동해 온 항목을 잠깐 강조했다가 원래 배경으로 되돌린다."""
        self._clear_focus_overlay()

        overlay = QWidget(self)
        overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        overlay.setStyleSheet(
            "background: rgba(127, 119, 221, 48); border-radius: 9px;"
        )
        overlay.setGeometry(self.rect())
        overlay.raise_()
        overlay.show()

        eff = QGraphicsOpacityEffect(overlay)
        overlay.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(820)
        anim.setStartValue(0.0)
        anim.setKeyValueAt(0.28, 1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def done() -> None:
            self._focus_anim = None
            old_overlay = getattr(self, "_focus_overlay", None)
            if old_overlay is not None:
                old_overlay.hide()
                old_overlay.deleteLater()
                self._focus_overlay = None

        anim.finished.connect(done)
        self._focus_overlay = overlay
        self._focus_anim = anim
        anim.start()

    def _clear_focus_overlay(self) -> None:
        old_anim = getattr(self, "_focus_anim", None)
        if old_anim is not None:
            old_anim.stop()
            self._focus_anim = None
        old_overlay = getattr(self, "_focus_overlay", None)
        if old_overlay is not None:
            old_overlay.hide()
            old_overlay.deleteLater()
            self._focus_overlay = None

    # ── 완료 토글 / 중요도 순환 ─────────────────────────────
    def _on_checkbox_clicked(self) -> None:
        if self._editing:
            self.check.setChecked(self.todo.completed)
            return
        self._service.toggle(self.todo.id)

    def _cycle_priority(self) -> None:
        if self._editing:
            return
        next_priority = _next_priority(self.todo.priority)
        self.todo.priority = next_priority
        self.priority_btn.set_priority(next_priority)
        self._service.set_priority(
            self.todo.id,
            next_priority,
            notify=self._priority_sort,
        )

    def _apply_strike(self) -> None:
        f: QFont = self.label.font()
        f.setStrikeOut(self.todo.completed)
        self.label.setFont(f)
        self._update_elision()

    # ── 말줄임 ──────────────────────────────────────────────
    def _update_elision(self) -> None:
        fm = QFontMetrics(self.label.font())
        w = max(10, self.label.width())
        lines = self.todo.content.splitlines() or [""]
        self.label.setText(
            "\n".join(fm.elidedText(line, Qt.TextElideMode.ElideRight, w) for line in lines)
        )

    def _set_actions_reserved(self, reserved: bool) -> None:
        """hover 편집/삭제 버튼 자리를 펼치거나(46) 접는다(0).
        접으면 라벨이 그 폭만큼 넓어져 말줄임 여백이 사라진다."""
        if self._compact or not hasattr(self, "_actions"):
            return
        w = _ACTION_WIDTH if reserved else 0
        if self._actions.maximumWidth() == w:
            return
        self._actions.setFixedWidth(w)
        self.layout().activate()  # 라벨 폭을 즉시 반영해야 말줄임 계산이 맞다
        self._update_elision()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        overlay = getattr(self, "_focus_overlay", None)
        if overlay is not None:
            overlay.setGeometry(self.rect())
        if not self._editing:
            self._update_elision()

    def refresh_text_layout(self) -> None:
        if not self._editing:
            self._update_elision()

    # ── 편집 ────────────────────────────────────────────────
    def _enter_edit(self) -> None:
        self._editing = True
        self.editor.setPlainText(self.todo.content)
        self.label.setVisible(False)
        self.pencil.setVisible(False)
        self.xbtn.setVisible(False)
        self._set_actions_reserved(False)  # 편집창은 전체 폭 사용
        self.editor.setVisible(True)
        self.editor.setFocus()
        self.editor.selectAll()

    def _commit_edit(self) -> None:
        if not self._editing:
            return
        self._editing = False
        text = self.editor.toPlainText().strip()
        self.editor.setVisible(False)
        self.label.setVisible(True)
        if text and text != self.todo.content:
            self._service.edit(self.todo.id, text)
        else:
            self._update_elision()

    # ── hover: 아이콘 + 1.5초 툴팁 ──────────────────────────
    def enterEvent(self, _e) -> None:
        if not self._compact and not self._editing:
            self.pencil.setVisible(True)
            self.xbtn.setVisible(True)
            self._set_actions_reserved(True)
        self._tip_timer.start()

    def leaveEvent(self, _e) -> None:
        self.pencil.setVisible(False)
        self.xbtn.setVisible(False)
        self._set_actions_reserved(False)
        self._tip_timer.stop()
        QToolTip.hideText()

    def _show_tooltip(self) -> None:
        if not self.underMouse() or self._editing:
            return
        # 편집/삭제 버튼 위에서는 버튼 자체 툴팁('편집'/'삭제')을 살린다.
        child = self.childAt(self.mapFromGlobal(QCursor.pos()))
        if child in (self.pencil, self.xbtn):
            return
        QToolTip.showText(QCursor.pos(), self.todo.content, self)

    # ── 마우스: 클릭=토글 / 드래그=이동 ─────────────────────
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_pos = e.position().toPoint()
            self._dragged = False
            e.accept()        # 이 위젯이 마우스를 잡아야 move 이벤트가 들어와 드래그가 시작됨
        elif e.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(e.globalPosition().toPoint())
            e.accept()
        else:
            super().mousePressEvent(e)

    # ── 우클릭 메뉴(편집 + 복사 + 중요도 + 고정 + 이동 + 타이머 + 복제) ─────
    def _show_context_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        edit = menu.addAction("편집")
        edit.triggered.connect(self._enter_edit)
        copy = menu.addAction("복사")
        copy.triggered.connect(lambda: copy_todo_to_clipboard(self.todo))
        menu.addSeparator()
        self._add_priority_menu(menu)
        self._add_pin_action(menu)
        self._add_move_actions(menu)
        self._add_timer_actions(menu)
        self._add_delete_action(menu)
        menu.exec(global_pos)

    def _add_priority_menu(self, menu: QMenu) -> None:
        priority_menu = menu.addMenu("중요도")
        priority_menu.setStyleSheet(menu_qss(theme_mode(self._settings)))
        for value, label in _PRIORITY_MENU_CHOICES:
            act = priority_menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(self.todo.priority == value)
            act.triggered.connect(
                lambda _checked=False, priority=value: self._service.set_priority(
                    self.todo.id, priority
                )
            )
        menu.addSeparator()

    def _add_pin_action(self, menu: QMenu) -> None:
        if self.todo.pinned:
            pin = menu.addAction("상단고정 해제")
            pin.triggered.connect(lambda: self._service.set_pinned(self.todo.id, False))
            menu.addSeparator()
        elif not self.todo.completed:
            pin = menu.addAction("상단고정")
            pin.triggered.connect(lambda: self._service.set_pinned(self.todo.id, True))
            menu.addSeparator()

    def _add_move_actions(self, menu: QMenu) -> None:
        if self.todo.completed:
            return
        next_day = menu.addAction("다음날로 이동")
        next_day.triggered.connect(lambda: self._move_by_days(1))
        if not self._allow_week_move:
            menu.addSeparator()
            return
        prev_week = menu.addAction("이전 주로 이동")
        prev_week.triggered.connect(lambda: self._move_by_days(-7))
        next_week = menu.addAction("다음 주로 이동")
        next_week.triggered.connect(lambda: self._move_by_days(7))
        menu.addSeparator()

    def _move_by_days(self, days: int) -> None:
        new_iso = (date.fromisoformat(self.todo.due_date) + timedelta(days=days)).isoformat()
        self._service.move(self.todo.id, new_iso)

    def _add_timer_actions(self, menu: QMenu) -> None:
        timer_running = self._timer is not None and self._timer.is_active(self.todo.id)
        if timer_running:
            act = menu.addAction("타이머 해제")
            act.triggered.connect(lambda: self._timer.cancel_for(self.todo.id))
        else:
            if self._timer is not None and not self.todo.completed:
                act = menu.addAction("타이머 설정")
                act.triggered.connect(self._set_timer)
            dup = menu.addAction("복제")
            dup.triggered.connect(lambda: self._service.duplicate(self.todo.id))
        menu.addSeparator()

    def _add_delete_action(self, menu: QMenu) -> None:
        rm = menu.addAction("삭제")
        rm.triggered.connect(lambda: self.request_remove.emit(self.todo.id))

    def _set_timer(self) -> None:
        from ui.timer_setup_dialog import TimerSetupDialog

        replacing = self._timer.is_active() and not self._timer.is_active(self.todo.id)
        dlg = TimerSetupDialog(
            self.todo.content, self._settings, replacing=replacing,
            parent=self.window(),
        )
        if dlg.exec() and dlg.result_seconds:
            self._timer.start(self.todo.id, self.todo.content, dlg.result_seconds,
                              auto_complete=dlg.auto_complete)

    def _complete_and_clear_timer(self) -> None:
        """타이머 아이콘 클릭 = 완료 처리(+타이머 해제)."""
        if self._timer is not None:
            self._timer.cancel_for(self.todo.id)
        self._service.toggle(self.todo.id)

    def mouseMoveEvent(self, e) -> None:
        if self._press_pos is None or self._editing:
            return
        dist = (e.position().toPoint() - self._press_pos).manhattanLength()
        if dist < QApplication.startDragDistance():
            return
        self._start_drag()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if not self._dragged and not self._editing and self._press_pos is not None:
            if self._timer_active:
                # 타이머 패널이 닫혀 있으면 본문 클릭 = 패널 열기(#4),
                # 열려 있으면 기존대로 완료(+해제).
                if self._timer_panel_open():
                    self._complete_and_clear_timer()
                else:
                    self._open_timer_panel()
            else:
                self._service.toggle(self.todo.id)   # 본문 클릭 = 완료 토글
        self._press_pos = None

    def _timer_panel_open(self) -> bool:
        if self._settings is None:
            return False
        return (self._settings.get(policies.KEY_TIMER_PANEL, "0") or "0") == "1"

    def _open_timer_panel(self) -> None:
        """타이머 중인 할일 클릭 시 닫혀 있던 타이머 패널을 연다(#4).
        설정 저장은 BubbleWidget 이 처리하므로 시그널만 쏜다."""
        if self._events is not None:
            self._events.timer_panel_changed.emit(True)

    def _start_drag(self) -> None:
        if not self._allow_drag:
            return
        self._dragged = True
        self._tip_timer.stop()
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME_TODO, f"{self.todo.id}|{self.todo.due_date}".encode())
        drag.setMimeData(mime)
        # 마우스 아래에 끌고 있는 할일을 반투명 미리보기로 표시
        pm = self._drag_preview()
        drag.setPixmap(pm)
        lw = int(pm.width() / pm.devicePixelRatio())
        drag.setHotSpot(QPoint(lw // 2, -8))  # 커서 살짝 아래·가운데
        # 캐릭터(휴지통) 위 = Copy 액션 → 휴지통 커서. 날짜 칸 = Move → 기본 커서.
        drag.setDragCursor(_trash_pixmap(30, "#E5484D"), Qt.DropAction.CopyAction)
        drag.exec(Qt.DropAction.MoveAction | Qt.DropAction.CopyAction)
        self._press_pos = None
        # 삭제는 캐릭터에 드롭 시 캐릭터 쪽에서 처리.

    def _drag_preview(self) -> QPixmap:
        """드래그 미리보기: 연필/휴지통 숨기고 캡처 후 반투명 처리.
        너비는 이 항목의 텍스트 길이 기준으로 고정(같은 컬럼 최장 텍스트에 끌려가지 않도록)."""
        pencil_v, x_v = self.pencil.isVisible(), self.xbtn.isVisible()
        self.pencil.setVisible(False)
        self.xbtn.setVisible(False)
        src = self.grab()
        self.pencil.setVisible(pencil_v)
        self.xbtn.setVisible(x_v)

        dpr = src.devicePixelRatio()
        # 이 항목 텍스트 길이 기반 목표 너비(논리 픽셀)
        fm = self.label.fontMetrics()
        text_w = fm.horizontalAdvance(self.todo.content)
        spacing = self.layout().spacing()
        margins = self.layout().contentsMargins()
        action_w = self.timer_btn.sizeHint().width() if self._timer_active else self.check.sizeHint().width()
        leading_w = self.priority_btn.sizeHint().width() + spacing + action_w + spacing
        # layout: margins + priority ribbon + checkbox/timer + text + small breathing room
        target_w = min(
            margins.left() + leading_w + text_w + margins.right() + 8,
            int(src.width() / dpr),
        )

        pm = QPixmap(int(target_w * dpr), src.height())
        pm.setDevicePixelRatio(dpr)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setOpacity(0.7)
        p.drawPixmap(0, 0, src)
        p.end()
        return pm


# ── 아이콘 그리기 (테마 무관, 직접 렌더) ────────────────────
def _trash_pixmap(size: int, color: str) -> QPixmap:
    """휴지통 아이콘 픽스맵."""
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(max(1.4, size * 0.07))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    s = size
    # 손잡이
    p.drawLine(int(s * 0.40), int(s * 0.22), int(s * 0.60), int(s * 0.22))
    # 뚜껑
    p.drawLine(int(s * 0.24), int(s * 0.32), int(s * 0.76), int(s * 0.32))
    # 통 몸체
    p.drawLine(int(s * 0.30), int(s * 0.32), int(s * 0.34), int(s * 0.80))
    p.drawLine(int(s * 0.70), int(s * 0.32), int(s * 0.66), int(s * 0.80))
    p.drawLine(int(s * 0.34), int(s * 0.80), int(s * 0.66), int(s * 0.80))
    # 세로 줄
    p.drawLine(int(s * 0.50), int(s * 0.40), int(s * 0.50), int(s * 0.72))
    p.end()
    return pm


def _clock_pixmap(size: int, color: str) -> QPixmap:
    """시계(타이머) 아이콘 픽스맵."""
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(max(1.4, size * 0.09))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    s = size
    # 테두리 원
    p.drawEllipse(int(s * 0.16), int(s * 0.22), int(s * 0.68), int(s * 0.68))
    # 시침/분침
    cx, cy = int(s * 0.50), int(s * 0.56)
    p.drawLine(cx, cy, cx, int(s * 0.34))
    p.drawLine(cx, cy, int(s * 0.66), cy)
    p.end()
    return pm


def _pencil_pixmap() -> QPixmap:
    size = 16
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#8A8A86"))
    pen.setWidthF(1.4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    s = size
    p.drawLine(int(s * 0.30), int(s * 0.72), int(s * 0.72), int(s * 0.30))
    p.drawLine(int(s * 0.30), int(s * 0.72), int(s * 0.24), int(s * 0.78))
    p.drawLine(int(s * 0.66), int(s * 0.24), int(s * 0.78), int(s * 0.36))
    p.end()
    return pm
