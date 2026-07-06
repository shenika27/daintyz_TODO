"""ui/bubble/input_bar.py — 말풍선 하단 입력. Enter 시 선택 날짜에 할일 추가."""
from __future__ import annotations

from time import monotonic

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPlainTextEdit,
    QSizePolicy,
    QWidget,
)

from domain.models import PRIORITY_NONE
from ui.bubble.priority_ui import PriorityDotButton, PriorityPickerPopup
from ui.qt_helpers import show_korean_text_menu


class _TodoInputEdit(QPlainTextEdit):
    submitted = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("할 일 입력 후 Enter")
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

    def contextMenuEvent(self, e) -> None:
        show_korean_text_menu(self, e.globalPos())

    def _sync_height(self) -> None:
        # QPlainTextEdit 의 document().size().height() 는 픽셀이 아니라 '줄 수'다
        # (래핑 포함). 1~2줄만 높이에 반영하고, 3줄 이상은 2줄로 고정(그 이상은 스크롤).
        lines = int(round(self.document().size().height())) or 1
        lines = max(1, min(2, lines))
        line_h = self.fontMetrics().lineSpacing()
        pad = 18  # 프레임 + 문서 여백 보정(기존 한 줄 높이와 동일하게)
        self.setFixedHeight(line_h * lines + pad)


class InputBar(QWidget):
    def __init__(self, service, get_iso, settings_repo=None, parent=None):
        super().__init__(parent)
        self._service = service
        self._get_iso = get_iso
        self._settings = settings_repo
        self._priority = PRIORITY_NONE
        self._priority_popup: PriorityPickerPopup | None = None
        self._priority_popup_closed_at = 0.0
        self._closing_priority_popup_intentionally = False

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(0)

        self.input_frame = QFrame()
        self.input_frame.setObjectName("todoInputFrame")
        frame_lay = QHBoxLayout(self.input_frame)
        frame_lay.setContentsMargins(7, 0, 10, 0)
        frame_lay.setSpacing(6)

        self.priority_btn = PriorityDotButton(PRIORITY_NONE, self._settings)
        self.priority_btn.setToolTip("새 할일 중요도")
        self.priority_btn.clicked.connect(self._toggle_priority_popup)
        frame_lay.addWidget(self.priority_btn)

        self.edit = _TodoInputEdit()
        self.edit.setObjectName("todoInputEdit")
        self.edit.submitted.connect(self._add)
        frame_lay.addWidget(self.edit, 1)
        lay.addWidget(self.input_frame, 1)

    def _add(self) -> None:
        text = self.edit.toPlainText().strip()
        if not text:
            return
        self._service.add(text, self._get_iso(), self._priority)
        self.edit.clear()

    def _toggle_priority_popup(self) -> None:
        if self._priority_popup is not None and self._priority_popup.isVisible():
            self._choose_priority(PRIORITY_NONE)
            return
        if monotonic() - self._priority_popup_closed_at < 0.25:
            self._choose_priority(PRIORITY_NONE)
            return
        if self._priority_popup is not None:
            self._priority_popup.deleteLater()
            self._priority_popup = None
        self._show_priority_popup()

    def _show_priority_popup(self) -> None:
        self.priority_btn.set_priority(PRIORITY_NONE)
        popup = PriorityPickerPopup(self._settings)
        popup.selected.connect(self._choose_priority)
        popup.closed.connect(lambda p=popup: self._on_priority_popup_closed(p))
        popup.destroyed.connect(lambda _obj=None, p=popup: self._on_priority_popup_destroyed(p))
        self._priority_popup = popup
        popup.show_above(self.priority_btn)

    def _choose_priority(self, priority: int) -> None:
        self._priority = priority
        self._close_priority_popup()

    def _close_priority_popup(self) -> None:
        popup = self._priority_popup
        if popup is not None:
            self._closing_priority_popup_intentionally = True
            popup.close_animated()
        self.priority_btn.set_priority(self._priority)

    def _on_priority_popup_closed(self, popup: PriorityPickerPopup) -> None:
        if popup is not self._priority_popup:
            return
        if self._closing_priority_popup_intentionally:
            return
        pos = self.priority_btn.mapFromGlobal(QCursor.pos())
        self._priority_popup_closed_at = (
            monotonic() if self.priority_btn.rect().contains(pos) else 0.0
        )

    def _on_priority_popup_destroyed(self, popup: PriorityPickerPopup) -> None:
        if popup is not self._priority_popup:
            return
        self._closing_priority_popup_intentionally = False
        self._priority_popup = None
        self.priority_btn.set_priority(self._priority)
