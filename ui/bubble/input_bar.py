"""ui/bubble/input_bar.py — 말풍선 하단 입력. Enter 시 선택 날짜에 할일 추가."""
from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QWidget


class InputBar(QWidget):
    def __init__(self, service, get_iso, parent=None):
        super().__init__(parent)
        self._service = service
        self._get_iso = get_iso

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 2, 6, 4)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("할 일 입력 후 Enter")
        self.edit.returnPressed.connect(self._add)
        lay.addWidget(self.edit)

    def _add(self) -> None:
        text = self.edit.text().strip()
        if not text:
            return
        self._service.add(text, self._get_iso())
        self.edit.clear()
