"""
数据库初始化模块

功能：
- 创建 SQLAlchemy engine 和 session factory
- 初始化 Base 类（所有 ORM 模型继承它）
- 提供 get_db() 依赖注入函数供 FastAPI 路由使用
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import settings

# ==================== 创建引擎 ====================
engine = create_engine(
    settings.database_url,
    echo=settings.echo_sql,  # 调试时打印 SQL 语句
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {}
)

# ==================== 创建会话工厂 ====================
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# ==================== 创建 Base 类 ====================
# 所有 ORM 模型都继承 Base
Base = declarative_base()


def get_db():
    """
    FastAPI 依赖注入函数

    使用方式：
    @app.get("/api/trades")
    def get_trades(db: Session = Depends(get_db)):
        trades = db.query(Trade).all()
        return trades
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    初始化数据库表

    在 FastAPI main.py 中调用：
    from app.models.database import init_db
    init_db()
    """
    Base.metadata.create_all(bind=engine)
