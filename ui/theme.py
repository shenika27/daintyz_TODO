"""ui/theme.py — 말풍선 테마(밝게/어둡게) 팔레트와 QSS 생성.

설정값 'light'|'dark'|'system' 을 받아 실제 'light'|'dark' 로 해석하고,
#bubbleRoot 하위에 적용할 스타일시트 문자열을 만든다.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QApplication

from core import paths

_CHECK_VER = "v1"  # 체크마크 디자인 바뀌면 올려서 캐시 갱신
_ARROW_VER = "v1"  # 스핀박스 화살표 디자인 바뀌면 올려서 캐시 갱신

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
    "ok": "#2E9E5B",
    "badge_todo": "#F2A98F",   # 월간 '할일' 배지 배경(옅은 빨강, 검정 텍스트)
    "badge_done": "#9FD06A",   # 월간 '완료' 배지 배경(연두, 검정 텍스트)
    "badge_text": "#1A1A1A",   # 라이트: 검정
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
    "ok": "#5BC081",
    "badge_todo": "#8B3A28",   # 월간 '할일' 배지 배경(진한 빨강, 흰 텍스트)
    "badge_done": "#3C6E2A",   # 월간 '완료' 배지 배경(진한 초록, 흰 텍스트)
    "badge_text": "#FFFFFF",   # 다크: 흰색
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


def _check_icon_path() -> str:
    """체크박스용 흰색 체크마크 PNG를 캐시(사용자 데이터)에 만들어 경로를 돌려준다.
    accent 채움 위에 올라가므로 흰색이면 밝게/어둡게 모두 잘 보인다."""
    path = paths.app_data_dir() / f"check_{_CHECK_VER}.png"
    if not path.exists():
        size = 28
        pm = QPixmap(size, size)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#FFFFFF"))
        pen.setWidthF(size * 0.13)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        s = size
        p.drawLine(QPointF(s * 0.24, s * 0.52), QPointF(s * 0.42, s * 0.70))
        p.drawLine(QPointF(s * 0.42, s * 0.70), QPointF(s * 0.74, s * 0.30))
        p.end()
        pm.save(str(path), "PNG")
    return path.as_posix()


def arrow_icon_path(direction: str, color: str) -> str:
    """스핀박스용 ▲/▼ 삼각형 화살표 PNG를 (방향·색상)별로 캐시에 만들어 경로를 돌려준다.
    direction: 'up'|'down'. color 는 '#RRGGBB'. 회색/보라 등 호출자가 색을 지정한다."""
    tag = color.lstrip("#")
    path = paths.app_data_dir() / f"arrow_{direction}_{tag}_{_ARROW_VER}.png"
    if not path.exists():
        size = 16
        pm = QPixmap(size, size)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(color))
        p.setPen(Qt.PenStyle.NoPen)
        s = size
        if direction == "up":
            pts = [QPointF(s * 0.5, s * 0.34), QPointF(s * 0.74, s * 0.64),
                   QPointF(s * 0.26, s * 0.64)]
        else:
            pts = [QPointF(s * 0.26, s * 0.36), QPointF(s * 0.74, s * 0.36),
                   QPointF(s * 0.5, s * 0.66)]
        p.drawPolygon(QPolygonF(pts))
        p.end()
        pm.save(str(path), "PNG")
    return path.as_posix()


def qss(mode: str | None) -> str:
    c = palette(mode)
    check_url = _check_icon_path()
    arrow_up = arrow_icon_path("up", c["sub"])
    arrow_down = arrow_icon_path("down", c["sub"])
    return f"""
#bubbleRoot {{
    background: {c['bg']};
    border: 1px solid {c['border_strong']};
    border-radius: 14px;
}}
#bubbleRoot QLabel {{ color: {c['text']}; background: transparent; }}
#bubbleRoot QLabel#bubbleTitle[today="true"] {{ color: {c['accent']}; }}
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
#bubbleRoot QLabel#badgeTotal {{
    background: {c['badge_todo']}; color: {c['badge_text']};
    border-radius: 4px; font-size: 9px; padding: 0px 4px;
}}
#bubbleRoot QLabel#badgeDone {{
    background: {c['badge_done']}; color: {c['badge_text']};
    border-radius: 4px; font-size: 9px; padding: 0px 4px;
}}
#bubbleRoot QLabel#recurBadge {{
    background: {c['accent_soft']}; color: {c['accent_text']};
    border-radius: 6px; font-size: 9px; padding: 0px 5px;
}}

#bubbleRoot QToolButton {{
    border: none; background: transparent; color: {c['sub']};
    border-radius: 8px; padding: 4px;
}}
#bubbleRoot QToolButton:hover {{ background: {c['surface']}; }}
#bubbleRoot QToolButton#xBtn {{ color: {c['red']}; }}
#bubbleRoot QToolButton#headerBtn {{ padding: 4px 3px; }}
#bubbleRoot QToolButton#prioritySortBtn {{
    background: transparent; color: {c['sub']};
    border: none; border-radius: 14px;
    padding: 0px; font-weight: bold;
}}
#bubbleRoot QToolButton#prioritySortBtn:hover {{
    background: {c['surface']}; color: {c['sub']};
}}
#bubbleRoot QToolButton#prioritySortBtn:checked {{
    background: {c['surface']}; color: {c['sub']};
    border: 1px solid {c['border_strong']};
}}
#bubbleRoot QToolButton#prioritySortBtn:pressed {{
    background: {c['accent']}; color: #FFFFFF;
    border: 1px solid {c['accent']};
}}

