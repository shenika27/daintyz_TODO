"""data/recurring_repository.py — recurring_rules 테이블 전담."""
from __future__ import annotations

from datetime import date

from domain.models import RecurringRule


class RecurringRepository:
    def __init__(self, db):
        self._db = db
        self.conn = db.conn

    def list_all(self) -> list[RecurringRule]:
        rows = self.conn.execute(
            "SELECT * FROM recurring_rules ORDER BY id"
        ).fetchall()
        return [RecurringRule.from_row(r) for r in rows]

    def add(
        self,
        content: str,
        rule_type: str,
        weekdays: str | None = None,
        day_of_month: int | None = None,
        remind_time: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> int:
        start_date = start_date or date.today().isoformat()
        cur = self.conn.execute(
            "INSERT INTO recurring_rules "
            "(content, rule_type, weekdays, day_of_month, remind_time, start_date, end_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (content, rule_type, weekdays, day_of_month, remind_time, start_date, end_date),
        )
        self.conn.commit()
        return cur.lastrowid

    def set_active(self, rule_id: int, active: bool) -> None:
        self.conn.execute(
            "UPDATE recurring_rules SET active = ? WHERE id = ?",
            (1 if active else 0, rule_id),
        )
        self.conn.commit()

    def delete(self, rule_id: int) -> None:
        self.conn.execute("DELETE FROM recurring_rules WHERE id = ?", (rule_id,))
        self.conn.commit()
