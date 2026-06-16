"""domain/policies.py — 순수 규칙 함수 모음. DB/Qt 의존 없음."""
from __future__ import annotations

import calendar
from datetime import date, timedelta

# 설정 키 상수 (오타 방지를 위해 한 곳에 모음)
KEY_INCOMPLETE = "policy.incomplete"        # 'keep' | 'rollover'
KEY_MONTH_OVERFLOW = "policy.month_overflow"  # 'skip' | 'clamp'
KEY_IMAGE_PATH = "character.image_path"            # 기본(오늘, 특이사항 없음)
KEY_IMAGE_OVERDUE = "character.image_overdue"      # 이전 날짜 미달성 할일이 있을 때
KEY_IMAGE_DELETE = "character.image_delete"        # 할일을 캐릭터에 끌어다 둘 때(삭제)
KEY_LAST_X = "character.last_x"
KEY_LAST_Y = "character.last_y"
KEY_AUTOSTART = "app.autostart"             # '0' | '1'
KEY_LAST_VIEW = "bubble.last_view"          # 'day' | 'week' | 'month'
KEY_THEME = "app.theme"                      # 'light' | 'dark' | 'system'
KEY_OVERDUE_PANEL = "bubble.overdue_panel"         # '0' | '1' — 밀린 할일 패널 표시
KEY_OVERDUE_PANEL_SIDE = "bubble.overdue_panel_side"  # 'right' | 'left'
KEY_IMAGE_IDLE = "character.image_idle"            # 비활성 상태(마지막 활동 n시간 초과)
KEY_IDLE_HOURS = "character.idle_hours"            # 비활성 판정 기준 시간 (0=비활성화)


def app_weekday(d: date) -> int:
    """앱 기준 요일: 0=일 ~ 6=토 (Python isoweekday 월1..일7 → %7)."""
    return d.isoweekday() % 7


def week_range(anchor: date) -> tuple[date, date]:
    """anchor 가 포함된 주(일~토)의 (일요일, 토요일)."""
    sunday = anchor - timedelta(days=app_weekday(anchor))
    return sunday, sunday + timedelta(days=6)


def month_grid_range(anchor: date) -> tuple[date, date]:
    """월간 7x6 고정 그리드의 시작/끝 날짜.

    그 달 1일이 속한 주의 일요일부터 42칸(6주)까지.
    """
    first = anchor.replace(day=1)
    grid_start = first - timedelta(days=app_weekday(first))
    grid_end = grid_start + timedelta(days=41)
    return grid_start, grid_end


def monthly_target_day(year: int, month: int, wanted: int, overflow: str) -> int | None:
    """월간 규칙이 해당 (year, month) 에서 실제로 떨어지는 날.

    overflow='clamp' 면 말일로 당김, 'skip' 이면 없는 날은 None.
    """
    last = calendar.monthrange(year, month)[1]
    if wanted <= last:
        return wanted
    return last if overflow == "clamp" else None
