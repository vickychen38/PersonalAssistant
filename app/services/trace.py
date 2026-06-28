"""
请求链路追踪 — 为每条消息生成唯一 trace_id，
贯穿 webhook → router → session → agent → deepseek → cconnect 全链路。
"""

import logging
import time
import uuid

logger = logging.getLogger("trace")


def new_trace_id() -> str:
    """生成短 trace id（8 位 hex）。"""
    return uuid.uuid4().hex[:8]


class Trace:
    """
    单条消息的追踪上下文。

    用法:
        trace = Trace()
        trace.log("webhook", "收到消息", msg_id="abc")
        ...
        trace.log("agent", "dispatch", agent="todo")
        trace.done("回复已发送")
    """

    def __init__(self, message_id: str = ""):
        self.trace_id = new_trace_id()
        self.message_id = message_id
        self._start = time.monotonic()
        self._steps: list[str] = []

    def log(self, stage: str, detail: str = "", **kwargs) -> None:
        """记录一个步骤。stage 是阶段名（webhook/router/session/agent/deepseek/cconnect/scheduler）。"""
        elapsed_ms = (time.monotonic() - self._start) * 1000
        extras = " ".join(f"{k}={v}" for k, v in kwargs.items() if v)
        msg = f"[trace={self.trace_id}] [{stage}] +{elapsed_ms:.1f}ms {detail}"
        if extras:
            msg += f" | {extras}"
        logger.info(msg)
        self._steps.append(stage)

    def done(self, result: str = "") -> None:
        """标记链路结束。"""
        total_ms = (time.monotonic() - self._start) * 1000
        steps_str = " → ".join(self._steps)
        logger.info(
            f"[trace={self.trace_id}] DONE +{total_ms:.1f}ms "
            f"steps={len(self._steps)} [{steps_str}] {result}"
        )

    @property
    def total_ms(self) -> float:
        return (time.monotonic() - self._start) * 1000
