"""data/settings_repository.py — settings KV 테이블 전담."""
from __future__ import annotations


class SettingsRepository:
    def __init__(self, db):
        self._db = db
        self.conn = db.conn

    def get(self, key: str, default: str | None = None) -> str | None:
        r = self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return r["value"] if r else default

    def get_int(self, key: str, default: int) -> int:
        v = self.get(key)
        try:
            return int(v) if v is not None else default
        except (TypeError, ValueError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        v = self.get(key)
        if v is None:
            return default
        return v in ("1", "true", "True")

    def set(self, key: str, value) -> None:
        self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )
        self.conn.commit()

    def set_bool(self, key: str, value: bool) -> None:
        """get_bool 의 짝: bool 을 '1'/'0' 으로 저장."""
        self.set(key, "1" if value else "0")

    def all(self) -> dict[str, str]:
        rows = self.conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}
