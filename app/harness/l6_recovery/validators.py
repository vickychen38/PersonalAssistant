"""
Pydantic v2 输入校验 — 所有工具输入参数 schema。

提供通用的校验装饰器和错误处理，不合法输入返回结构化错误给 Agent 修正。
"""

import logging
from typing import Type, Any, Dict, Tuple

from pydantic import BaseModel, ValidationError

logger = logging.getLogger("validators")


class ValidationResult(BaseModel):
    """校验结果。"""
    valid: bool
    data: Dict[str, Any] | None = None
    errors: list[str] = []


def validate_input(schema: Type[BaseModel], raw_input: Dict[str, Any]) -> ValidationResult:
    """
    使用 Pydantic v2 schema 校验工具输入。

    参数:
        schema: Pydantic BaseModel 子类
        raw_input: 原始输入字典

    返回:
        ValidationResult: valid=True 时 data 为校验通过后的字典，
                          valid=False 时 errors 包含错误描述列表
    """
    try:
        instance = schema(**raw_input)
        return ValidationResult(
            valid=True,
            data=instance.model_dump(),
        )
    except ValidationError as e:
        error_messages = []
        for error in e.errors():
            loc = " → ".join(str(loc) for loc in error["loc"])
            msg = error["msg"]
            error_messages.append(f"{loc}: {msg}")
        logger.warning(f"输入校验失败: {error_messages}")
        return ValidationResult(valid=False, errors=error_messages)


def format_validation_errors(errors: list[str]) -> str:
    """将校验错误列表格式化为 Agent 可理解的文本。"""
    return "输入参数有误：\n" + "\n".join(f"  - {e}" for e in errors)
