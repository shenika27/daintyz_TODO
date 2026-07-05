"""domain/models.py — 순수 데이터 모델. Qt/DB 의존 없음 → 단위테스트 용이."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


PRIORITY_NONE = 0
PRIORITY_LOW = 1
PRIORITY_NORMAL = 2
PRIORITY_HIGH = 3


@dataclass
class Todo:
    id: int
    content: str
    due_date: str          # 'YYYY-MM-DD'
    completed: bool = False
    hidden: bool = False
    sort_order: int = 0
    priority: int = PRIORITY_NONE
    pinned: bool = False
    remind_at: Optional[str] = None      # 'YYYY-MM-DD HH:MM' (지금은 항상 None)
    recurring_id: Optional[int] = None

    @property
    def is_recurring_instance(self) -> bool:
        return self.recurring_id is not None

    @staticmethod
    def from_row(row) -> "Todo":
        return Todo(
            id=row["id"],
            content=row["content"],
            due_date=row["due_date"],
            completed=bool(row["completed"]),
            hidden=bool(row["hidden"]),
            sort_order=row["sort_order"],
            priority=row["priority"] if "priority" in row.keys() else PRIORITY_NONE,
            pinned=bool(row["pinned"]) if "pinned" in row.keys() else False,
            remind_at=row["remind_at"],
            recurring_id=row["recurring_id"],
        )


@dataclass
class RecurringRule:
    id: int
    content: str
    rule_type: str         # 'daily' | 'weekly' | 'monthly'
    weekdays: Optional[str] = None       # '0,3,5' (0=일 ~ 6=토)
    day_of_month: Optional[int] = None
    remind_time: Optional[str] = None    # 'HH:MM'
    start_date: str = ""
    end_date: Optional[str] = None
    active: bool = True

    @staticmethod
    def from_row(row) -> "RecurringRule":
        return RecurringRule(
            id=row["id"],
            content=row["content"],
            rule_type=row["rule_type"],
            weekdays=row["weekdays"],
            day_of_month=row["day_of_month"],
            remind_time=row["remind_time"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            active=bool(row["active"]),
        )

    def describe(self) -> str:
        if self.rule_type == "daily":
            base = "매일"
        elif self.rule_type == "weekly":
            names = ["일", "월", "화", "수", "목", "금", "토"]
            days = [names[int(x)] for x in (self.weekdays or "").split(",") if x != ""]
            base = "매주 " + ",".join(days)
        elif self.rule_type == "monthly":
            base = f"매월 {self.day_of_month}일"
        else:
            base = self.rule_type
        return base + ("" if self.active else " (중지)")