#bubbleRoot QSpinBox#dateSpin {{
    background: {c['surface']}; color: {c['text']};
    border: 1px solid {c['border_strong']}; border-radius: 6px;
    padding: 1px 2px; min-width: 30px;
    selection-background-color: {c['accent']};
}}
#bubbleRoot QSpinBox#dateSpin:focus {{ border: 1px solid {c['accent']}; }}
#bubbleRoot QSpinBox#dateSpin::up-button {{
    subcontrol-origin: border; subcontrol-position: top right;
    width: 14px; border: none; background: transparent;
}}
#bubbleRoot QSpinBox#dateSpin::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right;
    width: 14px; border: none; background: transparent;
}}
#bubbleRoot QSpinBox#dateSpin::up-arrow {{
    image: url({arrow_up}); width: 8px; height: 8px;
}}
#bubbleRoot QSpinBox#dateSpin::down-arrow {{
    image: url({arrow_down}); width: 8px; height: 8px;
}}

#bubbleRoot QLineEdit, #bubbleRoot QPlainTextEdit {{
    border: none; background: {c['surface']}; color: {c['text']};
    border-radius: 10px; padding: 6px 10px; selection-background-color: {c['accent']};
}}
#bubbleRoot QFrame#todoInputFrame {{
    border: none; background: {c['surface']};
    border-radius: 10px;
}}
#bubbleRoot QPlainTextEdit#todoInputEdit {{
    border: none; background: transparent; color: {c['text']};
    border-radius: 0px; padding: 6px 0px;
    selection-background-color: {c['accent']};
}}
#bubbleRoot QPlainTextEdit#todoEditor,
#bubbleRoot QPlainTextEdit#todoEditor:hover,
#bubbleRoot QPlainTextEdit#todoEditor:focus {{
    border: none; background: {c['surface']}; color: {c['text']};
    border-radius: 10px; padding: 6px 10px;
    selection-background-color: {c['accent']};
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
#bubbleRoot QFrame#pinSeparator {{
    color: {c['border_strong']};
    background: {c['border_strong']};
    min-height: 1px;
    max-height: 1px;
    border: none;
}}

#bubbleRoot QCheckBox {{ spacing: 0; }}
#bubbleRoot QCheckBox::indicator {{
    width: 15px; height: 15px;
    border: 1.5px solid {c['check_border']}; border-radius: 5px; background: transparent;
}}
#bubbleRoot QCheckBox::indicator:unchecked:hover {{
    border-color: {c['accent']}; background: {c['accent_soft']};
}}
#bubbleRoot QCheckBox::indicator:checked {{
    border: 1.5px solid {c['accent']}; border-radius: 5px;
    background: {c['accent']}; image: url({check_url});
}}

#bubbleRoot QLabel#overdueTitle {{ color: {c['sub']}; }}
#bubbleRoot QLabel#overdueRow {{
    color: {c['text']}; padding: 4px 6px; border-radius: 7px;
}}
#bubbleRoot QLabel#overdueRow:hover {{ background: {c['surface']}; }}

#bubbleRoot QToolButton#timerBtn {{ color: {c['accent']}; }}
#bubbleRoot QToolButton#timerPlay {{ background: transparent; }}
#bubbleRoot QToolButton#timerPlay:hover {{ background: transparent; }}
#bubbleRoot QFrame#timerCell {{
    background: {c['accent_soft']};
    border: 1.5px solid {c['accent']}; border-radius: 10px;
}}
#bubbleRoot QFrame#timerCell QLabel {{ background: transparent; }}
#bubbleRoot QLabel#timerTime {{ color: {c['accent_text']}; }}
#bubbleRoot QLabel#timerName {{ color: {c['sub']}; }}
#bubbleRoot QToolButton#timerActionBtn {{
    background: {c['surface']}; color: {c['text']};
    border: none; border-radius: 8px; padding: 4px 4px;
}}
#bubbleRoot QToolButton#timerActionBtn:hover {{ background: {c['accent_soft']}; }}
#bubbleRoot QToolButton#timerAdjBtn {{
    background: {c['surface']}; color: {c['text']};
    border: 1px solid {c['border_strong']}; border-radius: 8px;
    font-size: 15px; font-weight: bold;
}}
#bubbleRoot QToolButton#timerAdjBtn:hover {{
    background: {c['accent_soft']}; border: 1px solid {c['accent']};
}}

#bubbleRoot QFrame#dayCol {{ border: 1px solid {c['border']}; border-radius: 8px; }}
#bubbleRoot QFrame#dayCol[selected="true"] {{ border: 2px solid {c['accent']}; }}
#bubbleRoot QFrame#monthCell {{ border: 1px solid {c['border']}; border-radius: 6px; }}
#bubbleRoot QFrame#monthCell[selected="true"] {{ border: 2px solid {c['accent']}; }}
"""
