"""ui/todo_count_bubble.py — 캐릭터 옆에 떠 있는 작은 '할일 n개' 풍선.

그리드를 모두 숨긴(최소화) 상태에서 오늘 미완료 할일이 있을 때 캐릭터 위(공간 없으면
아래)에 표시된다. 타이머 풍선이 떠 있으면 타이머가 우선이라 이 풍선은 숨긴다(#2-b).
  - '할일 N개' 텍스트(N = 오늘 미완료 수)
  - 클릭하면 그리드를 다시 연다(clicked 시그널)
외형(둥근 몸체+꼬리·배치·테마 골격)은 FloatingBubble 베이스를 TimerBubble 과 공유한다.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout

from domain import policies
from ui import theme
from ui.floating_bubble import FloatingBubble


class TodoCountBubble(FloatingBubble):
    clicked = pyqtSignal()

    def __init__(self, settings_repo, parent=None):
        super().__init__(settings_repo, parent)
        self.setToolTip("클릭하면 할 일 열기")

        v = QVBoxLayout(self._root)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(0)

        self._label = QLabel("할일 0개")
        self._label.setObjectName("tcCount")
        self._label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        f = self._label.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 2)
        self._label.setFont(f)
        v.addWidget(self._label)

        self.apply_theme()

    # ── 스타일(타이머 풍선과 동일 팔레트) ──────────────────────
    def apply_theme(self) -> None:
        c = theme.palette(self._settings.get(policies.KEY_THEME, "system"))
        self.setStyleSheet(
            self._chrome_theme()
            + f"#bubbleRootMini QLabel#tcCount {{ color: {c['accent_text']}; }}"
        )
        self.update()

    # ── 갱신 ────────────────────────────────────────────────
    def set_count(self, count: int) -> None:
        self._label.setText(f"할일 {count}개")

    # ── 마우스: 클릭=그리드 열기 ────────────────────────────
    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
