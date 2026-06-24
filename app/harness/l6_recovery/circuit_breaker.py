"""
DeepSeek API 熔断器。

规则：
  - 连续失败 5 次 → 熔断，60 秒内不再尝试
  - 熔断期间发消息 → 回复"我现在遇到了一些问题，稍后再和你说话"
  - 60 秒后自动恢复
"""

import asyncio
import time
import logging

logger = logging.getLogger("circuit_breaker")

# 配置
FAILURE_THRESHOLD = 5      # 连续失败阈值
COOLDOWN_SECONDS = 60      # 熔断冷却时间


class CircuitBreaker:
    """异步熔断器，使用 asyncio.Lock 防止阻塞事件循环。"""

    def __init__(self):
        self._lock = asyncio.Lock()
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._open_since: float | None = None  # 熔断开始时间

    async def is_open(self) -> bool:
        """熔断是否开启（不允许请求）。"""
        async with self._lock:
            if self._open_since is None:
                return False
            # 检查是否已过冷却期
            if time.monotonic() - self._open_since >= COOLDOWN_SECONDS:
                self._open_since = None
                self._failure_count = 0
                logger.info("熔断器已自动恢复")
                return False
            return True

    async def can_retry(self) -> bool:
        """是否允许重试（熔断未开启）。"""
        return not await self.is_open()

    async def record_failure(self) -> None:
        """记录一次失败。"""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._failure_count >= FAILURE_THRESHOLD:
                self._open_since = time.monotonic()
                logger.warning(
                    f"熔断器已开启！连续失败 {self._failure_count} 次，"
                    f"冷却 {COOLDOWN_SECONDS}s"
                )

    async def record_success(self) -> None:
        """记录一次成功，重置计数器。"""
        async with self._lock:
            self._failure_count = 0
            self._open_since = None

    async def get_status(self) -> dict:
        """获取熔断器状态（监控用）。"""
        async with self._lock:
            return {
                "open": self._open_since is not None and not (
                    time.monotonic() - self._open_since >= COOLDOWN_SECONDS
                ),
                "failure_count": self._failure_count,
                "cooldown_remaining": max(
                    0,
                    COOLDOWN_SECONDS - (time.monotonic() - (self._open_since or 0))
                ) if self._open_since else 0,
            }


# 全局单例
circuit_breaker = CircuitBreaker()


class CircuitBreakerOpenError(Exception):
    """熔断器开启，拒绝请求。"""
    pass
