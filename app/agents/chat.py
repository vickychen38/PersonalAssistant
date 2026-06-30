"""
ChatAgent — 日常闲聊 + 联网搜索。

处理无法归类到 todo/accounting/health/retrospective 的消息。
使用 DeepSeek V4 Flash，支持联网搜索工具。
"""

import json
import logging
from typing import Any, Dict

from app.agents.base import BaseAgent
from app.services.deepseek import chat_with_tools

logger = logging.getLogger("agent.chat")

TOOL_MAP = {}


def _init_tool_map():
    global TOOL_MAP
    if TOOL_MAP:
        return
    from app.harness.l2_tools.web_search import web_search_tool
    from app.services.cconnect import send_text
    from app.config import config

    TOOL_MAP = {
        "web_search": lambda args: web_search_tool(args),
        "send_message": lambda args: send_text(args["content"], to_user=config.wechat_user_id),
    }


def _load_prompt() -> str:
    """加载 Chat Agent 系统提示词。"""
    return """你是逐念，Vicky 的个人 AI 助理。你现在处于闲聊模式。

关于 Vicky:
- 女生，长期健身（私教课），在科技行业工作
- 关注健康、效率、个人成长

你的风格:
- 温暖、简洁、有分寸感——像熟识的朋友，不是客服机器人
- 可以聊任何话题：日常生活、工作吐槽、情感、学习、八卦、科技、美食
- 用户问事实性问题（天气除外）时，用 web_search 搜索后回答
- 回复控制在 3-5 句以内，不要太长
- 适当使用 emoji 增加亲和力

联网搜索:
- 当用户问"查一下XX"、"XX是什么"、"最近有什么新闻"等需要外部信息的问题时，
  调用 web_search(query="关键词")
- 搜索结果会返回摘要和相关链接，你根据结果用口语化的方式回答
- 纯闲聊、问候、情绪表达不需要搜索
"""


class ChatAgent(BaseAgent):
    """闲聊 Agent — 处理日常对话和上网查询。"""

    agent_type = "chat"
    relevant_knowledge_categories = ["工作模式", "作息规律"]

    def __init__(self):
        _init_tool_map()

    async def run(
        self,
        user_message: str,
        session: Dict[str, Any] | None = None,
        triggered_by: str = "user",
    ) -> str:
        """执行闲聊对话。"""
        messages = []
        if session and session.get("messages"):
            messages = session["messages"]
        messages.append({"role": "user", "content": user_message})

        system_prompt = _load_prompt()

        # 注入用户画像
        user_context = await self.get_user_context()
        if user_context:
            system_prompt += f"\n\n{user_context}"

        # 构建工具 schema
        from app.harness.l2_tools.tool_schemas import build_tool_schemas
        tool_schemas = build_tool_schemas(["web_search", "send_message"])

        try:
            response = await chat_with_tools(
                system_prompt=system_prompt,
                messages=messages,
                tool_schemas=tool_schemas,
                tool_executor=self._execute_tool,
                model="flash",
                session_id=session.get("id") if session else None,
                agent_type=self.agent_type,
            )
            return response.get("content", "嗯？刚刚走神了，你再说一遍？😅")
        except Exception as e:
            logger.error(f"ChatAgent 执行失败: {e}", exc_info=True)
            return "抱歉，我脑子有点短路了，等一下再试试？"

    async def _execute_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        """执行工具调用。"""
        func = TOOL_MAP.get(tool_name)
        if func is None:
            return json.dumps({"error": f"未知工具: {tool_name}"})

        try:
            result = await func(args)
            return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            logger.error(f"ChatAgent 工具 [{tool_name}] 失败: {e}")
            return json.dumps({"error": str(e)})
