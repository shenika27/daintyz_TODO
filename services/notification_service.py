"""services/notification_service.py — 알림 스케줄러 골격.

지금은 remind_at 입력 UI 가 없어 모든 todos.remind_at 이 NULL → 실제로 아무것도
쏘지 않는다. 시간 입력 UI 만 나중에 붙이면, 이미 돌고 있는 이 폴링이 바로 잡는다.

동시성: QTimer 는 GUI 이벤트 루프 위에서 동작하므로 별도 스레드가 필요 없다.
폴링 콜백은 초소형 쿼리 1회뿐이라 UI 를 멈추지 않는다.
"""
from __future__ import annotations

import logging
from datetime import datetime

from PyQt6.QtCore import QObject, QTimer

log = logging.getLogger(__name__)

POLL_INTERVAL_MS = 30_000  # 30초


class NotificationService(QObject):
    def __init__(self, db, tray=None, parent=None):
        super().__init__(parent)
        self.conn = db.conn
        self._tray = tray
        self._enabled = False
        self._fired: set[int] = set()
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)

    def set_tray(self, tray) -> None:
        self._tray = tray

    def start(self) -> None:
        self._enabled = True
        self._timer.start()
        log.info("NotificationService started (scaffold, no remind UI yet)")

    def stop(self) -> None:
        self._enabled = False
        self._timer.stop()

    def _poll(self) -> None:
        if not self._enabled:
            return
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        rows = self.conn.execute(
            "SELECT id, content FROM todos "
            "WHERE remind_at IS NOT NULL AND completed = 0 AND hidden = 0 "
            "AND remind_at <= ?",
            (now,),
        ).fetchall()
        for r in rows:
            if r["id"] in self._fired:
                continue
            self._fired.add(r["id"])
            self._show(r["content"])

    def _show(self, content: str) -> None:
        if self._tray is not None:
            try:
                self._tray.notify("할 일 알림", content)
            except Exception:  # noqa: BLE001
                log.exception("tray notify failed")
