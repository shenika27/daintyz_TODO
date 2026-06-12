"""main.py — 부팅 + 의존성 조립(DI) + 앱 컨트롤러.

계층 결합을 main 한 곳에서만 묶는다. 각 모듈은 서로를 직접 import 해 생성하지 않는다.
"""
from __future__ import annotations

import logging
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from core import logging_config
from core.events import EventBus
from data.database import Database
from data.recurring_repository import RecurringRepository
from data.settings_repository import SettingsRepository
from data.todo_repository import TodoRepository
from services.autostart_service import AutostartService
from services.backup_service import BackupService
from services.notification_service import NotificationService
from services.recurring_service import RecurringService
from services.todo_service import TodoService
from ui.bubble.bubble_widget import BubbleWidget
from ui.character_widget import CharacterWidget
from ui.settings_dialog import SettingsDialog
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

        # 이벤트 허브
        self.events = EventBus()

        # 서비스 계층
        self.recurring_service = RecurringService(
            self.db, self.recurring_repo, self.settings_repo
        )
        self.todo_service = TodoService(
            self.todo_repo, self.recurring_service, self.events
        )
        self.backup_service = BackupService(self.db)
        self.autostart_service = AutostartService()
        self.notification = NotificationService(self.db)

        # UI 계층
        self.bubble = BubbleWidget(self.todo_service, self.events, self.settings_repo)
        self.character = CharacterWidget(
            self.todo_service, self.events, self.settings_repo, self.bubble, self
        )
        self.tray = Tray(self)
        self.notification.set_tray(self.tray)

    # ── 컨트롤러 API (UI 가 호출) ───────────────────────────
    def open_settings(self) -> None:
        dlg = SettingsDialog(
            self.settings_repo,
            self.events,
            self.backup_service,
            self.autostart_service,
            self.recurring_repo,
            parent=self.character,
        )
        dlg.exec()

    def minimize_to_tray(self) -> None:
        self.bubble.hide()
        self.character.hide()

    def toggle_character(self) -> None:
        if self.character.isVisible():
            self.bubble.hide()
            self.character.hide()
        else:
            self.character.show()
            self.character.raise_()

    def quit_app(self) -> None:
        try:
            self.notification.stop()
            self.character._save_position()
        except Exception:  # noqa: BLE001
            log.exception("save on quit failed")
        finally:
            self.db.close()
            self.app.quit()

    def run(self) -> None:
        self.character.show()
        self.tray.show()
        self.notification.start()


def main() -> int:
    logging_config.setup_logging()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 트레이 상주: 창 닫혀도 종료 안 함

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
    from PyQt6.QtWidgets import QSystemTrayIcon

    return QSystemTrayIcon.isSystemTrayAvailable()


if __name__ == "__main__":
    sys.exit(main())
