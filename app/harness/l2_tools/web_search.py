"""
联网搜索工具 — 供 ChatAgent 使用。

使用 DuckDuckGo Instant Answer API（免费、无需 API Key）。
"""

import logging
from typing import Any, Dict

import httpx

logger = logging.getLogger("web_search")

DDG_API = "https://api.duckduckgo.com/"


async def web_search(query: str) -> Dict[str, Any]:
    """
    搜索互联网信息。

    参数:
        query: 搜索关键词

    返回:
        {"abstract": str, "related_topics": [...], "results": [...]}
        或 {"error": str}
    """
    if not query or not query.strip():
        return {"error": "搜索关键词不能为空"}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                DDG_API,
                params={
                    "q": query.strip(),
                    "format": "json",
                    "no_html": 1,
                    "skip_disambig": 1,
                },
                headers={"User-Agent": "ZhuNian/1.0 PersonalAssistant"},
            )
            resp.raise_for_status()
            data = resp.json()

            # 提取关键信息
            abstract = data.get("AbstractText", "")
            abstract_url = data.get("AbstractURL", "")
            related = data.get("RelatedTopics", [])

            # 构建结果
            results = {
                "abstract": abstract,
                "abstract_url": abstract_url,
                "related": [],
            }

            for topic in related[:5]:
                if isinstance(topic, dict):
                    results["related"].append({
                        "text": topic.get("Text", ""),
                        "url": topic.get("FirstURL", ""),
                    })

            if not abstract and not results["related"]:
                return {
                    "abstract": f"未找到「{query}」的相关结果。试试换一个更具体的关键词？",
                    "abstract_url": "",
                    "related": [],
                }

            logger.info(f"web_search 完成: query='{query}', abstract_len={len(abstract)}")
            return results

    except httpx.HTTPError as e:
        logger.error(f"web_search 请求失败: {e}")
        return {"error": f"搜索请求失败: {e}"}
    except Exception as e:
        logger.error(f"web_search 异常: {e}")
        return {"error": f"搜索失败: {e}"}


async def web_search_tool(args: Dict[str, Any]) -> str:
    """
    Agent 工具入口 — 执行搜索并格式化为文本。
    """
    import json

    query = args.get("query", "")
    result = await web_search(query)

    if "error" in result:
        return json.dumps(result, ensure_ascii=False)

    # 格式化为可读文本
    parts = []
    if result["abstract"]:
        parts.append(f"📖 {result['abstract']}")
        if result["abstract_url"]:
            parts.append(f"   来源: {result['abstract_url']}")

    for i, r in enumerate(result["related"][:3], 1):
        parts.append(f"{i}. {r['text']}")
        if r["url"]:
            parts.append(f"   {r['url']}")

    return "\n\n".join(parts) if parts else f"未找到「{query}」的相关信息。"
