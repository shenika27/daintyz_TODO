"""ui/theme.py — 말풍선 테마(밝게/어둡게) 팔레트와 QSS 생성.

설정값 'light'|'dark'|'system' 을 받아 실제 'light'|'dark' 로 해석하고,
#bubbleRoot 하위에 적용할 스타일시트 문자열을 만든다.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

LIGHT = {
    "bg": "#FFFFFF",
    "surface": "#F4F2EC",
    "border": "rgba(0,0,0,0.10)",
    "border_strong": "rgba(0,0,0,0.16)",
    "text": "#2C2C2A",
    "sub": "#6B6A66",
    "accent": "#534AB7",
    "accent_soft": "#EEEDFE",
    "accent_text": "#3C3489",
    "check_border": "#B4B2A9",
    "red": "#D85A30",
    "dim": "#A3A29C",
}

DARK = {
    "bg": "#1C1C1F",
    "surface": "#2A2A30",
    "border": "rgba(255,255,255,0.10)",
    "border_strong": "rgba(255,255,255,0.18)",
    "text": "#ECEAF0",
    "sub": "#9A99A2",
    "accent": "#7F77DD",
    "accent_soft": "#3C3489",
    "accent_text": "#CECBF6",
    "check_border": "#5C5C66",
    "red": "#F09595",
    "dim": "#6E6E78",
}


def resolve(mode: str | None) -> str:
    """'light'|'dark'|'system' → 'light'|'dark'."""
    if mode == "light":
        return "light"
    if mode == "dark":
        return "dark"
    # system: OS 다크모드 따라감
    try:
        scheme = QApplication.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return "dark"
        if scheme == Qt.ColorScheme.Light:
            return "light"
    except Exception:  # noqa: BLE001
        pass
    # fallback: 창 배경 밝기로 추정
    try:
        c = QApplication.palette().window().color()
        if (c.red() + c.green() + c.blue()) / 3 < 128:
            return "dark"
    except Exception:  # noqa: BLE001
        pass
    return "light"


def palette(mode: str | None) -> dict:
    return DARK if resolve(mode) == "dark" else LIGHT


def qss(mode: str | None) -> str:
    c = palette(mode)
    return f"""
#bubbleRoot {{
    background: {c['bg']};
    border: 1px solid {c['border_strong']};
    border-radius: 14px;
}}
#bubbleRoot QLabel {{ color: {c['text']}; background: transparent; }}
#bubbleRoot QLabel#subText {{ color: {c['sub']}; }}
#bubbleRoot QLabel#emptyText {{ color: {c['sub']}; }}
#bubbleRoot QLabel#todoLabel[state="done"] {{ color: {c['dim']}; }}
#bubbleRoot QLabel#wdHead {{ color: {c['sub']}; }}
#bubbleRoot QLabel#dimDay {{ color: {c['dim']}; }}
#bubbleRoot QLabel#repeatTag {{
    color: {c['accent_text']};
    background: {c['accent_soft']};
    border-radius: 7px;
    padding: 1px 6px;
}}
#bubbleRoot QLabel#countBadge {{
    color: white; background: {c['accent']};
    border-radius: 9px; font-size: 10px;
}}

#bubbleRoot QToolButton {{
    border: none; background: transparent; color: {c['sub']};
    border-radius: 8px; padding: 4px;
}}
#bubbleRoot QToolButton:hover {{ background: {c['surface']}; }}
#bubbleRoot QToolButton#xBtn {{ color: {c['red']}; }}
#bubbleRoot QToolButton#undoBtn {{ color: {c['accent']}; }}

#bubbleRoot QLineEdit {{
    border: none; background: {c['surface']}; color: {c['text']};
    border-radius: 10px; padding: 6px 10px; selection-background-color: {c['accent']};
}}

#bubbleRoot QScrollArea {{ border: none; background: transparent; }}
#bubbleRoot QScrollArea > QWidget > QWidget {{ background: transparent; }}
#bubbleRoot QScrollBar:vertical {{
    background: transparent; width: 7px; margin: 2px;
}}
#bubbleRoot QScrollBar::handle:vertical {{
    background: {c['check_border']}; border-radius: 3px; min-height: 20px;
}}
#bubbleRoot QScrollBar::add-line:vertical, #bubbleRoot QScrollBar::sub-line:vertical {{ height: 0; }}
#bubbleRoot QScrollBar::add-page:vertical, #bubbleRoot QScrollBar::sub-page:vertical {{ background: transparent; }}

#bubbleRoot QWidget#todoRow:hover {{ background: {c['surface']}; border-radius: 9px; }}

#bubbleRoot QCheckBox {{ spacing: 0; }}
#bubbleRoot QCheckBox::indicator {{
    width: 14px; height: 14px;
    border: 1.5px solid {c['check_border']}; border-radius: 4px; background: transparent;
}}
#bubbleRoot QCheckBox::indicator:checked {{
    background: {c['accent']}; border-color: {c['accent']};
}}

#bubbleRoot QFrame#dayCol {{ border: 1px solid {c['border']}; border-radius: 8px; }}
#bubbleRoot QFrame#dayCol[selected="true"] {{ border: 2px solid {c['accent']}; }}
#bubbleRoot QFrame#monthCell {{ border: 1px solid {c['border']}; border-radius: 6px; }}
#bubbleRoot QFrame#monthCell[selected="true"] {{ border: 2px solid {c['accent']}; }}
"""
