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
from ui.qt_helpers import make_overlay_window

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
    "done": "character_done",
    "work": "character_work",
    "pause": "character_pause",
    "timer_done": "character_timer_done",
    "open": "character_open",
    "closed": "character_closed",
    "add": "character_add",
}
_REACTION_MS = 3000       # 완료(done) 리액션 표시 시간
_TIMER_DONE_MS = 3000     # 타이머 만료(timer_done) 리액션 표시 시간
_GRID_REACT_MS = 1000     # 그리드 열기(open)/닫기(closed) 리액션 표시 시간
_FALLBACK_EXTS = (".png", ".gif")  # 우선순위 순(둘 다 있으면 png)

# 상황 → 설정 키. 'default' 는 기본 이미지, 나머지는 없으면 default 로 폴백.
_IMAGE_KEYS = {
    "default": policies.KEY_IMAGE_PATH,
    "overdue": policies.KEY_IMAGE_OVERDUE,
    "delete": policies.KEY_IMAGE_DELETE,
    "idle": policies.KEY_IMAGE_IDLE,
    "done": policies.KEY_IMAGE_DONE,
    "work": policies.KEY_IMAGE_WORK,
    "pause": policies.KEY_IMAGE_PAUSE,
    "timer_done": policies.KEY_IMAGE_TIMER_DONE,
    "open": policies.KEY_IMAGE_OPEN,
    "closed": policies.KEY_IMAGE_CLOSED,
    "add": policies.KEY_IMAGE_ADD,
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
    def __init__(self, service, events, settings_repo, bubble, controller,
                 timer_service=None, timer_bubble=None, todo_bubble=None, parent=None):
        super().__init__(parent)
        self._service = service
        self._events = events
        self._settings = settings_repo
        self._bubble = bubble
        self._controller = controller
        self._timer = timer_service
        self._timer_bubble = timer_bubble
        self._todo_bubble = todo_bubble

        self._pixmaps: dict[str, QPixmap | None] = {}
        self._movies: dict[str, QMovie | None] = {}  # 애니메이션 GIF 상황별
        self._situation = "default"   # default|overdue|idle|done|work|pause|timer_done|delete
        self._overdue = False
        self._idle = False
        self._working = False         # 타이머 실행 중(정지 포함)
        self._paused = False          # 타이머 정지(일시정지) 중
        self._reacting = False        # 완료/타이머완료 리액션 표시 중
        self._skip_open_reaction = False  # 우클릭 메뉴 등 리액션 없이 그리드 여는 경우
        self._react_sit = ""          # 리액션 상황('done'|'timer_done')
        self._press_global: QPoint | None = None
        self._press_frame: QPoint | None = None
        self._moved = False
        self._undo_available = False   # 되돌리기(삭제 취소) 가능 여부 — 우클릭 메뉴에서 사용

        make_overlay_window(self)
        self.setAcceptDrops(True)  # 할일을 캐릭터로 끌어다 놓으면 삭제(휴지통)

        self._load_images()
        self._refresh_situation()
        self._events.character_image_changed.connect(self._on_image_changed)
        self._events.character_scale_changed.connect(self._load_images)
        self._events.todos_changed.connect(lambda _iso: self._refresh_situation())
        self._events.todos_changed.connect(lambda _iso: self._sync_todo_count_bubble())
        self._events.todo_completed.connect(self._on_todo_completed)
        self._events.todo_added.connect(self._on_todo_added)
        self._events.delete_undo_available.connect(self._on_undo_available)
        if self._timer is not None:
            self._events.timer_started.connect(self._on_timer_started)
            self._events.timer_stopped.connect(self._on_timer_stopped)
            self._events.timer_finished.connect(self._on_timer_finished)
            self._events.timer_paused.connect(self._on_timer_paused)
            self._events.timer_resumed.connect(self._on_timer_resumed)
        if self._timer_bubble is not None:
            self._timer_bubble.clicked.connect(self._on_timer_bubble_clicked)
        if self._todo_bubble is not None:
            self._todo_bubble.clicked.connect(self._on_todo_bubble_clicked)
            self._events.todo_count_bubble_changed.connect(
                lambda _on: self._sync_todo_count_bubble()
            )
        # 그리드 열림/닫힘 → open/closed 리액션(3초) 후 기본 이미지 복귀
        self._events.bubble_opened.connect(self._on_bubble_opened)
        self._events.bubble_closed.connect(self._on_bubble_closed)

        # 비활성 상태는 할일 변경 없이도 시간 경과로 바뀌므로 1분마다 재확인
        self._idle_timer = QTimer(self)
        self._idle_timer.setInterval(60_000)
        self._idle_timer.timeout.connect(self._refresh_situation)
        self._idle_timer.start()

        # 완료 리액션: 잠깐 done 이미지 후 복귀
        self._react_timer = QTimer(self)
        self._react_timer.setSingleShot(True)
        self._react_timer.timeout.connect(self._end_reaction)

        self._restore_position()

    # ── 이미지 ──────────────────────────────────────────────
    def _box(self) -> int:
        """크기 설정(%)을 반영한 이미지 바운딩 박스 한 변(px)."""
        pct = int(self._settings.get(policies.KEY_CHAR_SCALE, "100") or "100")
        pct = max(50, min(200, pct))
        return int(_DEFAULT_SIZE * 2 * pct / 100)

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
        if self.isVisible():  # 크기 변경 reload 시 화면 밖으로 나가지 않게
            self.move(self._clamp(self.pos()))
        self._update_active_movie()
        self.update()

    def _load_source(self, path: str | None) -> tuple[QPixmap | None, QMovie | None]:
        """경로 → (pixmap, movie). 애니메이션 GIF 면 movie, 그 외 정적 pixmap."""
        if not path:
            return None, None
        box = self._box()
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
        """overdue · work · idle 여부를 재계산해 상황 반영.
        우선순위: delete > work(타이머) > timer_done/done(리액션) > overdue > idle > default
        — 타이머가 최우선이라 타이머가 도는 동안엔 overdue/완료 리액션보다 work 가 이긴다."""
        today = date.today().isoformat()
        self._overdue = self._service.has_overdue(today)
        hours = int(self._settings.get(policies.KEY_IDLE_HOURS, "0") or "0")
        self._idle = self._service.is_idle(hours)
        if self._situation == "delete" or self._reacting:
            return  # 드래그/리액션 중에는 덮어쓰지 않음
        self._set_situation(self._priority_situation())

    def _priority_situation(self) -> str:
        """현재 플래그 기준 기본 상황을 우선순위대로 결정:
        work/pause(타이머) > overdue > idle > default.
        delete·리액션 등 일시 상태는 호출 측에서 가드한다."""
        if self._working:
            return "pause" if self._paused else "work"
        if self._overdue:
            return "overdue"
        if self._idle:
            return "idle"
        return "default"

    def _has_image(self, sit: str) -> bool:
        return self._pixmaps.get(sit) is not None or self._movies.get(sit) is not None

    def _start_reaction(self, sit: str, ms: int) -> None:
        """sit 이미지가 있으면 ms 동안 보여주고 복귀. 없으면 리액션 생략."""
        if not self._has_image(sit):
            self._restore_situation()
            return
        self._reacting = True
        self._react_sit = sit
        self._set_situation(sit)
        self._react_timer.start(ms)

    def _on_todo_completed(self) -> None:
        """완료 체크 순간: done 이미지를 잠깐. 단, 타이머가 최우선이라 타이머 진행 중엔 생략."""
        if self._working:
            return  # 타이머 중에는 work 이미지를 유지(타이머 최우선)
        if self._reacting and self._react_sit == "timer_done":
            return  # timer_done 우선
        self._start_reaction("done", _REACTION_MS)

    def _on_todo_added(self) -> None:
        """할일 추가 순간: add 이미지를 잠깐. 타이머 진행 중이거나 done 리액션 중엔 생략."""
        if self._working:
            return
        if self._reacting:
            return
        self._start_reaction("add", _REACTION_MS)

    def _end_reaction(self) -> None:
        self._reacting = False
        if self._situation == self._react_sit:
            self._restore_situation()
        self._react_sit = ""

    # ── 타이머 ──────────────────────────────────────────────
    def _on_timer_started(self, _todo_id: int) -> None:
        self._working = True
        self._paused = False
        if not self._reacting and self._situation != "delete":
            self._restore_situation()  # work 로 전환(우선순위 반영)
        self._sync_timer_bubble()

    def _on_timer_stopped(self) -> None:
        self._working = False
        self._paused = False
        if not self._reacting and self._situation != "delete":
            self._restore_situation()
        self._sync_timer_bubble()

    def _on_timer_finished(self, _todo_id: int) -> None:
        self._working = False
        self._paused = False
        self._start_reaction("timer_done", _TIMER_DONE_MS)
        self._sync_timer_bubble()

    def _on_timer_paused(self, _todo_id: int) -> None:
        self._paused = True
        if not self._reacting and self._situation != "delete":
            self._restore_situation()  # pause 이미지로 전환

    def _on_timer_resumed(self, _todo_id: int) -> None:
        self._paused = False
        if not self._reacting and self._situation != "delete":
            self._restore_situation()  # work 이미지로 복귀

    def _on_bubble_opened(self) -> None:
        """말풍선(그리드)이 열렸을 때: open 이미지를 3초 표시 후 기본 이미지 복귀.
        타이머 진행 중(정지 포함)이거나 우클릭 메뉴 경유 시엔 현재 이미지를 유지한다."""
        if not self._working and not self._skip_open_reaction:
            self._start_reaction("open", _GRID_REACT_MS)
        self._skip_open_reaction = False
        self._sync_todo_count_bubble()  # 그리드 열림 → '할일 n개' 풍선 숨김

    def _on_bubble_closed(self) -> None:
        """말풍선(그리드)이 닫혔을 때: 타이머 풍선 동기화 + 상황 갱신.
        캐릭터 클릭 닫기는 이미 toggle_bubble 에서 closed 리액션이 시작됐으므로
        _refresh_situation 은 _reacting=True 중에는 자동으로 무시된다."""
        self._sync_timer_bubble()
        self._refresh_situation()

    def _on_timer_bubble_clicked(self) -> None:
        """타이머 풍선 클릭: (최소화 상태면 복원하고) 말풍선 열기."""
        self._controller.show_from_timer_bubble()

    def _on_todo_bubble_clicked(self) -> None:
        """'할일 n개' 풍선 클릭: 그리드를 다시 연다(캐릭터 클릭과 동일)."""
        self.toggle_bubble()

    def _today_incomplete_count(self) -> int:
        today = date.today().isoformat()
        return sum(1 for t in self._service.list_for_date(today) if not t.completed)

    def _sync_todo_count_bubble(self) -> None:
        """그리드가 모두 숨겨진(최소화) 상태에서 오늘 미완료 할일이 있으면 '할일 n개'
        풍선을 캐릭터 옆에 띄운다. 단, 타이머 풍선이 떠 있으면 타이머 우선이라 숨긴다(#2)."""
        tb = self._todo_bubble
        if tb is None:
            return
        on = self._settings.get_bool(policies.KEY_TODO_COUNT_BUBBLE, True)
        timer_showing = (
            self._timer_bubble is not None and self._timer_bubble.isVisible()
        )
        grids_hidden = (
            self.isVisible()
            and not self._bubble.isVisible()
            and not self._bubble.any_panel_visible()
        )
        count = self._today_incomplete_count() if (on and grids_hidden) else 0
        if on and grids_hidden and not timer_showing and count > 0:
            tb.set_count(count)
            scr = self.available_geometry()
            tb.place_for(self.frameGeometry(), scr)
            tb.show()
            tb.raise_()
        else:
            tb.hide()

    def sync_timer_bubble(self, standalone: bool = False) -> None:
        """타이머 풍선 표시 동기화(외부=컨트롤러용 공개 래퍼).
        standalone=True 면 캐릭터가 숨겨진 트레이 최소화 중에도 풍선만 띄운다."""
        self._sync_timer_bubble(standalone)

    def _sync_timer_bubble(self, standalone: bool = False) -> None:
        """말풍선이 닫혀 있고 타이머가 도는 동안만 캐릭터 옆 타이머 풍선 표시."""
        tb = self._timer_bubble
        if tb is None:
            return
        active = self._timer is not None and self._timer.is_active()
        # 타이머 패널이 이미 화면에 떠 있으면(✕로 말풍선만 닫고 패널 유지) 풍선은 중복이라 띄우지 않는다.
        panel_shown = self._bubble.timer_panel_visible()
        visible_ok = (
            standalone
            or (self.isVisible() and not self._bubble.isVisible() and not panel_shown)
        )
        if active and visible_ok:
            # 캐릭터가 내려간 단독 표시(standalone)일 때만 드래그 이동 허용.
            tb.set_draggable(standalone)
            snap = self._timer.snapshot()
            if snap is not None:
                tb.set_content(snap.content, snap.remaining_seconds)
            scr = self.available_geometry()
            tb.place_for(self.frameGeometry(), scr)
            tb.show()
            tb.raise_()
        else:
            tb.hide()
        # 타이머 풍선 상태가 정해진 뒤 '할일 n개' 풍선을 동기화(타이머 우선).
        self._sync_todo_count_bubble()

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

    def available_geometry(self):
        """캐릭터가 놓인 화면의 가용 영역(작업표시줄 제외). 컨트롤러/내부 공용."""
        return self._screen_for(self.frameGeometry().center()).availableGeometry()

    def save_position(self) -> None:
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
            scr = self.available_geometry()
            self._bubble.reposition_for_character(self.frameGeometry(), scr)
        else:
            # 닫힌 상태에서 드래그: ✕로 남긴 패널(캐릭터 상단)과 타이머 풍선이 함께 따라온다.
            scr = self.available_geometry()
            self._bubble.reposition_detached_panels(self.frameGeometry(), scr)
            self._sync_timer_bubble()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self._moved:
            self.save_position()
        else:
            self.toggle_bubble()
        self._press_global = None

    def toggle_bubble(self) -> None:
        """캐릭터 클릭 = 그리드 전체 토글.
        - 무엇이든 떠 있으면(목록/밀린할일/타이머) 전부 숨김(최소화, 설정 유지)
        - 모두 숨겨져 있으면 '켜진' 그리드만 다시 표시(꺼진 그리드는 안 나옴)
        - 모든 그리드가 꺼져 있으면 전부 켠다(escape)."""
        if self._bubble.isVisible() or self._bubble.any_panel_visible():
            if not self._working:  # 타이머 진행 중(정지 포함)이면 work/pause 이미지 유지
                self._start_reaction("closed", _GRID_REACT_MS)  # 클릭 즉시 closed 이미지
            self._bubble.minimize_all()
        else:
            self._restore_grids()

    def restore_on_startup(self) -> None:
        """앱 시작 시 이전 종료 시점의 그리드 상태 복원(open 리액션 없음).
        KEY_LIST_SHOW 가 한 번도 저장된 적 없으면(완전 첫 실행) 세 그리드 모두 켠다."""
        s = self._settings
        if s.get(policies.KEY_LIST_SHOW) is None:
            s.set_bool(policies.KEY_LIST_SHOW, True)
            s.set_bool(policies.KEY_OVERDUE_PANEL, True)
            s.set_bool(policies.KEY_TIMER_PANEL, True)
        list_on = s.get_bool(policies.KEY_LIST_SHOW, False)
        overdue_on = s.get_bool(policies.KEY_OVERDUE_PANEL, True)
        timer_on = s.get_bool(policies.KEY_TIMER_PANEL, False)
        if not (list_on or overdue_on or timer_on):
            return  # 모두 꺼진 채로 종료했으면 최소화 상태 유지
        scr = self.available_geometry()
        self._skip_open_reaction = True
        if list_on:
            self._bubble.show_for_character(self.frameGeometry(), scr)
        else:
            self._bubble.show_detached_panels(self.frameGeometry(), scr)
        self._sync_timer_bubble()

    def _restore_grids(self) -> None:
        """캐릭터 클릭으로 그리드 표시: 설정상 '켜짐'인 그리드만 보여준다(#2).
        모두 꺼져 있으면 전부 켠다(escape, #3). 설정 저장은 BubbleWidget 이 처리."""
        s = self._settings
        list_on = s.get_bool(policies.KEY_LIST_SHOW, True)
        overdue_on = s.get_bool(policies.KEY_OVERDUE_PANEL, True)
        timer_on = s.get_bool(policies.KEY_TIMER_PANEL, False)
        if not (list_on or overdue_on or timer_on):
            self._events.overdue_panel_changed.emit(True)  # 핸들러가 설정 저장
            self._events.timer_panel_changed.emit(True)
            list_on = True  # show_for_character 가 KEY_LIST_SHOW=1 기록
        scr = self.available_geometry()
        if list_on:
            self._bubble.show_for_character(self.frameGeometry(), scr)  # bubble_opened emit → open 리액션
        else:
            self._bubble.show_detached_panels(self.frameGeometry(), scr)
            if not self._working:  # 타이머 진행 중(정지 포함)이면 work/pause 이미지 유지
                self._start_reaction("open", _GRID_REACT_MS)  # 패널만 열릴 때도 캐릭터 클릭 → open 리액션
        self._sync_timer_bubble()

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
        """delete/리액션 등 일시 상태 종료 후 기본 상황으로 복귀."""
        self._set_situation(self._priority_situation())

    # ── 우클릭 메뉴 ─────────────────────────────────────────
    def _show_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        menu.addAction(self._action("설정", self._controller.open_settings))

        # 그리드 표시 토글(체크=표시). 체크 상태는 설정값을 그대로 반영한다(✕/–로 바뀐 값 포함).
        # 밀린할일·타이머는 시그널만 쏘고, 설정 저장·표시는 BubbleWidget 이 일괄 처리한다.
        menu.addAction(self._grid_action(
            "할일 목록 표시", policies.KEY_LIST_SHOW, True, self._toggle_list))
        menu.addAction(self._grid_action(
            "밀린할일 표시", policies.KEY_OVERDUE_PANEL, True,
            self._events.overdue_panel_changed))
        menu.addAction(self._grid_action(
            "타이머 패널 표시", policies.KEY_TIMER_PANEL, False,
            self._events.timer_panel_changed))

        # 되돌리기(삭제 취소): 되돌릴 항목이 있을 때만 활성.
        a_undo = self._action("되돌리기", self._service.undo_remove)
        a_undo.setEnabled(self._undo_available)
        menu.addAction(a_undo)

        menu.addAction(self._action("트레이로 최소화", self._controller.minimize_to_tray))
        menu.addSeparator()
        menu.addAction(self._action("종료", self._controller.quit_app))
        menu.exec(global_pos)

    def _action(self, label: str, slot) -> QAction:
        """클릭형 메뉴 항목 생성(triggered → slot)."""
        a = QAction(label, self)
        a.triggered.connect(slot)
        return a

    def _grid_action(self, label: str, key: str, default_on: bool, slot) -> QAction:
        """체크형 그리드 토글 항목 생성. 체크 상태=설정값, toggled(bool)→slot(슬롯/시그널)."""
        a = QAction(label, self)
        a.setCheckable(True)
        a.setChecked(self._settings.get_bool(key, default_on))
        a.toggled.connect(slot)
        return a

    def _on_undo_available(self, available: bool) -> None:
        self._undo_available = available

    def _toggle_list(self, on: bool) -> None:
        """할일 목록 표시 토글(우클릭 메뉴): 목록 그리드 '상태'만 바꾼다.
        전체 최소화(아무 그리드도 안 보임) 상태에서는 화면 출력을 하지 않는다 —
        그리드 출력은 캐릭터 좌클릭 액션이 담당한다(#2). 그리드가 떠 있는 동안엔 즉시 반영."""
        if not (self._bubble.isVisible() or self._bubble.any_panel_visible()):
            self._settings.set_bool(policies.KEY_LIST_SHOW, on)
            return
        if on == self._bubble.isVisible():
            return
        scr = self.available_geometry()
        if on:
            self._skip_open_reaction = True  # 우클릭 메뉴 → open 리액션 억제
            self._bubble.show_for_character(self.frameGeometry(), scr)
            self._sync_timer_bubble()
        else:
            self._bubble.close_keep_panels()  # 목록만 닫고 밀린할일·타이머 패널은 유지
        self._refresh_situation()

    def closeEvent(self, e) -> None:
        self.save_position()
        super().closeEvent(e)
