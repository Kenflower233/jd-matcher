"""公开部署的进程内每日调用额度，避免共享API密钥被无限消耗。"""
from dataclasses import dataclass
from datetime import date
from threading import Lock


class PublicQuotaExceeded(RuntimeError):
    """公开演示版当日模型调用额度已用完。"""


@dataclass(frozen=True)
class QuotaSnapshot:
    used: int
    limit: int

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)


class DailyCallLimiter:
    """线程安全的单进程日额度；服务重启时自动重新计数。"""

    def __init__(self) -> None:
        self._lock = Lock()
        self._day = date.today()
        self._used = 0

    def _reset_if_needed(self) -> None:
        today = date.today()
        if today != self._day:
            self._day = today
            self._used = 0

    def reserve(self, limit: int) -> QuotaSnapshot:
        with self._lock:
            self._reset_if_needed()
            if self._used >= limit:
                raise PublicQuotaExceeded(
                    "公开演示版今天的模型调用额度已用完，请明天再试。"
                )
            self._used += 1
            return QuotaSnapshot(used=self._used, limit=limit)

    def snapshot(self, limit: int) -> QuotaSnapshot:
        with self._lock:
            self._reset_if_needed()
            return QuotaSnapshot(used=self._used, limit=limit)

    def reset_for_test(self) -> None:
        with self._lock:
            self._day = date.today()
            self._used = 0


PUBLIC_DAILY_LIMITER = DailyCallLimiter()
