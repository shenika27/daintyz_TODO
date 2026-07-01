"""ui/bubble/input_bar.py — 말풍선 하단 입력. Enter 시 선택 날짜에 할일 추가."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QPlainTextEdit, QSizePolicy, QWidget


class _TodoInputEdit(QPlainTextEdit):
    submitted = pyqtSignal()

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

    def _sync_height(self) -> None:
        # QPlainTextEdit 의 document().size().height() 는 픽셀이 아니라 '줄 수'다
        # (래핑 포함). 1~2줄만 높이에 반영하고, 3줄 이상은 2줄로 고정(그 이상은 스크롤).
        lines = int(round(self.document().size().height())) or 1
        lines = max(1, min(2, lines))
        line_h = self.fontMetrics().lineSpacing()
        pad = 18  # 프레임 + 문서 여백 보정(기존 한 줄 높이와 동일하게)
        self.setFixedHeight(line_h * lines + pad)


class InputBar(QWidget):
    def __init__(self, service, get_iso, parent=None):
        super().__init__(parent)
        self._service = service
        self._get_iso = get_iso

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        self.edit = _TodoInputEdit()
        self.edit.submitted.connect(self._add)
        lay.addWidget(self.edit)

    def _add(self) -> None:
        text = self.edit.toPlainText().strip()
        if not text:
            return
        self._service.add(text, self._get_iso())
        self.edit.clear()
