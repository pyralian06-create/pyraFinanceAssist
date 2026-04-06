import logging
import threading
from datetime import datetime
from typing import List, Dict, Any
import pandas as pd

try:
    import akshare as ak
except ImportError:
    ak = None

try:
    from pypinyin import pinyin, Style
except ImportError:
    pinyin = None

from app.models.database import SessionLocal
from app.models.market_symbol import MarketSymbol
from sqlalchemy.dialects.sqlite import insert

logger = logging.getLogger(__name__)

def get_pinyin_abbr(text: str) -> str:
    """生成中文文本的拼音首字母缩写"""
    if not pinyin or not text:
        return ""
    try:
        # 如 "贵州茅台" -> "gzmt"
        chars = pinyin(text, style=Style.FIRST_LETTER)
        return "".join([c[0] for c in chars if c]).lower()
    except Exception:
        return ""

def sync_market_symbols() -> None:
    """
    全量同步市场标的名录（后台任务）

    聚合：A股 (sh/sz/bj), ETF, LOF, 开放式基金, 港股, 美股
    """
    if ak is None:
        logger.error("❌ 同步失败: akshare 未安装")
        return

    def run_sync():
        start_time = datetime.now()
        logger.info("🔄 [后台] 开始同步全市场标的名录...")
        
        all_symbols = [] 

        # 1. A股名单 (沪深京)
        try:
            # 改用 stock_zh_a_spot_em 接口获取名单，极其稳定
            df_a = ak.stock_zh_a_spot_em()
            for _, row in df_a.iterrows():
                symbol = str(row['代码'])
                name = str(row['名称'])
                all_symbols.append({
                    "symbol": symbol,
                    "name": name,
                    "asset_type": "STOCK_A",
                    "pinyin": get_pinyin_abbr(name),
                    "is_active": True
                })
            logger.info(f"✅ 已抓取 A股 名单 (EM接口): {len(df_a)} 只")
        except Exception as e:
            logger.error(f"⚠️ A股名单抓取失败: {e}")

        # 2. ETF名单
        try:
            df_etf = ak.fund_etf_spot_em()
            for _, row in df_etf.iterrows():
                symbol = str(row['代码'])
                name = str(row['名称'])
                all_symbols.append({
                    "symbol": symbol,
                    "name": name,
                    "asset_type": "FUND_ETF",
                    "pinyin": get_pinyin_abbr(name),
                    "is_active": True
                })
            logger.info(f"✅ 已抓取 ETF 名单: {len(df_etf)} 只")
        except Exception as e:
            logger.error(f"⚠️ ETF名单抓取失败: {e}")

        # 3. LOF名单
        try:
            df_lof = ak.fund_lof_spot_em()
            for _, row in df_lof.iterrows():
                symbol = str(row['代码'])
                name = str(row['名称'])
                all_symbols.append({
                    "symbol": symbol,
                    "name": name,
                    "asset_type": "FUND_LOF",
                    "pinyin": get_pinyin_abbr(name),
                    "is_active": True
                })
            logger.info(f"✅ 已抓取 LOF 名单: {len(df_lof)} 只")
        except Exception as e:
            logger.error(f"⚠️ LOF名单抓取失败: {e}")

        # 4. 开放式基金
        try:
            df_open = ak.fund_open_fund_daily_em()
            for _, row in df_open.iterrows():
                symbol = str(row['基金代码'])
                name = str(row['基金简称'])
                all_symbols.append({
                    "symbol": symbol,
                    "name": name,
                    "asset_type": "FUND_OPEN",
                    "pinyin": get_pinyin_abbr(name),
                    "is_active": True
                })
            logger.info(f"✅ 已抓取 开放式基金 名单: {len(df_open)} 只")
        except Exception as e:
            logger.error(f"⚠️ 开放式基金名单抓取失败: {e}")

        # 5. 港股名单
        try:
            df_hk = ak.stock_hk_spot_em()
            for _, row in df_hk.iterrows():
                code = str(row['代码'])  # AkShare 返回 5位零填充格式，如 00700
                symbol = code.lstrip('0') or '0'  # 去掉前导零，至少保留一个 0；如 00700 -> 0700
                name = str(row['名称'])
                all_symbols.append({
                    "symbol": symbol,
                    "name": name,
                    "asset_type": "STOCK_HK",
                    "pinyin": get_pinyin_abbr(name),
                    "is_active": True
                })
            logger.info(f"✅ 已抓取 港股 名单: {len(df_hk)} 只")
        except Exception as e:
            logger.error(f"⚠️ 港股名单抓取失败: {e}")

        # 6. 美股名单
        try:
            df_us = ak.stock_us_spot_em()
            for _, row in df_us.iterrows():
                code = str(row['代码'])  # AkShare 返回 编码.ticker 格式，如 105.AAPL
                # 提取纯 ticker（AAPL）
                symbol = code.split('.')[-1] if '.' in code else code
                name = str(row['名称'])    # 东方财富给的中文名，如 苹果
                all_symbols.append({
                    "symbol": symbol,
                    "name": name,
                    "asset_type": "STOCK_US",
                    "pinyin": get_pinyin_abbr(name),
                    "is_active": True
                })
            logger.info(f"✅ 已抓取 美股 名单: {len(df_us)} 只")
        except Exception as e:
            logger.error(f"⚠️ 美股名单抓取失败: {e}")

        if not all_symbols:
            logger.error("❌ 同步完成但未发现任何数据，跳过更新")
            return

        db = SessionLocal()
        try:
            # 批量入库 (分批提高效率)
            batch_size = 500
            for i in range(0, len(all_symbols), batch_size):
                batch = all_symbols[i : i + batch_size]
                
                # 构建 SQLite UPSERT 语句
                stmt = insert(MarketSymbol).values(batch)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['asset_type', 'symbol'],
                    set_={
                        "name": stmt.excluded.name,
                        "asset_type": stmt.excluded.asset_type,
                        "pinyin": stmt.excluded.pinyin,
                        "is_active": True,
                        "updated_at": datetime.now()
                    }
                )
                db.execute(stmt)
            db.commit()
            
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(f"✨ 全市场名单同步完成！共 {len(all_symbols)} 个活跃标的，耗时 {elapsed:.1f}s")
        except Exception as e:
            db.rollback()
            logger.error(f"❌ 数据库写入失败: {e}")
        finally:
            db.close()

    thread = threading.Thread(target=run_sync, daemon=True)
    thread.start()
