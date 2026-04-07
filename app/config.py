"""
全局配置模块

读取 .env 文件，管理：
- 数据库连接
- 日志级别
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """使用 Pydantic 管理配置，优先级：.env > 环境变量 > 默认值"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # 忽略 .env 中已废弃的键（如旧版盯盘相关变量）
    )

    # ==================== 数据库 ====================
    database_url: str = "sqlite:///./finance_data.db"
    echo_sql: bool = False

    # ==================== 数据缓存 ====================
    cache_ttl_seconds: int = 300  # 全市场行情缓存有效期（秒），根据接口返回时延调整
    cache_refresh_interval_seconds: int = 300  # 缓存定时刷新间隔（秒），默认 5 分钟

    # ==================== 日志 ====================
    log_level: str = "INFO"


# 全局配置实例，整个项目导入 settings 使用
settings = Settings()
