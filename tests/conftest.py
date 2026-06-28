"""
测试配置 — 共享 fixtures。
"""
import pytest
import asyncio
import os


@pytest.fixture(scope="session")
def event_loop():
    """Session 级别 event loop — 避免每次测试创建新 loop 导致 asyncpg 报错。"""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()
