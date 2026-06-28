"""
DeepSeek API 客户端。

封装：
  - Tool Call Loop（最多 10 次循环）
  - 模型选择（pro / flash）
  - 重试与熔断
  - 上下文控制（最多 20 条消息）
"""

import logging
from typing import Any, Dict, List

from openai import AsyncOpenAI

from app.config import config
from app.harness.l6_recovery.retry import retry_with_backoff, RetryExhaustedError
from app.harness.l6_recovery.circuit_breaker import circuit_breaker, CircuitBreakerOpenError

logger = logging.getLogger("deepseek")

# 最大工具调用循环次数
MAX_TOOL_ROUNDS = 10
# 传入 DeepSeek 的最大消息数
MAX_MESSAGES = 20

# 客户端实例（延迟初始化）
_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    """获取 DeepSeek API 客户端（单例）。"""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=config.deepseek_api_key,
            base_url=config.deepseek_base_url,
        )
    return _client


def _resolve_model(model: str) -> str:
    """将简称映射为完整模型名。"""
    if model == "pro":
        return config.deepseek_pro_model
    if model == "flash":
        return config.deepseek_flash_model
    return model


def _build_params(
    system_prompt: str,
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]] | None,
    model: str,
    max_tokens: int = 4096,
    disable_thinking: bool = False,
) -> Dict[str, Any]:
    """构建 API 请求参数，控制消息数量不超过 MAX_MESSAGES。"""
    # 截取最近的消息
    recent_messages = messages[-MAX_MESSAGES:]

    # 过滤非标准字段（如 session 存储的 ts 等），仅保留 OpenAI 兼容字段
    ALLOWED_MSG_KEYS = {"role", "content", "name", "tool_calls", "tool_call_id"}
    clean_messages = [
        {k: v for k, v in msg.items() if k in ALLOWED_MSG_KEYS}
        for msg in recent_messages
    ]

    params: Dict[str, Any] = {
        "model": _resolve_model(model),
        "messages": [
            {"role": "system", "content": system_prompt},
            *clean_messages,
        ],
        "max_tokens": max_tokens,
    }

    if tools:
        params["tools"] = tools
    if disable_thinking:
        params["extra_body"] = {"thinking": {"type": "disabled"}}

    return params


async def _call_api(
    system_prompt: str,
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]] | None,
    model: str,
    max_tokens: int = 4096,
    disable_thinking: bool = False,
) -> dict:
    """单次 API 调用（不含工具循环）。"""
    if await circuit_breaker.is_open():
        raise CircuitBreakerOpenError("熔断器开启，拒绝请求")

    client = get_client()
    params = _build_params(system_prompt, messages, tools, model, max_tokens, disable_thinking)

    response = await client.chat.completions.create(**params)
    await circuit_breaker.record_success()

    # 返回第一个 choice
    choice = response.choices[0]
    return {
        "content": choice.message.content or "",
        "tool_calls": choice.message.tool_calls or [],
        "finish_reason": choice.finish_reason,
    }


async def chat(
    system_prompt: str,
    messages: List[Dict[str, str]],
    tools: List[Dict[str, Any]] | None = None,
    model: str = "flash",
    max_tokens: int = 4096,
    disable_thinking: bool = False,
) -> dict:
    """
    DeepSeek 对话入口 — 包装了重试逻辑。

    返回:
        {"content": str, "tool_calls": list, "finish_reason": str}
    """
    try:
        return await retry_with_backoff(
            _call_api, system_prompt, messages, tools, model, max_tokens, disable_thinking
        )
    except RetryExhaustedError:
        logger.error("DeepSeek API 调用失败")
        raise
    except CircuitBreakerOpenError:
        logger.warning("DeepSeek 熔断中")
        raise


