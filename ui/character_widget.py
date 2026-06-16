"""ui/character_widget.py — 바탕화면 위 캐릭터.

- 프레임리스 · 배경 투명 · 항상 위
- 드래그로 이동, 위치는 종료 시 저장 / 시작 시 복원(화면 안으로 clamp)
- 좌클릭(이동 없음): 말풍선 토글
- 우클릭: 설정 / 트레이로 최소화 / 종료
- 이미지 경로가 없거나 깨지면 기본 캐릭터를 직접 그린다
"""
from __future__ import annotations

import logging
from datetime import date

from PyQt6.QtCore import QPoint, QSize, QTimer, Qt
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QImageReader,
    QMovie,
    QPainter,
    QPixmap,
)
from PyQt6.QtWidgets import QApplication, QMenu, QWidget

from core import paths
from domain import policies
from ui.bubble.todo_item import MIME_TODO

log = logging.getLogger(__name__)

_DEFAULT_SIZE = 96
# 상황별 이미지 미설정 시 resources\ 에서 찾는 파일 베이스명(번들 폴백).
#   잠금 빌드(설정에서 변경 불가)에서도 파일만 넣으면 상황별 이미지가 적용된다.
#   default 외 상황 파일이 없으면 default 로, default 도 없으면 코드 placeholder.
_FALLBACK_BASE = {
    "default": "character_default",
    "overdue": "character_overdue",
    "delete": "character_delete",
    "idle": "character_idle",
}
_FALLBACK_EXTS = (".png", ".gif")  # 우선순위 순(둘 다 있으면 png)

# 상황 → 설정 키. 'default' 는 기본 이미지, 나머지는 없으면 default 로 폴백.
_IMAGE_KEYS = {
    "default": policies.KEY_IMAGE_PATH,
    "overdue": policies.KEY_IMAGE_OVERDUE,
    "delete": policies.KEY_IMAGE_DELETE,
    "idle": policies.KEY_IMAGE_IDLE,
}


def _bundled_fallback(situation: str) -> str | None:
    """resources\\ 에서 상황별 폴백 이미지 경로를 찾는다(png→gif 순). 없으면 None."""
    base = _FALLBACK_BASE[situation]
    res_dir = paths.resource_dir()
    for ext in _FALLBACK_EXTS:
        cand = res_dir / (base + ext)
        if cand.exists():
            return str(cand)
    return None


