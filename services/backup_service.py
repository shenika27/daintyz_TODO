"""services/backup_service.py — DB 파일 백업/복원.

export : 현재 .db 를 사용자가 지정한 경로로 복사.
import : 지정한 백업 .db 로 현재 DB 를 덮어씀(복원).
        무결성 검사를 통과한 경우에만 교체한다.

용량이 작아 동기 복사로 충분하다. 매우 큰 DB 로 커지면 QThread 워커로 빼고
완료를 시그널로 통지하도록 바꾸면 된다.
"""
from __future__ import annotations

import logging
import shutil
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)


class BackupService:
    def __init__(self, db):
        self._db = db

    def export(self, dest: str | Path) -> Path:
        dest = Path(dest)
        # 쓰기 캐시를 디스크로 내린 뒤 복사
        self._db.conn.commit()
        shutil.copy2(self._db.path, dest)
        log.info("Backup exported to %s", dest)
        return dest

    def import_(self, src: str | Path) -> None:
        src = Path(src)
        if not src.exists():
            raise FileNotFoundError(src)
        # 1) 후보 파일이 정상 SQLite 인지 검사
        self._verify_sqlite(src)
        # 2) 현재 커넥션 닫고 파일 교체
        target = self._db.path
        self._db.close()
        shutil.copy2(src, target)
        log.info("Backup imported from %s (restart 권장)", src)

    @staticmethod
    def _verify_sqlite(path: Path) -> None:
        conn = sqlite3.connect(str(path))
        try:
            res = conn.execute("PRAGMA integrity_check").fetchone()
            if not res or res[0] != "ok":
                raise ValueError("백업 파일 무결성 검사 실패")
            # 우리 스키마인지 최소 확인
            conn.execute("SELECT 1 FROM todos LIMIT 1")
        finally:
            conn.close()
