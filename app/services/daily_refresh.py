"""
每日收益自动刷新服务

策略：
- 启动时检查今日 position_daily_marks 是否缺失，缺失则立即补跑一次
- 此后每天在 REFRESH_HOUR:REFRESH_MINUTE（本地时间，默认 15:30）自动触发
- 计算今日区间并调用 rebuild_daily_marks，写入 DB

说明：
- A 股 15:00 收盘，15:30 触发可保证收盘价已可用
- 港股/美股有时区差异，其历史 K 线次日才完整入库；当日港美数据为实时估算，次日重算后覆盖
- 若触发时行情接口不可用，异常会被捕获并记录日志，不影响应用运行
"""

import logging
import threading
import time
from datetime import date, datetime, timedelta

logger = logging.getLogger(__name__)

# 每日自动触发时间（本地时间）
REFRESH_HOUR = 15
REFRESH_MINUTE = 30

_thread: threading.Thread | None = None
_stop_event = threading.Event()

# ── 按需触发重算（流水写入后调用）─────────────────────────────
_rebuild_lock = threading.Lock()
_pending_start: date | None = None   # 待重算的最早起始日
_rebuild_running = False              # 是否有重算线程正在执行


def _seconds_until_next_trigger() -> float:
    """计算距离下一次触发时间的秒数（同日未到则等到今日，否则等到明日）。"""
    now = datetime.now()
    target = now.replace(hour=REFRESH_HOUR, minute=REFRESH_MINUTE, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _get_last_mark_date() -> date | None:
    """返回 position_daily_marks 中最新的 mark_date，无记录时返回 None。"""
    from app.models.database import SessionLocal
    from app.models.position_daily_mark import PositionDailyMark

    db = SessionLocal()
    try:
        row = db.query(PositionDailyMark.mark_date).order_by(
            PositionDailyMark.mark_date.desc()
        ).first()
        return row.mark_date if row else None
    except Exception:
        return None
    finally:
        db.close()


def _run_rebuild_since_last() -> None:
    """
    从库中最新记录日期起，补算至今日，填满中间所有缺失日期。
    若库中完全无记录，则只算今日。
    """
    from app.models.database import SessionLocal
    from app.pnl_engine.daily_pnl import rebuild_daily_marks

    today = date.today()
    last_date = _get_last_mark_date()
    start = last_date if last_date else today

    db = SessionLocal()
    try:
        logger.info(f"🔄 [daily_refresh] 补算收益区间 [{start} → {today}]...")
        count = rebuild_daily_marks(db, start=start, end=today)
        logger.info(f"✅ [daily_refresh] 完成，写入 {count} 行")
    except Exception as e:
        logger.error(f"❌ [daily_refresh] 刷新失败: {e}", exc_info=True)
    finally:
        db.close()


def _needs_refresh() -> bool:
    """今日数据缺失（或库中完全无记录）时返回 True。"""
    last_date = _get_last_mark_date()
    return last_date is None or last_date < date.today()


def _scheduler_loop() -> None:
    """后台调度主循环：启动补跑 + 定时触发。"""
    # 启动时若有缺失日期则立即补算
    if _needs_refresh():
        logger.info("📅 [daily_refresh] 检测到缺失数据，启动时立即补算...")
        _run_rebuild_since_last()
    else:
        logger.info("📅 [daily_refresh] 今日数据已存在，跳过启动补算")

    # 定时循环
    while not _stop_event.is_set():
        wait_seconds = _seconds_until_next_trigger()
        trigger_at = datetime.now() + timedelta(seconds=wait_seconds)
        logger.info(
            f"⏰ [daily_refresh] 下次刷新: {trigger_at.strftime('%Y-%m-%d %H:%M:%S')} "
            f"（{wait_seconds/3600:.1f}h 后）"
        )

        # 分段等待，每 60s 检查一次 stop_event
        elapsed = 0.0
        while elapsed < wait_seconds and not _stop_event.is_set():
            chunk = min(60.0, wait_seconds - elapsed)
            _stop_event.wait(chunk)
            elapsed += chunk

        if _stop_event.is_set():
            break

        _run_rebuild_since_last()


def trigger_rebuild_from(start: date) -> None:
    """
    流水写入后调用：以 start 为起点重算至今日，后台异步执行。

    并发安全：
    - 若当前已有重算在跑，更新 _pending_start（取更早日期），让其结束后接续执行
    - 若无重算在跑，立即启动新线程
    - 批量录入场景：多次调用只会累积 _pending_start，最终只跑一次（取最早日期）
    """
    global _pending_start, _rebuild_running

    with _rebuild_lock:
        # 取更早的日期，确保覆盖全部影响区间
        if _pending_start is None or start < _pending_start:
            _pending_start = start
        if _rebuild_running:
            # 已有线程在跑，它结束后会检查 _pending_start 并接续
            logger.info(f"ℹ️ [daily_refresh] 重算中，已合并 {start} 到待处理队列")
            return
        _rebuild_running = True

    threading.Thread(target=_run_pending_rebuild, daemon=True, name="on-demand-rebuild").start()


def _run_pending_rebuild() -> None:
    """消费 _pending_start，循环直到无待处理任务。"""
    global _pending_start, _rebuild_running

    while True:
        with _rebuild_lock:
            start = _pending_start
            _pending_start = None

        if start is None:
            with _rebuild_lock:
                _rebuild_running = False
            return

        from app.models.database import SessionLocal
        from app.pnl_engine.daily_pnl import rebuild_daily_marks

        today = date.today()
        db = SessionLocal()
        try:
            logger.info(f"🔄 [daily_refresh] 按需重算 [{start} → {today}]...")
            count = rebuild_daily_marks(db, start=start, end=today)
            logger.info(f"✅ [daily_refresh] 按需重算完成，写入 {count} 行")
        except Exception as e:
            logger.error(f"❌ [daily_refresh] 按需重算失败: {e}", exc_info=True)
        finally:
            db.close()


def start_daily_refresh() -> None:
    """在后台线程启动每日刷新调度器（幂等，重复调用无效）。"""
    global _thread
    if _thread and _thread.is_alive():
        logger.info("ℹ️ [daily_refresh] 调度器已在运行，跳过")
        return

    _stop_event.clear()
    _thread = threading.Thread(
        target=_scheduler_loop,
        name="daily-refresh-scheduler",
        daemon=True,
    )
    _thread.start()
    logger.info("✅ [daily_refresh] 每日收益刷新调度器已启动")


def stop_daily_refresh() -> None:
    """通知调度器停止（用于应用关闭时清理）。"""
    _stop_event.set()
    if _thread:
        _thread.join(timeout=5)
    logger.info("🛑 [daily_refresh] 调度器已停止")
