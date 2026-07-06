"""tests/test_policies.py — 순수 도메인 정책 테스트 (PySide6 없이 실행 가능).

실행: python -m pytest -q   또는   python tests/test_policies.py
"""
from datetime import date

from domain import policies


def test_app_weekday_sunday_is_zero():
    assert policies.app_weekday(date(2026, 6, 14)) == 0   # 일요일
    assert policies.app_weekday(date(2026, 6, 13)) == 6   # 토요일
    assert policies.app_weekday(date(2026, 6, 15)) == 1   # 월요일


def test_week_range_is_sun_to_sat():
    s, e = policies.week_range(date(2026, 6, 11))  # 목요일
    assert s == date(2026, 6, 7)   # 일
    assert e == date(2026, 6, 13)  # 토


def test_month_grid_is_42_days_from_sunday():
    s, e = policies.month_grid_range(date(2026, 2, 15))
    assert policies.app_weekday(s) == 0
    assert (e - s).days == 41


def test_monthly_target_day_clamp():
    # 해당 월에 없는 날짜는 말일로 당김
    assert policies.monthly_target_day(2026, 2, 31) == 28
    assert policies.monthly_target_day(2026, 2, 29) == 28   # 평년
    assert policies.monthly_target_day(2024, 2, 31) == 29   # 윤년
    # 존재하는 날짜는 그대로
    assert policies.monthly_target_day(2026, 1, 31) == 31
    assert policies.monthly_target_day(2026, 1, 15) == 15


def test_default_hotkey_scope_is_focused():
    assert policies.DEFAULT_HOTKEY_SCOPE == policies.HOTKEY_SCOPE_FOCUSED
    assert policies.HOTKEY_SCOPE_GLOBAL == "global"


def _run_all():
    fns = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print("PASS", fn.__name__)
    print(f"{len(fns)} passed")


if __name__ == "__main__":
    _run_all()
