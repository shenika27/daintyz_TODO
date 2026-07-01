"""ui/qt_helpers.py — 위젯 공통 셋업 헬퍼."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QMenu, QPlainTextEdit, QWidget


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


def show_korean_text_menu(edit: QPlainTextEdit, global_pos) -> None:
    """QPlainTextEdit 우클릭 시 Qt 기본(영어) 메뉴 대신 한글 편집 메뉴를 띄운다.
    Qt 번역 파일을 번들하지 않아도 되도록 표준 편집 동작을 직접 구성한다."""
    cur = edit.textCursor()
    has_sel = cur.hasSelection()
    read_only = edit.isReadOnly()
    doc = edit.document()

    menu = QMenu(edit)

    a = menu.addAction("실행 취소")
    a.setShortcut(QKeySequence.StandardKey.Undo)
    a.setEnabled(not read_only and doc.isUndoAvailable())
    a.triggered.connect(edit.undo)

    a = menu.addAction("다시 실행")
    a.setShortcut(QKeySequence.StandardKey.Redo)
    a.setEnabled(not read_only and doc.isRedoAvailable())
    a.triggered.connect(edit.redo)

    menu.addSeparator()

    a = menu.addAction("잘라내기")
    a.setShortcut(QKeySequence.StandardKey.Cut)
    a.setEnabled(not read_only and has_sel)
    a.triggered.connect(edit.cut)

    a = menu.addAction("복사")
    a.setShortcut(QKeySequence.StandardKey.Copy)
    a.setEnabled(has_sel)
    a.triggered.connect(edit.copy)

    a = menu.addAction("붙여넣기")
    a.setShortcut(QKeySequence.StandardKey.Paste)
    a.setEnabled(not read_only and edit.canPaste())
    a.triggered.connect(edit.paste)

    def _delete_selection() -> None:
        c = edit.textCursor()
        c.removeSelectedText()
        edit.setTextCursor(c)

    a = menu.addAction("삭제")
    a.setEnabled(not read_only and has_sel)
    a.triggered.connect(_delete_selection)

    menu.addSeparator()

    a = menu.addAction("모두 선택")
    a.setShortcut(QKeySequence.StandardKey.SelectAll)
    a.setEnabled(not doc.isEmpty())
    a.triggered.connect(edit.selectAll)

    menu.exec(global_pos)


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
