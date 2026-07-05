"""domain/policies.py — 순수 규칙 함수 모음. DB/Qt 의존 없음."""
from __future__ import annotations

import calendar
from datetime import date, timedelta

# 설정 키 상수 (오타 방지를 위해 한 곳에 모음)
KEY_INCOMPLETE = "policy.incomplete"        # 예전 keep/rollover 설정 호환용(현재 UI 미노출)
KEY_OVERDUE_AUTO_ROLLOVER = "todo.overdue_auto_rollover"  # '0' | '1' — 날짜 변경 시 밀린 일반 할일 자동 이월
KEY_FONT = "app.font"                        # 폰트 서체 패밀리명 (빈 문자열 = 시스템 기본)
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
KEY_COMPLETED_VIEW_MODE = "bubble.completed_view_mode"  # 'summary' | 'detail' — 완료한 일 표시 방식
KEY_IMAGE_IDLE = "character.image_idle"            # 비활성 상태(마지막 활동 n시간 초과)
KEY_IDLE_HOURS = "character.idle_hours"            # 비활성 판정 기준 시간 (0=비활성화)
KEY_IMAGE_DONE = "character.image_done"            # 할일 완료 리액션
KEY_IMAGE_ADD = "character.image_add"              # 할일 추가 리액션
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
KEY_HOTKEY_OVERDUE = "hotkey.overdue"              # 밀린할일 패널 토글
KEY_HOTKEY_TIMER = "hotkey.timer_panel"            # 타이머 패널 토글
KEY_BUBBLE_ANIMATION = "app.bubble_animation"      # '0' | '1' — 팝업 열기/닫기 페이드 애니메이션
KEY_TIMER_AUTO_COMPLETE = "timer.auto_complete"    # '0' | '1' — 타이머 완료 시 할일 자동 완료
KEY_TIMER_STEP = "timer.adjust_step"               # 타이머 −/+ 증감 간격(초). 1분 미만은 항상 5초 고정.
KEY_TODO_COUNT_BUBBLE = "bubble.todo_count_bubble"  # '0' | '1' — 최소화 시 '할일 n개' 풍선 표시
KEY_ALWAYS_ON_TOP = "app.always_on_top"      # '0' | '1' — 캐릭터/그리드 항상 위 표시
KEY_CHARACTER_POSITION_LOCKED = "character.position_locked"  # '0' | '1' — 캐릭터 드래그 이동 잠금
KEY_HOTKEY_UNDO = "hotkey.undo_remove"       # 삭제 되돌리기
KEY_OVERDUE_IMAGE_INTERVAL_MINUTES = "character.overdue_image_interval_minutes"  # 밀린할일 이미지 재표시 간격(분, 0=항상)
KEY_OVERDUE_IMAGE_LAST_SHOWN = "character.overdue_image_last_shown"  # 밀린할일 이미지 마지막 표시 시각(epoch seconds)

DEFAULT_TIMER_STEP = 60   # 타이머 증감 간격 기본값(1분)
DEFAULT_STANDALONE_SECONDS = 25 * 60  # 일반(상시) 타이머 기본 시간(25분)

# 글로벌 단축키 기본값
DEFAULT_HOTKEY_TODO = "Ctrl+Shift+T"
DEFAULT_HOTKEY_CHARACTER = "Ctrl+Shift+C"
DEFAULT_HOTKEY_TODAY = "Ctrl+Shift+U"
DEFAULT_HOTKEY_OVERDUE = "Ctrl+Shift+O"
DEFAULT_HOTKEY_TIMER = "Ctrl+Shift+P"
DEFAULT_HOTKEY_UNDO = "Ctrl+Shift+Z"


WEEKDAYS_KR = ["일", "월", "화", "수", "목", "금", "토"]


def app_weekday(d: date) -> int:
    """앱 기준 요일: 0=일 ~ 6=토 (Python isoweekday 월1..일7 → %7)."""
    return d.isoweekday() % 7


def fmt_md(d: date) -> str:
    """'6/17(수)' 형식의 짧은 날짜 표기(요일 포함)."""
    return f"{d.month}/{d.day}({WEEKDAYS_KR[app_weekday(d)]})"


def fmt_hms(seconds: int) -> str:
    """초 → 'mm:ss'(1시간 미만) 또는 'h:mm:ss'. 음수는 0으로 clamp."""
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def week_range(anchor: date) -> tuple[date, date]:
    """anchor 가 포함된 주(일~토)의 (일요일, 토요일)."""
    sunday = anchor - timedelta(days=app_weekday(anchor))
    return sunday, sunday + timedelta(days=6)


def week_of_month(anchor: date) -> tuple[int, int]:
    """anchor 가 속한 주(일~토)의 (월, 그 달의 몇 번째 주). 예: (6, 3) = 6월 3주차.

    주가 두 달에 걸칠 때는 그 주의 수요일(7일 중 가운데)이 속한 달을 기준으로 삼고,
    그 달 1일이 속한 주를 1주차로 센다(일요일 시작 기준)."""
    sunday, _ = week_range(anchor)
    mid = sunday + timedelta(days=3)            # 그 주의 수요일 = 소속 월 판정 기준
    first = mid.replace(day=1)
    first_sunday = first - timedelta(days=app_weekday(first))
    week_idx = (sunday - first_sunday).days // 7 + 1
    return mid.month, week_idx


def month_grid_range(anchor: date) -> tuple[date, date]:
    """월간 7x6 고정 그리드의 시작/끝 날짜.

    그 달 1일이 속한 주의 일요일부터 42칸(6주)까지.
    """
    first = anchor.replace(day=1)
    grid_start = first - timedelta(days=app_weekday(first))
    grid_end = grid_start + timedelta(days=41)
    return grid_start, grid_end


def monthly_target_day(year: int, month: int, wanted: int) -> int:
    """월간 규칙이 해당 (year, month) 에서 실제로 떨어지는 날.

    해당 월에 wanted 일이 없으면 말일로 당김(clamp).
    예: 2월에 31일 규칙 → 28일(또는 29일).
    """
    last = calendar.monthrange(year, month)[1]
    return min(wanted, last)
