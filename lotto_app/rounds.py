"""추첨일 기준 회차 계산 (한국 시간 기준).

- 로또 6/45: 1회 2002-12-07(토), 매주 토요일 20:35경 추첨
- 연금복권 720+: 1회 2020-05-07(목), 매주 목요일 19:05경 추첨
"""
from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
LOTTO_BASE = date(2002, 12, 7)
PENSION_BASE = date(2020, 5, 7)
# 추첨 후 결과가 공개될 만한 시각 (여유를 둠)
LOTTO_RESULT_HOUR = 21
PENSION_RESULT_HOUR = 20


def now_kst() -> datetime:
    return datetime.now(KST)


def _latest_drawn(base: date, result_hour: int, now: datetime | None = None) -> int:
    now = now or now_kst()
    days = (now.date() - base).days
    rnd = days // 7 + 1
    draw_day = base + timedelta(days=(rnd - 1) * 7)
    if draw_day == now.date() and now.hour < result_hour:
        rnd -= 1
    return rnd


def lotto_latest_drawn(now=None) -> int:
    """결과가 나왔을 것으로 예상되는 최신 로또 회차."""
    return _latest_drawn(LOTTO_BASE, LOTTO_RESULT_HOUR, now)


def pension_latest_drawn(now=None) -> int:
    return _latest_drawn(PENSION_BASE, PENSION_RESULT_HOUR, now)


def lotto_next_round(now=None) -> int:
    """지금 구매하면 해당되는 로또 회차."""
    return lotto_latest_drawn(now) + 1


def pension_next_round(now=None) -> int:
    return pension_latest_drawn(now) + 1


def lotto_draw_date(rnd: int) -> date:
    return LOTTO_BASE + timedelta(days=(rnd - 1) * 7)


def pension_draw_date(rnd: int) -> date:
    return PENSION_BASE + timedelta(days=(rnd - 1) * 7)
