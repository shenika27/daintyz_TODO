"""ui/update_flow.py — 업데이트 다운로드·적용 공용 흐름(비차단).

시작 시 자동 확인(main)과 설정의 수동 확인이 공용으로 쓴다.
다운로드는 QThread 에서 수행하고 QProgressDialog 로 진행률을 보여주므로
받는 동안 UI 가 멈추지 않는다(이전에는 main 이 GUI 스레드에서 동기 다운로드해
앱 전체가 응답 없음 상태가 됐다).
"""
from __future__ import annotations

import logging
import webbrowser
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QMessageBox, QProgressDialog

from services import update_service

log = logging.getLogger(__name__)

# parent 가 없어도(자동 확인) worker/dialog 가 GC 되지 않도록 참조를 붙잡아 둔다.
_ACTIVE: list = []


class _DownloadWorker(QThread):
    progress = Signal(int, int)  # downloaded, total
    done = Signal(str)           # 완료 파일 경로
    error = Signal(str)          # 실패 메시지

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self):
        try:
            path = update_service.download_update(self._url, self.progress.emit)
            self.done.emit(str(path))
        except Exception as e:  # noqa: BLE001
            self.error.emit(str(e))


def run_update_flow(parent, info, on_quit: Callable[[], None]) -> None:
    """새 버전 다운로드 → 적용 → 재시작. 진행 중 UI 는 멈추지 않는다.

    on_quit: 적용 직전에 앱을 정상 종료시키는 콜백(위치 저장·DB close 등).
    """
    dlg = QProgressDialog("다운로드 중…", "취소", 0, 100, parent)
    dlg.setWindowTitle(f"업데이트 v{info.version}")
    dlg.setMinimumDuration(0)
    dlg.setAutoClose(False)
    dlg.setAutoReset(False)

    worker = _DownloadWorker(info.download_url, parent)
    _ACTIVE.append(worker)
    _ACTIVE.append(dlg)

    def _cleanup() -> None:
        for obj in (worker, dlg):
            if obj in _ACTIVE:
                _ACTIVE.remove(obj)

    def on_progress(downloaded: int, total: int) -> None:
        if total > 0:
            dlg.setMaximum(total)
            dlg.setValue(downloaded)
        else:
            dlg.setMaximum(0)  # 크기 미상 → 불확정 진행바

    def on_error(msg: str) -> None:
        dlg.close()
        _cleanup()
        QMessageBox.critical(parent, "오류", f"다운로드 중 오류가 발생했습니다:\n{msg}")

    def on_done(path: str) -> None:
        dlg.close()
        _cleanup()
        try:
            update_service.apply_and_restart(Path(path))
        except update_service.UpdateNeedsManualInstall:
            QMessageBox.information(
                parent,
                "수동 설치 필요",
                "설치된 위치에 쓸 수 없어 자동 교체가 불가합니다.\n"
                "열리는 릴리즈 페이지에서 최신 설치본을 내려받아 실행해 주세요.",
            )
            webbrowser.open(update_service.RELEASES_PAGE_URL)
            return
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(parent, "오류", f"업데이트 적용 실패:\n{e}")
            return
        on_quit()

    def on_cancel() -> None:
        if worker.isRunning():
            worker.terminate()  # 다운로드 스레드 중단
        _cleanup()

    worker.progress.connect(on_progress)
    worker.done.connect(on_done)
    worker.error.connect(on_error)
    dlg.canceled.connect(on_cancel)

    worker.start()
    dlg.show()
