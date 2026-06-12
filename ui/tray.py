"""ui/tray.py — 시스템 트레이 아이콘과 메뉴."""
from __future__ import annotations

from PyQt6.QtGui import QAction, QBrush, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon


def _fallback_icon() -> QIcon:
    pm = QPixmap(32, 32)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QBrush(QColor("#7F77DD")))
    p.setPen(QColor("#26215C"))
    p.drawRoundedRect(3, 3, 26, 26, 8, 8)
    p.end()
    return QIcon(pm)


class Tray(QSystemTrayIcon):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self._controller = controller
        self.setIcon(_fallback_icon())
        self.setToolTip("Character TODO")

        menu = QMenu()
        a_show = QAction("캐릭터 보이기/숨기기", menu)
        a_show.triggered.connect(controller.toggle_character)
        a_set = QAction("설정", menu)
        a_set.triggered.connect(controller.open_settings)
        a_quit = QAction("종료", menu)
        a_quit.triggered.connect(controller.quit_app)
        menu.addAction(a_show)
        menu.addAction(a_set)
        menu.addSeparator()
        menu.addAction(a_quit)
        self.setContextMenu(menu)

        self.activated.connect(self._on_activated)

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._controller.toggle_character()

    def notify(self, title: str, message: str) -> None:
        self.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 5000)
