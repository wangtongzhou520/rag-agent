"""自研 PG 队列 worker 骨架（python -m app.worker）。

设计见 00 文档 §5.3：t_async_task 表即队列，FOR UPDATE SKIP LOCKED 原子 claim，
LISTEN/NOTIFY 唤醒 + 短轮询兜底，asyncio 定时器承载 cron（定时刷新 10s / 卡死恢复 60s）。
"""

import asyncio
import signal

from app.framework.config import get_settings
from app.framework.logging import get_logger, init_logging

logger = get_logger(__name__)

HEARTBEAT_INTERVAL_S = 1.0


async def run() -> None:
    settings = get_settings()
    init_logging(settings.logging.level)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:  # Windows 不支持 add_signal_handler
            signal.signal(sig, lambda *_: stop_event.set())

    # TODO(M2): 连接 PG（LISTEN ragent_task）与 Redis（消费幂等键）
    # TODO(M2): 注册任务 handler（入库执行 / 反馈落库 / 会话摘要）
    # TODO(M2): claim 循环：SELECT ... FOR UPDATE SKIP LOCKED，PENDING -> RUNNING（owner + 租约）
    # TODO(M2): asyncio 定时器 cron：定时刷新扫描(10s)、卡死恢复(60s，RUNNING 租约超时重置 PENDING)

    logger.info("worker started")
    while not stop_event.is_set():
        logger.info("worker heartbeat")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=HEARTBEAT_INTERVAL_S)
        except TimeoutError:
            pass
    logger.info("worker stopped")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
