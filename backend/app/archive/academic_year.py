from datetime import date, datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def to_kst_date(dt: datetime) -> date:
    """timezone-aware datetime을 KST 기준 날짜로 변환한다. naive 입력은 거부한다."""
    if dt.utcoffset() is None:
        raise ValueError("timezone-aware datetime이 필요합니다")
    return dt.astimezone(KST).date()


def academic_year(dt: datetime) -> int:
    """학년도 연도를 반환한다. KST 기준 3월 1일 ~ 이듬해 2월 말일이 한 학년도다."""
    d = to_kst_date(dt)
    return d.year if d.month >= 3 else d.year - 1
