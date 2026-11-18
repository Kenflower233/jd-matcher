import pytest

from src.usage_limit import DailyCallLimiter, PublicQuotaExceeded


def test_daily_call_limiter_blocks_after_limit():
    limiter = DailyCallLimiter()
    assert limiter.reserve(2).remaining == 1
    assert limiter.reserve(2).remaining == 0
    with pytest.raises(PublicQuotaExceeded, match="额度已用完"):
        limiter.reserve(2)
