"""
动态建表工具 — 用户需求驱动的 schema 扩展。

流程：
  1. Agent 发现需要新表 → 组织提案消息给用户
  2. 用户确认 → 执行 CREATE TABLE
  3. 禁止 DROP/ALTER/TRUNCATE/DELETE（由 L2 guards 保护）
"""

import logging
from typing import Any, Dict, List

from pydantic import BaseModel, Field
from sqlalchemy import text

from app.database import async_session_factory
from app.harness.l2_tools.guards import sql_guard

logger = logging.getLogger("schema_tools")


class CreateTableInput(BaseModel):
    table_name: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-z][a-z0-9_]*$")
    columns: List[Dict[str, str]]  # [{"name": "...", "type": "...", "nullable": "true/false"}]


def _validate_column_type(col_type: str) -> bool:
    """校验列类型是否安全。只允许白名单内的类型。"""
    allowed = {
        "INTEGER", "BIGINT", "SMALLINT", "SERIAL",
        "VARCHAR", "TEXT", "CHAR",
        "DECIMAL", "NUMERIC",
        "DATE", "TIME", "TIMESTAMP",
        "BOOLEAN",
        "JSONB",
        "FLOAT", "DOUBLE PRECISION",
    }
    upper = col_type.upper().split("(")[0].strip()
    return upper in allowed


async def propose_table(
    table_name: str,
    columns: List[Dict[str, str]],
    purpose: str,
) -> str:
    """
    生成建表提案消息（不执行 SQL）。

    返回:
        提案消息文本，用于发给用户确认
    """
    col_lines = []
    for c in columns:
        nullable = "NULL" if c.get("nullable", "true") == "true" else "NOT NULL"
        col_lines.append(f"  • {c['name']} ({c['type']}) {nullable}")

    return (
        f"我发现需要记录「{purpose}」数据，现有表里没有合适的地方存。\n\n"
        f"我想新建一个表 `{table_name}`，包含：\n"
        + "\n".join(col_lines) +
        f"\n\n建完后可以{purpose}。\n"
        f"可以创建吗？"
    )


async def create_table(data: CreateTableInput) -> Dict[str, Any]:
    """
    执行 CREATE TABLE（用户确认后调用）。

    安全检查:
      1. 表名必须符合命名规范
      2. 列类型必须是白名单内类型
      3. 通过 sql_guard 检查
    """
    # 校验列类型
    for col in data.columns:
        if not _validate_column_type(col["type"]):
            return {"error": f"不安全的列类型: {col['type']}"}

    # 构建 SQL
    col_defs = []
    for col in data.columns:
        nullable = "NULL" if col.get("nullable", "true") == "true" else "NOT NULL"
        col_defs.append(f"  {col['name']} {col['type']} {nullable}")

    sql = f"CREATE TABLE {data.table_name} (\n" + ",\n".join(
        ["  id SERIAL PRIMARY KEY"] + col_defs +
        ["  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"]
    ) + "\n)"

    # Guard 检查
    sql_guard(sql)

    async with async_session_factory() as session:
        try:
            await session.execute(text(sql))
            await session.commit()
            logger.info(f"动态建表成功: {data.table_name}")
            return {
                "table_name": data.table_name,
                "columns": len(data.columns) + 2,  # +id +created_at
                "status": "created",
            }
        except Exception as e:
            logger.error(f"动态建表失败: {e}")
            return {"error": str(e)}