async def _log_tool_result(
    session_id: int | None,
    agent_type: str,
    tool_name: str,
    input_data: dict,
    output_data: str | None,
    success: bool,
    error_msg: str | None = None,
) -> None:
    """记录工具调用结果到 agent_action_logs（静默失败，不影响主流程）。"""
    try:
        from app.harness.l5_evaluation.logger import log_tool_call
        await log_tool_call(
            session_id=session_id,
            agent_type=agent_type,
            tool_name=tool_name,
            input_data=input_data,
            output_data=output_data if output_data else "",
            success=success,
            error_msg=error_msg,
        )
    except Exception as e:
        logger.warning(f"工具日志写入失败 [{tool_name}]: {e}")


async def chat_with_tools(
    system_prompt: str,
    messages: List[Dict[str, str]],
    tool_schemas: List[Dict[str, Any]],
    tool_executor,
    model: str = "flash",
    max_tokens: int = 4096,
    session_id: int | None = None,
    agent_type: str = "unknown",
) -> dict:
    """
    DeepSeek 带工具调用的对话 — 实现 Tool Call Loop。

    参数:
        system_prompt: 系统提示词
        messages: 对话历史
        tool_schemas: OpenAI 格式的工具定义列表
        tool_executor: 可调用的工具执行器 callable(name, args) -> result
        model: "pro" | "flash"
        max_tokens: 最大输出 token
        session_id: 会话 ID（用于审计日志）
        agent_type: Agent 类型（用于审计日志）

    返回:
        {"content": str, "tool_calls": list, "finish_reason": str}
        最终文本回复（工具已全部执行完毕）
    """
    local_messages = list(messages)  # 浅拷贝，避免修改原始列表
    tool_call_count = 0

    for round_num in range(1, MAX_TOOL_ROUNDS + 1):
        logger.info(f"DeepSeek 第 {round_num}/{MAX_TOOL_ROUNDS} 轮请求, model={_resolve_model(model)}, "
                    f"messages={len(local_messages)}, tools={len(tool_schemas)}")
        response = await chat(
            system_prompt=system_prompt,
            messages=local_messages,
            tools=tool_schemas,
            model=model,
            max_tokens=max_tokens,
        )

        # 没有工具调用 → 直接返回
        if not response["tool_calls"]:
            finish = response.get("finish_reason", "?")
            content_len = len(response.get("content", "") or "")
            logger.info(f"DeepSeek 最终回复: finish={finish}, content_len={content_len}, rounds={round_num}")
            return response

        # 执行工具调用
        tool_results = []
        for tc in response["tool_calls"]:
            func_name = tc.function.name
            try:
                import json
                func_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                func_args = {}

            logger.info(f"工具调用 [round={round_num}]: {func_name}({json.dumps(func_args, ensure_ascii=False)})")

            try:
                result = await tool_executor(func_name, func_args)
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": str(result),
                })
                # 记录工具调用成功日志
                await _log_tool_result(
                    session_id=session_id, agent_type=agent_type,
                    tool_name=func_name, input_data=func_args,
                    output_data=str(result), success=True,
                )
            except Exception as e:
                logger.error(f"工具执行失败 [{func_name}]: {e}")
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": f"Error: {e}",
                })
                # 记录工具调用失败日志
                await _log_tool_result(
                    session_id=session_id, agent_type=agent_type,
                    tool_name=func_name, input_data=func_args,
                    output_data=None, success=False, error_msg=str(e),
                )

        # 将 assistant 消息和工具结果追加到本地消息列表
        assistant_msg = {
            "role": "assistant",
            "content": response["content"] or "",
        }
        if response["tool_calls"]:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in response["tool_calls"]
            ]

        local_messages.append(assistant_msg)
        local_messages.extend(tool_results)

    # 达到最大轮次仍未得到最终回复
    logger.warning(f"工具调用达到最大轮次 {MAX_TOOL_ROUNDS}，请求最终总结")
    return await chat(
        system_prompt=system_prompt,
        messages=local_messages,
        tools=None,  # 不再提供工具
        model=model,
        max_tokens=max_tokens,
    )
