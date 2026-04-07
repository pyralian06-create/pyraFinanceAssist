"""
FastAPI 应用入口

职责：
- 初始化 FastAPI 应用
- 配置中间件（CORS、异常处理）
- 管理应用生命周期（启动、关闭）
- 挂载 API 路由
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.models import init_db
from app.config import settings
from app.services.market_info import sync_market_symbols

# ==================== 日志配置 ====================
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    """
    # ========== 启动阶段 ==========
    logger.info("🚀 启动金融助手应用...")

    # 1. 初始化数据库表
    try:
        init_db()
        logger.info("✅ 数据库初始化成功")
    except Exception as e:
        logger.error(f"❌ 数据库初始化失败: {e}")
        raise

    # 2. 异步同步全市场名单 (不阻塞启动)
    try:
        sync_market_symbols()
        logger.info("✅ 已触发市场名单后台同步任务")
    except Exception as e:
        logger.error(f"❌ 触发同步任务失败: {e}")

    logger.info("✅ 应用启动完成")
    yield

    # ========== 关闭阶段 ==========
    logger.info("🛑 关闭应用...")
    logger.info("✅ 应用关闭完成")


# ==================== 创建 FastAPI 应用 ====================
app = FastAPI(
    title="个人金融助手",
    description="轻量级持仓分析与盈亏工具 v0.1.0",
    version="0.1.0",
    lifespan=lifespan
)


# ==================== 中间件配置 ====================
# CORS 中间件：允许前端跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应改为具体域名列表
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 错误处理 ====================
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理器"""
    logger.error(f"未捕获异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "内部服务器错误"}
    )


# ==================== 健康检查 ====================
@app.get("/health", tags=["System"])
def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "service": "Personal Finance Assistant",
        "version": "0.1.0"
    }


@app.get("/", tags=["System"])
def root():
    """API 根路由"""
    return {
        "message": "个人金融助手 API",
        "docs": "http://localhost:8000/docs",
        "version": "0.1.0"
    }


# ==================== API 路由挂载 ====================
from app.api.trades import router as trades_router
from app.api.portfolio import router as portfolio_router
from app.api.market import router as market_router

app.include_router(trades_router, prefix="/api/trades", tags=["Trades"])
app.include_router(portfolio_router, prefix="/api/portfolio", tags=["Portfolio"])
app.include_router(market_router, prefix="/api/market", tags=["Market"])


# ==================== 应用入口 ====================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # 开发模式：代码变动自动重载
        log_level="info"
    )
