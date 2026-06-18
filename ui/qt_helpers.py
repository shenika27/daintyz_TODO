"""ui/qt_helpers.py — 위젯 공통 셋업 헬퍼."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget


def make_overlay_window(widget: QWidget, *, dialog: bool = False) -> None:
    """프레임리스·배경 투명·항상 위 오버레이 창 공통 설정.

    캐릭터/말풍선/패널 등 바탕화면에 떠 있는 창들이 공유한다.
    dialog=False → Tool(작업표시줄 미표시), dialog=True → Dialog(모달 등 대화상자).
    """
    kind = Qt.WindowType.Dialog if dialog else Qt.WindowType.Tool
    widget.setWindowFlags(
        Qt.WindowType.FramelessWindowHint
        | kind
        | Qt.WindowType.WindowStaysOnTopHint
    )
    widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
