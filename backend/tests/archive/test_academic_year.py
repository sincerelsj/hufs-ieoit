from datetime import datetime

import pytest

from app.archive.academic_year import academic_year, to_kst_date


@pytest.mark.parametrize("utc, expected", [
    ("2026-02-28T14:59:59+00:00", 2025),  # KST 2/28 23:59:59
    ("2026-02-28T15:00:00+00:00", 2026),  # KST 3/1 00:00
    ("2028-02-29T03:00:00+00:00", 2027),  # 윤년
    ("2026-12-31T16:00:00+00:00", 2026),  # KST 2027-01-01
    ("2026-03-01T00:00:00+00:00", 2026),
])
def test_academic_year(utc, expected):
    assert academic_year(datetime.fromisoformat(utc)) == expected


def test_naive_rejected():
    with pytest.raises(ValueError):
        academic_year(datetime(2026, 3, 1))


def test_to_kst_date_converts_utc_to_kst_date():
    # UTC 2026-02-28 15:00 은 KST 2026-03-01 00:00 이다.
    assert to_kst_date(datetime.fromisoformat("2026-02-28T15:00:00+00:00")).isoformat() == "2026-03-01"


def test_to_kst_date_naive_rejected():
    with pytest.raises(ValueError):
        to_kst_date(datetime(2026, 3, 1))
