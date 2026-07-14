"""ui/timer_setup_dialog.py — 타이머 설정 다이얼로그(시/분/초).

기존 QInputDialog 는 네이티브 제목표시줄이 있는 창이라 열릴 때 화면에 잠깐
'실행창'처럼 깜빡였다. 여기서는 말풍선과 같은 프레임리스·투명·둥근 카드로 만들어
깜빡임을 없애고 디자인을 입힌다. exec() 가 확인이면 총 '초'를 result_seconds 로 돌려준다.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from domain import policies
from ui import theme
from ui.qt_helpers import make_overlay_window

_DEFAULT_MIN = 25  # 기본 25분


class TimerSetupDialog(QDialog):
    """시·분·초 입력 + 확인/취소. result_seconds 에 총 초가 담긴다(취소 시 None)."""

    def __init__(self, content: str, settings_repo, replacing: bool = False, parent=None):
        super().__init__(parent)
        self._settings = settings_repo
        self.result_seconds: int | None = None
        self.auto_complete: bool = False  # 확인 시 '완료 시 자동 완료' 선택값
        self._drag_offset: QPoint | None = None

        make_overlay_window(self, dialog=True)
        self.setModal(True)

        self._root = QFrame(self)
        self._root.setObjectName("bubbleRoot")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)  # 그림자/여백
        outer.addWidget(self._root)

        v = QVBoxLayout(self._root)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)

        title = QLabel("타이머 설정")
        title.setObjectName("bubbleTitle")
        f = title.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 2)
        title.setFont(f)
        v.addWidget(title)

        # 대상 할일명(길면 말줄임)
        name = QLabel()
        name.setObjectName("subText")
        fm = QFontMetrics(name.font())
        name.setText(fm.elidedText(content, Qt.TextElideMode.ElideRight, 230))
        v.addWidget(name)

        if replacing:
            warn = QLabel("기존 타이머는 초기화됩니다.")
            warn.setObjectName("subText")
            v.addWidget(warn)

        # 시 / 분 / 초 스핀박스
        self._h = self._make_spin(0, 23, 0, "시")
        self._m = self._make_spin(0, 59, _DEFAULT_MIN, "분")
        self._s = self._make_spin(0, 59, 0, "초")

        spins = QHBoxLayout()
        spins.setSpacing(6)
        for i, (spin, suffix) in enumerate(
            ((self._h, "시"), (self._m, "분"), (self._s, "초"))
        ):
            if i > 0:  # 박스 사이 콜론(스핀박스 높이에 맞춰 세로 중앙 정렬)
                colon = QLabel(":")
                colon.setObjectName("timerColon")
                colon.setFixedHeight(52)
                colon.setAlignment(Qt.AlignmentFlag.AlignCenter)
                spins.addWidget(colon, 0, Qt.AlignmentFlag.AlignTop)
            cell = QVBoxLayout()
            cell.setSpacing(2)
            lab = QLabel(suffix)
            lab.setObjectName("subText")
            lab.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            cell.addWidget(spin)
            cell.addWidget(lab)
            box = QWidget()
            box.setLayout(cell)
            spins.addWidget(box)
        v.addLayout(spins)

        # 완료 시 자동 완료(마지막 선택을 기억)
        self._auto_cb = QCheckBox("완료 시 할일 자동 완료")
        self._auto_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self._auto_cb.setChecked(
            settings_repo.get_bool(policies.KEY_TIMER_AUTO_COMPLETE, True)
            if settings_repo else True
        )
        v.addWidget(self._auto_cb)

        # 버튼
        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.addStretch(1)
        cancel = QPushButton("취소")
        cancel.setObjectName("dlgBtn")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        ok = QPushButton("시작")
        ok.setObjectName("dlgBtnPrimary")
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        v.addLayout(btns)

        self._apply_theme()
        self.adjustSize()
        self._center_on_parent()

    def _make_spin(self, lo: int, hi: int, val: int, _suffix: str) -> QSpinBox:
        sp = QSpinBox()
        sp.setRange(lo, hi)
        sp.setValue(val)
        sp.setWrapping(True)
        sp.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sp.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)
        sp.setFixedSize(90, 52)
        f = sp.font()
        f.setPointSize(f.pointSize() + 3)
        f.setBold(True)
        sp.setFont(f)
        return sp

    def _accept(self) -> None:
        total = self._h.value() * 3600 + self._m.value() * 60 + self._s.value()
        if total <= 0:
            return  # 0초 타이머는 무시(버튼만 비활성 대신 조용히 무시)
        self.result_seconds = total
        self.auto_complete = self._auto_cb.isChecked()
        if self._settings is not None:  # 마지막 선택 기억
            self._settings.set_bool(policies.KEY_TIMER_AUTO_COMPLETE, self.auto_complete)
        self.accept()

    # ── 스타일(말풍선 테마 + 다이얼로그 전용 버튼/스핀) ─────────
    def _apply_theme(self) -> None:
        mode = self._settings.get(policies.KEY_THEME, "system") if self._settings else "system"
        c = theme.palette(mode)
        # 화살표: 평소 회색(sub), 마우스오버 시 보라(accent)
        up_n = theme.arrow_icon_path("up", c["sub"])
        up_h = theme.arrow_icon_path("up", c["accent"])
        dn_n = theme.arrow_icon_path("down", c["sub"])
        dn_h = theme.arrow_icon_path("down", c["accent"])
        self.setStyleSheet(
            theme.qss(mode)
            + f"""
            #bubbleRoot QSpinBox {{
                background: {c['surface']}; color: {c['text']};
                border: 1.5px solid {c['border_strong']}; border-radius: 10px;
                padding: 2px 16px 2px 4px;
            }}
            #bubbleRoot QSpinBox:focus {{ border: 2px solid {c['accent']}; }}
            /* 화살표: 박스(테두리/배경) 없이 삼각형만. 색은 hover 시 회색→보라로 변동 */
            #bubbleRoot QSpinBox::up-button {{
                subcontrol-origin: border; subcontrol-position: top right;
                width: 16px; border: none; background: transparent;
            }}
            #bubbleRoot QSpinBox::down-button {{
                subcontrol-origin: border; subcontrol-position: bottom right;
                width: 16px; border: none; background: transparent;
            }}
            #bubbleRoot QSpinBox::up-arrow {{
                image: url({up_n}); width: 10px; height: 10px;
            }}
            #bubbleRoot QSpinBox::up-arrow:hover {{ image: url({up_h}); }}
            #bubbleRoot QSpinBox::down-arrow {{
                image: url({dn_n}); width: 10px; height: 10px;
            }}
            #bubbleRoot QSpinBox::down-arrow:hover {{ image: url({dn_h}); }}
            #bubbleRoot QLabel#timerColon {{
                color: {c['sub']}; font-size: 22px; font-weight: bold;
            }}
            #bubbleRoot QCheckBox {{ color: {c['sub']}; spacing: 6px; }}
            #bubbleRoot QPushButton#dlgBtn {{
                background: {c['surface']}; color: {c['text']};
                border: none; border-radius: 10px; padding: 7px 16px;
            }}
            #bubbleRoot QPushButton#dlgBtn:hover {{ background: {c['accent_soft']}; }}
            #bubbleRoot QPushButton#dlgBtnPrimary {{
                background: {c['accent']}; color: #FFFFFF;
                border: none; border-radius: 10px; padding: 7px 18px; font-weight: bold;
            }}
            #bubbleRoot QPushButton#dlgBtnPrimary:hover {{ background: {c['accent_text']}; }}
            """
        )

    # ── 부모(또는 화면) 중앙에 배치(표시 전에 호출 → 좌상단 깜빡임 방지) ──
    def _center_on_parent(self) -> None:
        from PySide6.QtWidgets import QApplication

        par = self.parent()
        if par is not None and par.isVisible():
            ref = par.frameGeometry()
        else:
            ref = QApplication.primaryScreen().availableGeometry()
        c = ref.center()
        self.move(c.x() - self.width() // 2, c.y() - self.height() // 2)

    # ── 프레임리스 창 드래그 이동 ───────────────────────────
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e) -> None:
        if self._drag_offset is not None:
            self.move(e.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, _e) -> None:
        self._drag_offset = None
