"""数据库引擎与会话工厂。

默认使用 SQLite（零依赖即可试跑）；将 DATABASE_URL 指向 PostgreSQL 后，
同一套 SQLAlchemy 模型直接落到 PostgreSQL（原始文件索引、相似关系、归并操作均在此）。
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from . import config

_connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    config.DATABASE_URL,
    connect_args=_connect_args,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
