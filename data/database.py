"""data/database.py — SQLite 커넥션 + 마이그레이션 러너.

마이그레이션은 별도 테이블 없이 PRAGMA user_version 으로 관리한다.
migrations/ 안의 NNNN_*.sql 중, 현재 user_version 보다 번호가 큰 것만
순서대로 실행한다. 파일 끝의 `PRAGMA user_version = N;` 이 버전을 올린다.
"""
from __future__ import annotations

import logging
import re
import sqlite3
from pathlib import Path

from core import paths

log = logging.getLogger(__name__)
_MIG_RE = re.compile(r"^(\d{4})_.*\.sql$")


class Database:
    def __init__(self, db_file: Path | None = None):
        self._db_file = db_file or paths.db_path()
        self.conn = sqlite3.connect(str(self._db_file))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.migrate()

    @property
    def path(self) -> Path:
        return self._db_file

    def _current_version(self) -> int:
        return self.conn.execute("PRAGMA user_version").fetchone()[0]

    def migrate(self) -> None:
        mig_dir = paths.migrations_dir()
        files = []
        for f in sorted(mig_dir.glob("*.sql")):
            m = _MIG_RE.match(f.name)
            if m:
                files.append((int(m.group(1)), f))
        files.sort()

        current = self._current_version()
        for version, f in files:
            if version <= current:
                continue
            log.info("Applying migration %s", f.name)
            sql = f.read_text(encoding="utf-8")
            self.conn.executescript(sql)
            self.conn.commit()
        log.info("DB ready at version %s (%s)", self._current_version(), self._db_file)

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:  # noqa: BLE001
            pass
