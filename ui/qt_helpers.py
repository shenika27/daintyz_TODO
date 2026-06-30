"""ui/qt_helpers.py — 위젯 공통 셋업 헬퍼."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget


def make_overlay_window(
    widget: QWidget, *, dialog: bool = False, always_on_top: bool = True
) -> None:
    """프레임리스·배경 투명·항상 위 오버레이 창 공통 설정.

    캐릭터/말풍선/패널 등 바탕화면에 떠 있는 창들이 공유한다.
    dialog=False → Tool(작업표시줄 미표시), dialog=True → Dialog(모달 등 대화상자).
    """
    kind = Qt.WindowType.Dialog if dialog else Qt.WindowType.Tool
    flags = (
        Qt.WindowType.FramelessWindowHint
        | kind
    )
    if always_on_top:
        flags |= Qt.WindowType.WindowStaysOnTopHint
    widget.setWindowFlags(flags)
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)


def set_overlay_always_on_top(widget: QWidget, on: bool) -> None:
    """이미 만들어진 오버레이 창의 항상 위 플래그를 토글한다."""
    flags = widget.windowFlags()
    if on:
        flags |= Qt.WindowType.WindowStaysOnTopHint
    else:
        flags &= ~Qt.WindowType.WindowStaysOnTopHint
    if flags == widget.windowFlags():
        return
    was_visible = widget.isVisible()
    widget.setWindowFlags(flags)
    if was_visible:
        widget.show()
