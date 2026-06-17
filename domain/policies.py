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
KEY_IMAGE_DONE = "character.image_done"            # 할일 완료 리액션
KEY_IMAGE_WORK = "character.image_work"            # 타이머 실행 중
KEY_IMAGE_PAUSE = "character.image_pause"          # 타이머 정지(일시정지) 중
KEY_IMAGE_TIMER_DONE = "character.image_timer_done"  # 타이머 완료(만료) 리액션
KEY_TIMER_TRAY_SHOW = "timer.tray_show"            # '0' | '1' — 트레이 최소화 시 타이머 풍선 유지
KEY_TIMER_PANEL = "bubble.timer_panel"             # '0' | '1' — 타이머 패널 상시 표시(할일 없이도)
KEY_LIST_SHOW = "bubble.list_show"                 # '0' | '1' — 할일 목록(말풍선) 그리드 표시 상태
KEY_IMAGE_OPEN = "character.image_open"            # 목록(말풍선) 열린 상태
KEY_IMAGE_CLOSED = "character.image_closed"        # 목록(말풍선) 닫힌 상태
KEY_BUBBLE_SIZE_PREFIX = "bubble.size."            # + 'day'|'week'|'month' → 'WxH' (사용자 커스텀 크기)
KEY_CHAR_SCALE = "character.scale"                 # 캐릭터 크기 % (50~200)
KEY_HOTKEY_TODO = "hotkey.todo"                    # 투두 목록 토글
KEY_HOTKEY_CHARACTER = "hotkey.character"          # 캐릭터 토글
KEY_HOTKEY_TODAY = "hotkey.today"                  # 오늘로 이동
KEY_BUBBLE_ANIMATION = "app.bubble_animation"      # '0' | '1' — 팝업 열기/닫기 페이드 애니메이션
KEY_TIMER_AUTO_COMPLETE = "timer.auto_complete"    # '0' | '1' — 타이머 완료 시 할일 자동 완료
KEY_TIMER_STEP = "timer.adjust_step"               # 타이머 −/+ 증감 간격(초). 1분 미만은 항상 5초 고정.

DEFAULT_TIMER_STEP = 60   # 타이머 증감 간격 기본값(1분)

# 글로벌 단축키 기본값
DEFAULT_HOTKEY_TODO = "Ctrl+Shift+T"
DEFAULT_HOTKEY_CHARACTER = "Ctrl+Shift+C"
DEFAULT_HOTKEY_TODAY = "Ctrl+Shift+D"


WEEKDAYS_KR = ["일", "월", "화", "수", "목", "금", "토"]


def app_weekday(d: date) -> int:
    """앱 기준 요일: 0=일 ~ 6=토 (Python isoweekday 월1..일7 → %7)."""
    return d.isoweekday() % 7


def fmt_md(d: date) -> str:
    """'6/17(수)' 형식의 짧은 날짜 표기(요일 포함)."""
    return f"{d.month}/{d.day}({WEEKDAYS_KR[app_weekday(d)]})"


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
