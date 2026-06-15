"""ui/character_widget.py — 바탕화면 위 캐릭터.

- 프레임리스 · 배경 투명 · 항상 위
- 드래그로 이동, 위치는 종료 시 저장 / 시작 시 복원(화면 안으로 clamp)
- 좌클릭(이동 없음): 말풍선 토글
- 우클릭: 설정 / 트레이로 최소화 / 종료
- 이미지 경로가 없거나 깨지면 기본 캐릭터를 직접 그린다
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QAction, QBrush, QColor, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from domain import policies
from ui.bubble.todo_item import MIME_TODO

log = logging.getLogger(__name__)

_DEFAULT_SIZE = 96


class CharacterWidget(QWidget):
    def __init__(self, service, events, settings_repo, bubble, controller, parent=None):
        super().__init__(parent)
        self._service = service
        self._events = events
        self._settings = settings_repo
        self._bubble = bubble
        self._controller = controller

        self._pixmap: QPixmap | None = None
        self._press_global: QPoint | None = None
        self._press_frame: QPoint | None = None
        self._moved = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAcceptDrops(True)  # 할일을 캐릭터로 끌어다 놓으면 삭제(휴지통)

        self._load_image()
        self._events.character_image_changed.connect(self._on_image_changed)
        self._restore_position()

    # ── 이미지 ──────────────────────────────────────────────
    def _load_image(self) -> None:
        path = self._settings.get(policies.KEY_IMAGE_PATH)
        pm = QPixmap(path) if path else QPixmap()
        if not pm.isNull():
            self._pixmap = pm.scaled(
                _DEFAULT_SIZE * 2,
                _DEFAULT_SIZE * 2,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.resize(self._pixmap.size())
        else:
            self._pixmap = None
            self.resize(_DEFAULT_SIZE, _DEFAULT_SIZE)
        self.update()

    def _on_image_changed(self, _path: str) -> None:
        self._load_image()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._pixmap is not None:
            p.drawPixmap(0, 0, self._pixmap)
        else:
            self._paint_placeholder(p)

    def _paint_placeholder(self, p: QPainter) -> None:
        w, h = self.width(), self.height()
        p.setBrush(QBrush(QColor("#7F77DD")))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(8, 8, w - 16, h - 16, 24, 24)
        p.setBrush(QBrush(QColor("white")))
        p.drawEllipse(int(w * 0.34) - 6, int(h * 0.42) - 6, 12, 12)
        p.drawEllipse(int(w * 0.62) - 6, int(h * 0.42) - 6, 12, 12)
        p.setBrush(QBrush(QColor("#26215C")))
        p.drawEllipse(int(w * 0.34) - 3, int(h * 0.42) - 3, 6, 6)
        p.drawEllipse(int(w * 0.62) - 3, int(h * 0.42) - 3, 6, 6)

    # ── 위치 저장/복원 ──────────────────────────────────────
    def _restore_position(self) -> None:
        x = self._settings.get_int(policies.KEY_LAST_X, -10_000)
        y = self._settings.get_int(policies.KEY_LAST_Y, -10_000)
        if x == -10_000:
            scr = QApplication.primaryScreen().availableGeometry()
            x = scr.right() - self.width() - 40
            y = scr.bottom() - self.height() - 60
        self.move(self._clamp(QPoint(x, y)))

    def _clamp(self, pt: QPoint) -> QPoint:
        scr = self._screen_for(pt).availableGeometry()
        x = max(scr.left(), min(pt.x(), scr.right() - self.width()))
        y = max(scr.top(), min(pt.y(), scr.bottom() - self.height()))
        return QPoint(x, y)

    def _screen_for(self, pt: QPoint):
        s = QApplication.screenAt(pt)
        return s or QApplication.primaryScreen()

    def _save_position(self) -> None:
        self._settings.set(policies.KEY_LAST_X, self.x())
        self._settings.set(policies.KEY_LAST_Y, self.y())

    # ── 마우스 ──────────────────────────────────────────────
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_global = e.globalPosition().toPoint()
            self._press_frame = self.frameGeometry().topLeft()
            self._moved = False
        elif e.button() == Qt.MouseButton.RightButton:
            self._show_menu(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e) -> None:
        if self._press_global is None:
            return
        delta = e.globalPosition().toPoint() - self._press_global
        if delta.manhattanLength() >= QApplication.startDragDistance():
            self._moved = True
        self.move(self._clamp(self._press_frame + delta))
        # 말풍선이 열려 있으면 같이 따라 이동 (뷰 재구성 없이 위치만)
        if self._bubble.isVisible():
            scr = self._screen_for(self.frameGeometry().center()).availableGeometry()
            self._bubble.reposition_for_character(self.frameGeometry(), scr)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self._moved:
            self._save_position()
        else:
            self._toggle_bubble()
        self._press_global = None

    def _toggle_bubble(self) -> None:
        if self._bubble.isVisible():
            self._bubble.hide()
        else:
            scr = self._screen_for(self.frameGeometry().center()).availableGeometry()
            self._bubble.show_for_character(self.frameGeometry(), scr)

    # ── 휴지통(할일 드롭=삭제) ──────────────────────────────
    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasFormat(MIME_TODO):
            e.setDropAction(Qt.DropAction.CopyAction)  # Copy = 삭제(휴지통) 의미
            e.accept()

    def dragMoveEvent(self, e) -> None:
        if e.mimeData().hasFormat(MIME_TODO):
            e.setDropAction(Qt.DropAction.CopyAction)
            e.accept()

    def dropEvent(self, e) -> None:
        raw = bytes(e.mimeData().data(MIME_TODO)).decode()
        tid_s, _src = raw.split("|", 1)
        self._service.remove(int(tid_s))
        e.setDropAction(Qt.DropAction.CopyAction)
        e.accept()

    # ── 우클릭 메뉴 ─────────────────────────────────────────
    def _show_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        a_set = QAction("설정", self)
        a_set.triggered.connect(self._controller.open_settings)
        a_min = QAction("트레이로 최소화", self)
        a_min.triggered.connect(self._controller.minimize_to_tray)
        a_quit = QAction("종료", self)
        a_quit.triggered.connect(self._controller.quit_app)
        menu.addAction(a_set)
        menu.addAction(a_min)
        menu.addSeparator()
        menu.addAction(a_quit)
        menu.exec(global_pos)

    def closeEvent(self, e) -> None:
        self._save_position()
        super().closeEvent(e)
