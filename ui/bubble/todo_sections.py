from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from ui.bubble.todo_item import TodoItem


class PinnedTodoSection(QWidget):
    def __init__(
        self,
        todos,
        service,
        timer_service=None,
        settings_repo=None,
        events=None,
        compact: bool = False,
        allow_week_move: bool = False,
        margins: tuple[int, int, int, int] = (0, 0, 0, 0),
        parent=None,
    ):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*margins)
        lay.setSpacing(2)
        for todo in todos:
            item = TodoItem(
                todo,
                service,
                compact=compact,
                timer_service=timer_service,
                settings_repo=settings_repo,
                events=events,
                allow_drag=False,
                allow_week_move=allow_week_move,
            )
            item.request_remove.connect(service.remove)
            lay.addWidget(item)


def pin_separator() -> QFrame:
    sep = QFrame()
    sep.setObjectName("pinSeparator")
    sep.setFrameShape(QFrame.Shape.HLine)
    return sep
