"""
SQLAlchemy 2.0 async 引擎 + session 工厂。

使用 asyncpg 驱动连接 PostgreSQL。
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import config


# 异步引擎
engine = create_async_engine(
    config.database_url,
    echo=False,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
)

# 异步 session 工厂
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """ORM 模型基类，所有模型继承自此。"""
    pass


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：获取数据库 session。

    用法:
        @app.get("/")
        async def route(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def check_db_connection() -> bool:
    """启动时检查数据库连通性。"""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        import logging
        logging.getLogger("database").error(f"数据库连接失败: {e}")
        return False
