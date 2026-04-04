"""
全局配置模块

读取 .env 文件，管理：
- 数据库连接
- 微信推送凭证
- 盯盘告警参数
- 日志级别
"""

from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """使用 Pydantic 管理配置，优先级：.env > 环境变量 > 默认值"""

    # ==================== 数据库 ====================
    database_url: str = "sqlite:///./finance_data.db"
    echo_sql: bool = False

    # ==================== 微信推送 ====================
    serverchan_sendkey: str = ""
    pushplus_token: str = ""

    # ==================== 盯盘告警 ====================
    alert_cooldown_minutes: int = 30  # 冷却时间（分钟）
    monitor_interval_seconds: int = 60  # 轮询频率（秒）

    # ==================== 数据缓存 ====================
    cache_ttl_seconds: int = 300  # 全市场行情缓存有效期（秒），根据接口返回时延调整
    cache_refresh_interval_seconds: int = 300  # 缓存定时刷新间隔（秒），默认 5 分钟

    # ==================== 日志 ====================
    log_level: str = "INFO"

    class Config:
        """从项目根目录的 .env 读取配置"""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False  # 环境变量不区分大小写


# 全局配置实例，整个项目导入 settings 使用
settings = Settings()