class CharacterWidget(QWidget):
    def __init__(self, service, events, settings_repo, bubble, controller, parent=None):
        super().__init__(parent)
        self._service = service
        self._events = events
        self._settings = settings_repo
        self._bubble = bubble
        self._controller = controller

        self._pixmaps: dict[str, QPixmap | None] = {}
        self._movies: dict[str, QMovie | None] = {}  # 애니메이션 GIF 상황별
        self._situation = "default"   # 'default' | 'overdue' | 'idle' | 'delete'
        self._overdue = False
        self._idle = False
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

        self._load_images()
        self._refresh_situation()
        self._events.character_image_changed.connect(self._on_image_changed)
        self._events.todos_changed.connect(lambda _iso: self._refresh_situation())

        # 비활성 상태는 할일 변경 없이도 시간 경과로 바뀌므로 1분마다 재확인
        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(60_000)
        self._idle_timer.timeout.connect(self._refresh_situation)
        self._idle_timer.start()

        self._restore_position()

    # ── 이미지 ──────────────────────────────────────────────
    def _load_images(self) -> None:
        """상황별 이미지를 모두 읽어둔다. GIF 는 QMovie(애니메이션), 그 외는 QPixmap.
        미설정/없음이면 None → 그릴 때 default 로 폴백. 위젯 크기는 기본 이미지 기준 고정."""
        for m in self._movies.values():  # 재로드 전 기존 무비 정지
            if m is not None:
                m.stop()
        self._pixmaps = {}
        self._movies = {}
        for sit, key in _IMAGE_KEYS.items():
            path = self._settings.get(key) or _bundled_fallback(sit)
            pm, movie = self._load_source(path)
            if movie is not None:
                movie.frameChanged.connect(self.update)
            self._pixmaps[sit] = pm
            self._movies[sit] = movie

        size = self._source_size("default") or QSize(_DEFAULT_SIZE, _DEFAULT_SIZE)
        self.resize(size)
        self._update_active_movie()
        self.update()

    def _load_source(self, path: str | None) -> tuple[QPixmap | None, QMovie | None]:
        """경로 → (pixmap, movie). 애니메이션 GIF 면 movie, 그 외 정적 pixmap."""
        if not path:
            return None, None
        box = _DEFAULT_SIZE * 2
        if path.lower().endswith(".gif"):
            movie = QMovie(path)
            if movie.isValid():
                movie.setCacheMode(QMovie.CacheMode.CacheAll)
                native = QImageReader(path).size()
                if native.isValid() and (native.width() > box or native.height() > box):
                    movie.setScaledSize(native.scaled(box, box, Qt.AspectRatioMode.KeepAspectRatio))
                return None, movie
        pm = QPixmap(path)
        if pm.isNull():
            return None, None
        pm = pm.scaled(box, box, Qt.AspectRatioMode.KeepAspectRatio,
                       Qt.TransformationMode.SmoothTransformation)
        return pm, None

    def _resolved_situation(self) -> str:
        """현재 상황(소스 없으면 default 로 폴백)."""
        sit = self._situation
        if self._pixmaps.get(sit) is None and self._movies.get(sit) is None:
            return "default"
        return sit

    def _source_size(self, sit: str) -> QSize | None:
        pm = self._pixmaps.get(sit)
        if pm is not None:
            return pm.size()
        movie = self._movies.get(sit)
        if movie is not None:
            s = movie.scaledSize()
            if s.isValid() and not s.isEmpty():
                return s
            movie.jumpToFrame(0)
            return movie.currentPixmap().size()
        return None

    def _update_active_movie(self) -> None:
        """현재 상황의 무비만 재생하고 나머지는 멈춘다(불필요한 CPU 방지)."""
        active = self._movies.get(self._resolved_situation())
        for m in self._movies.values():
            if m is None:
                continue
            if m is active:
                if m.state() != QMovie.MovieState.Running:
                    m.start()
            elif m.state() == QMovie.MovieState.Running:
                m.stop()

    def _set_situation(self, sit: str) -> None:
        if sit != self._situation:
            self._situation = sit
            self._update_active_movie()
            self.update()

    def _refresh_situation(self) -> None:
        """overdue · idle 여부를 재계산해 (드래그 중이 아니면) 상황 반영.
        우선순위: delete > overdue > idle > default"""
        today = date.today().isoformat()
        self._overdue = self._service.has_overdue(today)
        hours = int(self._settings.get(policies.KEY_IDLE_HOURS, "0") or "0")
        self._idle = self._service.is_idle(hours)
        if self._situation != "delete":
            if self._overdue:
                self._set_situation("overdue")
            elif self._idle:
                self._set_situation("idle")
            else:
                self._set_situation("default")

    def _on_image_changed(self, _path: str) -> None:
        self._load_images()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        sit = self._resolved_situation()
        movie = self._movies.get(sit)
        pm = movie.currentPixmap() if movie is not None else self._pixmaps.get(sit)
        if pm is not None and not pm.isNull():
            x = (self.width() - pm.width()) // 2
            y = (self.height() - pm.height()) // 2
            p.drawPixmap(x, y, pm)
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
            self._set_situation("delete")              # 삭제 상황 이미지로 전환
            e.accept()

    def dragMoveEvent(self, e) -> None:
        if e.mimeData().hasFormat(MIME_TODO):
            e.setDropAction(Qt.DropAction.CopyAction)
            e.accept()

    def dragLeaveEvent(self, _e) -> None:
        self._restore_situation()

    def dropEvent(self, e) -> None:
        raw = bytes(e.mimeData().data(MIME_TODO)).decode()
        tid_s, _src = raw.split("|", 1)
        self._service.remove(int(tid_s))
        e.setDropAction(Qt.DropAction.CopyAction)
        e.accept()
        self._restore_situation()  # 삭제 후 overdue/default 로 복귀

    def _restore_situation(self) -> None:
        if self._overdue:
            self._set_situation("overdue")
        elif self._idle:
            self._set_situation("idle")
        else:
            self._set_situation("default")

    # ── 우클릭 메뉴 ─────────────────────────────────────────
    def _show_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        a_set = QAction("설정", self)
        a_set.triggered.connect(self._controller.open_settings)

        a_overdue = QAction("밀린할일 표시", self)
        a_overdue.setCheckable(True)
        a_overdue.setChecked(
            (self._settings.get(policies.KEY_OVERDUE_PANEL, "1") or "1") == "1"
        )
        a_overdue.toggled.connect(self._toggle_overdue_panel)

        a_min = QAction("트레이로 최소화", self)
        a_min.triggered.connect(self._controller.minimize_to_tray)
        a_quit = QAction("종료", self)
        a_quit.triggered.connect(self._controller.quit_app)
        menu.addAction(a_set)
        menu.addAction(a_overdue)
        menu.addAction(a_min)
        menu.addSeparator()
        menu.addAction(a_quit)
        menu.exec(global_pos)

    def _toggle_overdue_panel(self, on: bool) -> None:
        self._settings.set(policies.KEY_OVERDUE_PANEL, "1" if on else "0")
        self._events.overdue_panel_changed.emit(on)

    def closeEvent(self, e) -> None:
        self._save_position()
        super().closeEvent(e)
