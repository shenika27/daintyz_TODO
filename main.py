"""main.py — 부팅 + 의존성 조립(DI) + 앱 컨트롤러.

계층 결합을 main 한 곳에서만 묶는다. 각 모듈은 서로를 직접 import 해 생성하지 않는다.
"""
from __future__ import annotations

import logging
import sys
from datetime import date

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from core import logging_config
from core.events import EventBus
from core.global_hotkeys import GlobalHotkeys
from core.local_hotkeys import LocalHotkeys
from domain import policies
from data.database import Database
from data.recurring_repository import RecurringRepository
from data.settings_repository import SettingsRepository
from data.todo_repository import TodoRepository
from services.autostart_service import AutostartService
from services.backup_service import BackupService
from services.notification_service import NotificationService
from services.recurring_service import RecurringService
from services.timer_service import TimerService
from services.todo_service import TodoService
from ui.bubble.bubble_widget import BubbleWidget
from ui.character_widget import CharacterWidget
from ui.settings_dialog import SettingsDialog
from ui.timer_bubble import TimerBubble
from ui.todo_count_bubble import TodoCountBubble
from ui.tray import Tray

log = logging.getLogger(__name__)


class AppController:
    def __init__(self, app: QApplication):
        self.app = app
        self.db = Database()

        # 영속 계층
        self.todo_repo = TodoRepository(self.db)
        self.recurring_repo = RecurringRepository(self.db)
        self.settings_repo = SettingsRepository(self.db)

        # 저장된 폰트 서체 적용 (위젯 생성 전에 적용해야 전체 반영)
        font_family = self.settings_repo.get(policies.KEY_FONT, "")
        if font_family:
            f = app.font()
            f.setFamily(font_family)
            # 폰트가 작은 크기에서 AA를 끄도록 힌팅돼 있어도 강제로 매끄럽게 렌더링
            f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
            # 힌팅이 획을 픽셀 격자에 억지로 맞추며 두께가 들쭉날쭉해지는 것 방지
            f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
            app.setFont(f)

        # 이벤트 허브
        self.events = EventBus()

        # 서비스 계층
        self.recurring_service = RecurringService(
            self.todo_repo, self.recurring_repo, self.settings_repo
        )
        self.todo_service = TodoService(
            self.todo_repo, self.recurring_service, self.events
        )
        self.backup_service = BackupService(self.db)
        self.autostart_service = AutostartService()
        from services import update_service

        update_service.ensure_canonical_exe_copy()
        self.autostart_service.sync_on_startup()
        self.notification = NotificationService(self.db)
        self.timer_service = TimerService(self.events)

        # UI 계층
        self.bubble = BubbleWidget(
            self.todo_service, self.events, self.settings_repo, self.timer_service
        )
        self.timer_bubble = TimerBubble(self.events, self.settings_repo)
        self.todo_count_bubble = TodoCountBubble(self.settings_repo)
        self.character = CharacterWidget(
            self.todo_service, self.events, self.settings_repo, self.bubble, self,
            self.timer_service, self.timer_bubble, self.todo_count_bubble,
        )
        self.tray = Tray(self)
        self.notification.set_tray(self.tray)

        # 타이머 만료 시 트레이 알림
        self.events.timer_finished.connect(self._on_timer_finished)
        # 타이머 대상 할일이 외부에서 삭제/완료되면 타이머 해제
        self.events.todos_changed.connect(self._validate_timer)

        # 단축키. 기본은 앱 포커스 중만 동작하고, 옵션으로 전역 단축키를 쓴다.
        self.hotkeys = GlobalHotkeys(self.app)
        self.local_hotkeys = LocalHotkeys(self.app)
        self._register_hotkeys()
        self.events.hotkeys_changed.connect(self._register_hotkeys)

        # 반복 할일은 '오늘'에만 생성: 시작 시 1회 + 자정 넘김(1분마다 확인) 시 재생성.
        self._recurring_day = date.today()
        self._roll_over_overdue_if_enabled()
        self.todo_service.ensure_today_recurring()
        self._day_timer = QTimer(self.app)
        self._day_timer.setInterval(60_000)
        self._day_timer.timeout.connect(self._check_day_rollover)
        self._day_timer.start()

    def _check_day_rollover(self) -> None:
        """자정을 넘겨 날짜가 바뀌면 오늘 반복 회차를 생성하고 화면을 갱신한다."""
        today = date.today()
        if today != self._recurring_day:
            self._recurring_day = today
            self._roll_over_overdue_if_enabled()
            self.todo_service.ensure_today_recurring()
            self.events.todos_changed.emit(today.isoformat())

    def _roll_over_overdue_if_enabled(self) -> None:
        if not self.settings_repo.get_bool(
            policies.KEY_OVERDUE_AUTO_ROLLOVER, False
        ):
            return
        self.todo_service.move_all_overdue_regular_to_today()

    # ── 컨트롤러 API (UI 가 호출) ───────────────────────────
    def open_settings(self) -> None:
        dlg = SettingsDialog(
            self.settings_repo,
            self.events,
            self.backup_service,
            self.autostart_service,
            self.recurring_repo,
            self.todo_service,
            parent=self.character,
            app_quit=self.quit_app,
        )
        dlg.exec()

    def minimize_to_tray(self) -> None:
        self.bubble.hide()
        self.character.hide()
        # 설정이 켜져 있으면 타이머 도는 동안 타이머 풍선만 바탕화면에 남긴다
        keep = self.settings_repo.get_bool(policies.KEY_TIMER_TRAY_SHOW, True)
        self.character.sync_timer_bubble(standalone=keep)

    def toggle_character(self) -> None:
        if self.character.isVisible():
            self.bubble.hide()
            self.character.hide()
            keep = self.settings_repo.get_bool(policies.KEY_TIMER_TRAY_SHOW, True)
            self.character.sync_timer_bubble(standalone=keep)
        else:
            self.character.show()
            self.character.raise_()
            self.character.sync_timer_bubble()

    def show_from_timer_bubble(self) -> None:
        """타이머 풍선 클릭: 캐릭터 복원 + 말풍선 열기."""
        if not self.character.isVisible():
            self.character.show()
            self.character.raise_()
        if not self.bubble.isVisible():
            scr = self.character.available_geometry()
            self.bubble.show_for_character(self.character.frameGeometry(), scr)
        self.character.sync_timer_bubble()  # 말풍선 열렸으니 풍선 숨김

    def _on_timer_finished(self, todo_id: int) -> None:
        self.tray.notify("타이머 완료", "설정한 시간이 끝났어요.")
        # 자동 완료 옵션이 켜져 있으면 할일을 완료 처리.
        # CharacterWidget 이 먼저 timer_done 리액션을 시작하므로(시그널 연결 순서),
        # 여기서 발생하는 todo_completed 의 done 이미지는 억제되어 timer_done 만 출력된다.
        if self.timer_service.auto_complete:
            t = self.todo_repo.get(todo_id)
            if t is not None and not t.completed:
                self.todo_service.toggle(todo_id)

    def _validate_timer(self, _iso: str) -> None:
        """타이머 대상 할일이 삭제되거나 완료되면 타이머를 해제한다."""
        tid = self.timer_service.active_todo_id
        if tid is None:
            return
        t = self.todo_repo.get(tid)
        if t is None or t.completed:
            self.timer_service.cancel()

    # ── 단축키 ─────────────────────────────────────────────
    def _register_hotkeys(self) -> None:
        self.hotkeys.unregister_all()
        self.local_hotkeys.unregister_all()
        s = self.settings_repo
        scope = s.get(policies.KEY_HOTKEY_SCOPE, policies.DEFAULT_HOTKEY_SCOPE)
        manager = self.hotkeys if scope == policies.HOTKEY_SCOPE_GLOBAL else self.local_hotkeys
        specs = [
            (policies.KEY_HOTKEY_TODO, policies.DEFAULT_HOTKEY_TODO, self.toggle_bubble),
            (policies.KEY_HOTKEY_CHARACTER, policies.DEFAULT_HOTKEY_CHARACTER, self.toggle_character),
            (policies.KEY_HOTKEY_TODAY, policies.DEFAULT_HOTKEY_TODAY, self.go_today),
            (policies.KEY_HOTKEY_OVERDUE, policies.DEFAULT_HOTKEY_OVERDUE, self.toggle_overdue),
            (policies.KEY_HOTKEY_TIMER, policies.DEFAULT_HOTKEY_TIMER, self.toggle_timer_panel),
            (policies.KEY_HOTKEY_UNDO, policies.DEFAULT_HOTKEY_UNDO, self.todo_service.undo_remove),
            (policies.KEY_HOTKEY_PASTE, policies.DEFAULT_HOTKEY_PASTE, self.bubble.paste_clipboard_to_selected_date),
        ]
        for key, default, cb in specs:
            seq = s.get(key, default) or default
            manager.register(seq, cb)

    def toggle_overdue(self) -> None:
        on = not self.settings_repo.get_bool(policies.KEY_OVERDUE_PANEL, True)
        self.events.overdue_panel_changed.emit(on)

    def toggle_timer_panel(self) -> None:
        on = not self.settings_repo.get_bool(policies.KEY_TIMER_PANEL, False)
        self.events.timer_panel_changed.emit(on)

    def toggle_bubble(self) -> None:
        self.character.toggle_bubble()

    def go_today(self) -> None:
        self.bubble.go_today()
        if not self.bubble.isVisible():
            scr = self.character.available_geometry()
            self.bubble.show_for_character(self.character.frameGeometry(), scr)
        else:
            self.bubble.raise_()

    def quit_app(self) -> None:
        if getattr(self, "_quitting", False):
            return
        self._quitting = True
        try:
            self.hotkeys.unregister_all()
            self.local_hotkeys.unregister_all()
            self.notification.stop()
            self.timer_service.cancel()
            self.timer_bubble.hide()
            self.todo_count_bubble.hide()
            self.tray.hide()          # 트레이 잔상/지연 방지: 먼저 내림
            self.bubble.hide()
            self.character.save_position()
            self.character.hide()
        except Exception:  # noqa: BLE001
            log.exception("정리 중 오류")
        finally:
            try:
                self.db.close()
            except Exception:  # noqa: BLE001
                log.exception("db close 오류")
            # 메뉴/트리거 콜백 스택이 풀린 뒤 종료하도록 다음 틱으로 미룸
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, self.app.quit)

    def run(self) -> None:
        self.character.show()
        self.tray.show()
        self.notification.start()
        # character.show() 이후 frameGeometry 가 확정되면 이전 그리드 상태 복원
        QTimer.singleShot(0, self.character.restore_on_startup)
        # 시작 3초 후 백그라운드로 업데이트 확인
        QTimer.singleShot(3000, self._check_update_background)

    def _check_update_background(self) -> None:
        from PySide6.QtCore import QThread, Signal
        from services import update_service

        if not update_service.UPDATE_CHECK_URL:
            return

        class _Worker(QThread):
            found = Signal(object)

            def run(self):
                status, info = update_service.check_update()
                if status == "update" and info:
                    self.found.emit(info)

        self._update_worker = _Worker(self.app)
        self._update_worker.found.connect(self._on_update_found)
        self._update_worker.start()

    def _on_update_found(self, info) -> None:
        from PySide6.QtWidgets import QMessageBox

        from ui.update_flow import run_update_flow

        ret = QMessageBox.question(
            self.character,
            "업데이트 알림",
            f"새 버전 v{info.version} 이 있습니다.\n지금 업데이트할까요?\n\n(나중에 설정 → 업데이트 확인에서도 가능합니다)",
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        # 다운로드는 백그라운드 스레드에서 진행(UI 멈춤 방지). 완료 시 정상 종료 후 재시작.
        run_update_flow(self.character, info, self.quit_app)


class _WindowShowLogger:
    """진단용: 최상위 위젯이 표시(Show)/숨김(Hide)될 때 클래스/지오메트리를 로깅한다.
    환경변수 CT_DEBUG_WINDOWS=1 일 때만 설치된다('떴다 사라지는 원인미상 창' 추적용)."""

    def __init__(self):
        from PySide6.QtCore import QObject

        class _Filter(QObject):
            def eventFilter(self, obj, event):
                from PySide6.QtCore import QEvent
                from PySide6.QtWidgets import QWidget

                et = event.type()
                if et in (QEvent.Type.Show, QEvent.Type.Hide) and \
                        isinstance(obj, QWidget) and obj.isWindow():
                    kind = "SHOW" if et == QEvent.Type.Show else "HIDE"
                    log.info(
                        "[WINDOW-%s] %s title=%r geom=%s flags=0x%X",
                        kind, obj.__class__.__name__, obj.windowTitle(),
                        obj.geometry().getRect(), int(obj.windowFlags()),
                    )
                return False

        self._filter = _Filter()

    def install(self, app) -> None:
        app.installEventFilter(self._filter)


_SINGLE_INSTANCE_KEY = "character_todo_single_instance"


def _acquire_single_instance():
    """이미 실행 중인 인스턴스가 있으면 None 을 반환한다(중복 실행 차단, #1).
    없으면 공유 메모리 핸들을 만들어 돌려준다 — 호출자가 프로세스 수명 동안 참조를
    유지해야 잠금이 풀리지 않는다. Windows 는 프로세스 종료 시 자동 해제된다."""
    from PySide6.QtCore import QSharedMemory

    shared = QSharedMemory(_SINGLE_INSTANCE_KEY)
    if not shared.create(1):
        return None
    return shared


def main() -> int:
    import os

    logging_config.setup_logging()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 트레이 상주: 창 닫혀도 종료 안 함

    # 단일 인스턴스 보장: 중복 실행 시 캐릭터/그리드가 겹쳐 떠 '복제'처럼 보이는 문제 차단(#1).
    _single = _acquire_single_instance()
    if _single is None:
        log.info("[SINGLE] 이미 실행 중 — 새 인스턴스 종료 (pid=%s)", os.getpid())
        QMessageBox.information(None, "이미 실행 중", "캐릭터 투두가 이미 실행 중입니다.")
        return 0
    log.info("[SINGLE] 인스턴스 시작 (pid=%s)", os.getpid())
    # 툴팁 페이드/애니메이션 끄기 → 0.5초 뒤 즉시 표시
    app.setEffectEnabled(Qt.UIEffect.UI_FadeTooltip, False)
    app.setEffectEnabled(Qt.UIEffect.UI_AnimateTooltip, False)

    _win_logger = None
    if os.environ.get("CT_DEBUG_WINDOWS"):
        _win_logger = _WindowShowLogger()
        _win_logger.install(app)
        log.info("[WINDOW-SHOW] 진단 로거 활성화됨")

    if not Tray_is_available():
        QMessageBox.warning(None, "트레이 없음", "시스템 트레이를 사용할 수 없습니다.")

    try:
        controller = AppController(app)
    except Exception:  # noqa: BLE001
        log.exception("초기화 실패")
        raise
    controller.run()
    return app.exec()


def Tray_is_available() -> bool:
    from PySide6.QtWidgets import QSystemTrayIcon

    return QSystemTrayIcon.isSystemTrayAvailable()


if __name__ == "__main__":
    sys.exit(main())
