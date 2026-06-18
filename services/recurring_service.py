"""services/recurring_service.py — 반복 규칙을 '조회 시점'에 todos 로 구체화.

핵심
  - 날짜(범위)를 펼칠 때 호출 → 해당 규칙을 todos 행으로 1회 기록.
  - 존재 검사는 (recurring_id, due_date) 만 본다(hidden 무시) → 숨긴 회차 재생성 방지.
  - 월간 31일 없는 달: 말일로 당김(clamp) — 예: 2월에 31일 규칙 → 28일 생성.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from domain import policies
from domain.models import RecurringRule

log = logging.getLogger(__name__)


class RecurringService:
    def __init__(self, db, recurring_repo, settings_repo):
        self.conn = db.conn
        self._rules = recurring_repo
        self._settings = settings_repo

    def ensure_for_date(self, day: date) -> None:
        self.ensure_for_range(day, day)

    def ensure_for_range(self, start: date, end: date) -> None:
        rules = [r for r in self._rules.list_all() if r.active]
        if not rules:
            return
        cur = start
        while cur <= end:
            for rule in rules:
                if self._applies(rule, cur):
                    self._materialize(rule, cur)
            cur += timedelta(days=1)
        self.conn.commit()

    # ── 내부 ────────────────────────────────────────────────
    def _applies(self, rule: RecurringRule, day: date) -> bool:
        iso = day.isoformat()
        if rule.start_date and iso < rule.start_date:
            return False
        if rule.end_date and iso > rule.end_date:
            return False

        if rule.rule_type == "daily":
            return True
        if rule.rule_type == "weekly":
            allowed = {int(x) for x in (rule.weekdays or "").split(",") if x != ""}
            return policies.app_weekday(day) in allowed
        if rule.rule_type == "monthly":
            target = policies.monthly_target_day(day.year, day.month, rule.day_of_month or 1)
            return day.day == target
        return False

    def _materialize(self, rule: RecurringRule, day: date) -> None:
        iso = day.isoformat()
        exists = self.conn.execute(
            "SELECT 1 FROM todos WHERE recurring_id = ? AND due_date = ? LIMIT 1",
            (rule.id, iso),
        ).fetchone()
        if exists:
            return

        remind_at = f"{iso} {rule.remind_time}" if rule.remind_time else None
        next_order = self.conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM todos WHERE due_date = ?",
            (iso,),
        ).fetchone()[0]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute(
            "INSERT OR IGNORE INTO todos "
            "(content, due_date, sort_order, remind_at, recurring_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (rule.content, iso, next_order, remind_at, rule.id, now, now),
        )
