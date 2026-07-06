"""core/local_hotkeys.py - 앱 포커스 중에만 동작하는 단축키."""
from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QKeySequenceEdit

log = logging.getLogger(__name__)

_MODIFIER_KEYS = {
    Qt.Key.Key_Control,
    Qt.Key.Key_Shift,
    Qt.Key.Key_Alt,
    Qt.Key.Key_Meta,
}
_MODIFIER_MASK = (
    Qt.KeyboardModifier.ControlModifier
    | Qt.KeyboardModifier.AltModifier
    | Qt.KeyboardModifier.ShiftModifier
    | Qt.KeyboardModifier.MetaModifier
)


class LocalHotkeys(QObject):
    """QApplication 이벤트 필터로 앱 활성 상태의 단축키만 처리한다."""

    def __init__(self, app: QApplication):
        super().__init__(app)
        self._app = app
        self._callbacks: list[tuple[QKeySequence, Callable[[], None]]] = []
        app.installEventFilter(self)

    def register(self, seq: str, callback: Callable[[], None]) -> bool:
        key_sequence = QKeySequence(seq)
        if key_sequence.isEmpty() or key_sequence.count() != 1:
            return False

        combo = key_sequence[0]
        if not combo.keyboardModifiers():
            log.warning("Local hotkey ignored because modifier is missing: %s", seq)
            return False

        self._callbacks.append((key_sequence, callback))
        return True

    def unregister_all(self) -> None:
        self._callbacks.clear()

    def eventFilter(self, watched, event):  # noqa: N802 (Qt 시그니처)
        if event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(watched, event)
        if event.isAutoRepeat() or event.key() in _MODIFIER_KEYS:
            return super().eventFilter(watched, event)
        if self._app.activeWindow() is None and self._app.focusWidget() is None:
            return super().eventFilter(watched, event)
        if isinstance(self._app.focusWidget(), QKeySequenceEdit):
            return super().eventFilter(watched, event)

        modifiers = event.modifiers() & _MODIFIER_MASK
        pressed = QKeySequence(int(modifiers.value) | int(event.key()))
        for key_sequence, callback in list(self._callbacks):
            if pressed.matches(key_sequence) == QKeySequence.SequenceMatch.ExactMatch:
                callback()
                event.accept()
                return True
        return super().eventFilter(watched, event)
