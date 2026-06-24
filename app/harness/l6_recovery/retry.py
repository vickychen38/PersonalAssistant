"""
DeepSeek API 重试机制 — 指数退避。

策略：
  - 第 1 次失败 → 等 1 秒重试
  - 第 2 次失败 → 等 2 秒重试
  - 第 3 次失败 → 等 4 秒重试
  - 全部失败 → 30 秒后最后重试一次
  - 仍失败 → 放弃，记录日志
"""

import asyncio
import logging
from typing import TypeVar, Callable, Awaitable, Any

from app.harness.l6_recovery.circuit_breaker import circuit_breaker

logger = logging.getLogger("retry")

T = TypeVar("T")

# 重试间隔（秒）
RETRY_DELAYS = [1, 2, 4]
FINAL_RETRY_DELAY = 30  # 最终重试等待时间
MAX_RETRIES = len(RETRY_DELAYS)


class RetryExhaustedError(Exception):
    """所有重试均已失败。"""
    pass


async def retry_with_backoff(
    fn: Callable[..., Awaitable[T]],
    *args: Any,
    **kwargs: Any,
) -> T:
    """
    对异步函数执行指数退避重试。

    参数:
        fn: 要重试的异步函数
        *args, **kwargs: 传递给 fn 的参数

    返回:
        fn 的成功返回值

    异常:
        RetryExhaustedError: 所有重试均失败
    """
    last_error: Exception | None = None

    for i, delay in enumerate(RETRY_DELAYS):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            last_error = e
            logger.warning(
                f"DeepSeek 调用失败 (第 {i+1}/{MAX_RETRIES+1} 次)，"
                f"{delay}s 后重试: {e}"
            )
            # 通知熔断器
            await circuit_breaker.record_failure()
            await asyncio.sleep(delay)

    # 全部重试失败后等待 30 秒，最后尝试一次
    logger.warning(f"前 {MAX_RETRIES} 次重试全部失败，{FINAL_RETRY_DELAY}s 后最后尝试")
    await asyncio.sleep(FINAL_RETRY_DELAY)

    try:
        return await fn(*args, **kwargs)
    except Exception as e:
        last_error = e
        await circuit_breaker.record_failure()
        logger.error(f"DeepSeek 最终重试也失败: {e}")
        raise RetryExhaustedError(
            f"DeepSeek API 调用失败，已重试 {MAX_RETRIES + 1} 次"
        ) from last_error
