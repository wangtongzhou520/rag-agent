"""M5 本地容量基准：Redis 限流、PG 队列与 SSE，不访问模型供应商。"""

import argparse
import asyncio
import json
import platform
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import asyncpg
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.framework.config import DatasourceSettings, get_settings
from app.framework.db import init_schema
from app.framework.sse import MessageDeltaType, SseSender
from app.framework.task_queue import TaskQueue
from app.rag.ratelimit import FairDistributedRateLimiter


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    name: str
    operations: int
    elapsed_seconds: float
    throughput_per_second: float
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    peak_concurrency: int | None = None
    rejected: int = 0


def percentile(values: list[float], quantile: float) -> float:
    """使用线性插值计算分位数；输入单位保持不变。"""
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * min(1.0, max(0.0, quantile))
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def summarize(
    name: str,
    operations: int,
    elapsed: float,
    latencies_ms: list[float],
    *,
    peak_concurrency: int | None = None,
    rejected: int = 0,
) -> BenchmarkResult:
    return BenchmarkResult(
        name=name,
        operations=operations,
        elapsed_seconds=round(elapsed, 6),
        throughput_per_second=round(operations / elapsed if elapsed else 0, 2),
        latency_p50_ms=round(percentile(latencies_ms, 0.50), 3),
        latency_p95_ms=round(percentile(latencies_ms, 0.95), 3),
        latency_p99_ms=round(percentile(latencies_ms, 0.99), 3),
        peak_concurrency=peak_concurrency,
        rejected=rejected,
    )


async def benchmark_redis(
    *,
    requests: int,
    permits: int,
    work_ms: float,
) -> BenchmarkResult:
    settings = get_settings()
    redis = Redis(
        host=settings.redis.host,
        port=settings.redis.port,
        db=settings.redis.database,
        password=settings.redis.password or None,
        decode_responses=True,
    )
    name = f"{settings.redis.key_prefix}benchmark:fair:{uuid.uuid4()}"
    limiters = [
        FairDistributedRateLimiter(
            redis,
            name=name,
            max_concurrent=permits,
            max_wait_seconds=60,
            lease_seconds=120,
            poll_interval_ms=50,
        )
        for _ in range(2)
    ]
    for limiter in limiters:
        await limiter.start()
    active = 0
    peak = 0
    rejected = 0
    latencies: list[float] = []
    state_lock = asyncio.Lock()

    async def execute(index: int) -> None:
        nonlocal active, peak, rejected
        limiter = limiters[index % len(limiters)]
        started = time.perf_counter()
        permit = await limiter.acquire(f"request-{index}")
        latencies.append((time.perf_counter() - started) * 1000)
        if permit is None:
            rejected += 1
            return
        async with state_lock:
            active += 1
            peak = max(peak, active)
        await asyncio.sleep(work_ms / 1000)
        async with state_lock:
            active -= 1
        await limiter.release(permit)

    started = time.perf_counter()
    try:
        await asyncio.gather(*(execute(index) for index in range(requests)))
        elapsed = time.perf_counter() - started
        if peak > permits:
            raise RuntimeError(f"Redis limiter over-issued: peak={peak}, permits={permits}")
        if rejected:
            raise RuntimeError(f"Redis limiter unexpectedly rejected {rejected} requests")
        return summarize(
            "redis_fair_limiter",
            requests,
            elapsed,
            latencies,
            peak_concurrency=peak,
            rejected=rejected,
        )
    finally:
        for limiter in limiters:
            await limiter.close()
        keys = [key async for key in redis.scan_iter(f"{name}*")]
        if keys:
            await redis.delete(*keys)
        await redis.aclose()


async def _with_temporary_database(
    operation: Callable[[DatasourceSettings], Awaitable[BenchmarkResult]],
) -> BenchmarkResult:
    source = get_settings().datasource
    database = f"ragent_bench_{uuid.uuid4().hex[:12]}"
    admin = await asyncpg.connect(
        host=source.host,
        port=source.port,
        database="postgres",
        user=source.username,
        password=source.password or None,
    )
    try:
        await admin.execute(f'CREATE DATABASE "{database}"')
    finally:
        await admin.close()
    temporary = DatasourceSettings(**{**source.model_dump(), "database": database})
    try:
        return await operation(temporary)
    finally:
        admin = await asyncpg.connect(
            host=source.host,
            port=source.port,
            database="postgres",
            user=source.username,
            password=source.password or None,
        )
        try:
            await admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = $1 AND pid <> pg_backend_pid()",
                database,
            )
            await admin.execute(f'DROP DATABASE "{database}"')
        finally:
            await admin.close()


async def benchmark_postgres(*, tasks: int, workers: int) -> BenchmarkResult:
    async def run(source: DatasourceSettings) -> BenchmarkResult:
        engine = create_async_engine(source.url, pool_pre_ping=True)
        try:
            await init_schema(engine)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            enqueue_started = time.perf_counter()
            async with sessions.begin() as session:
                for index in range(tasks):
                    await TaskQueue.enqueue(
                        session,
                        "benchmark-probe",
                        f"probe:{index}",
                        {"index": index},
                    )
            enqueue_elapsed = time.perf_counter() - enqueue_started
            queues = [TaskQueue(engine) for _ in range(workers)]
            latencies: list[float] = []
            claimed_ids: list[int] = []

            async def drain(index: int) -> None:
                queue = queues[index]
                while True:
                    claimed_started = time.perf_counter()
                    task = await queue.claim(f"benchmark-worker-{index}")
                    if task is None:
                        return
                    await queue.succeed(task.id, f"benchmark-worker-{index}")
                    latencies.append((time.perf_counter() - claimed_started) * 1000)
                    claimed_ids.append(task.id)

            started = time.perf_counter()
            await asyncio.gather(*(drain(index) for index in range(workers)))
            elapsed = time.perf_counter() - started
            if len(claimed_ids) != tasks or len(set(claimed_ids)) != tasks:
                raise RuntimeError("PG queue lost or duplicated tasks")
            result = summarize(
                "postgres_task_queue",
                tasks,
                elapsed,
                latencies,
                peak_concurrency=workers,
            )
            return BenchmarkResult(
                **{
                    **asdict(result),
                    "elapsed_seconds": round(elapsed + enqueue_elapsed, 6),
                    "throughput_per_second": round(
                        tasks / (elapsed + enqueue_elapsed), 2
                    ),
                }
            )
        finally:
            await engine.dispose()

    return await _with_temporary_database(run)


async def benchmark_sse(*, messages: int, chunk_size: int) -> BenchmarkResult:
    sender = SseSender()
    latencies: list[float] = []

    async def produce() -> None:
        for _ in range(messages):
            started = time.perf_counter()
            await sender.send_message(MessageDeltaType.RESPONSE, "性能测试", chunk_size)
            latencies.append((time.perf_counter() - started) * 1000)
        await sender.done()

    started = time.perf_counter()
    producer = asyncio.create_task(produce())
    frames = 0
    async for _ in sender.stream():
        frames += 1
    await producer
    elapsed = time.perf_counter() - started
    if frames != messages + 1:
        raise RuntimeError(f"SSE frame mismatch: expected={messages + 1}, actual={frames}")
    return summarize("sse_sender", messages, elapsed, latencies)


def markdown_report(payload: dict[str, Any]) -> str:
    parameters = payload["parameters"]
    lines = [
        "# M5 容量与性能基准",
        "",
        f"- 时间：{payload['generatedAt']}",
        f"- 平台：{payload['platform']}",
        f"- Python：{payload['python']}",
        "- 范围：本地 Redis、临时 PostgreSQL 数据库、内存 SSE；不调用模型供应商",
        f"- 参数：`{json.dumps(parameters, ensure_ascii=False, sort_keys=True)}`",
        "",
        "| 场景 | 操作数 | 总耗时(s) | 吞吐(op/s) | P50(ms) | P95(ms) | P99(ms) | 峰值并发 | 拒绝 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in payload["results"]:
        lines.append(
            "| {name} | {operations} | {elapsed_seconds} | "
            "{throughput_per_second} | {latency_p50_ms} | {latency_p95_ms} | "
            "{latency_p99_ms} | {peak_concurrency} | {rejected} |".format(
                **{**result, "peak_concurrency": result["peak_concurrency"] or "-"}
            )
        )
    lines.extend(
        [
            "",
            "> 该结果是开发机基线，不等同于生产 SLA。模型首包与生成速度需由评测批次单独测量。",
            "",
        ]
    )
    return "\n".join(lines)


async def run(args: argparse.Namespace) -> dict[str, Any]:
    results: list[BenchmarkResult] = []
    if args.target in ("all", "redis"):
        results.append(
            await benchmark_redis(
                requests=args.redis_requests,
                permits=args.redis_permits,
                work_ms=args.redis_work_ms,
            )
        )
    if args.target in ("all", "postgres"):
        results.append(
            await benchmark_postgres(tasks=args.pg_tasks, workers=args.pg_workers)
        )
    if args.target in ("all", "sse"):
        results.append(
            await benchmark_sse(messages=args.sse_messages, chunk_size=args.sse_chunk_size)
        )
    return {
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "platform": f"{platform.system()} {platform.release()} {platform.machine()}",
        "python": platform.python_version(),
        "parameters": {
            "target": args.target,
            "redisRequests": args.redis_requests,
            "redisPermits": args.redis_permits,
            "redisWorkMs": args.redis_work_ms,
            "pgTasks": args.pg_tasks,
            "pgWorkers": args.pg_workers,
            "sseMessages": args.sse_messages,
            "sseChunkSize": args.sse_chunk_size,
        },
        "results": [asdict(result) for result in results],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("all", "redis", "postgres", "sse"), default="all")
    parser.add_argument("--redis-requests", type=int, default=200)
    parser.add_argument("--redis-permits", type=int, default=10)
    parser.add_argument("--redis-work-ms", type=float, default=10)
    parser.add_argument("--pg-tasks", type=int, default=200)
    parser.add_argument("--pg-workers", type=int, default=8)
    parser.add_argument("--sse-messages", type=int, default=10_000)
    parser.add_argument("--sse-chunk-size", type=int, default=16)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if min(
        args.redis_requests,
        args.redis_permits,
        args.pg_tasks,
        args.pg_workers,
        args.sse_messages,
        args.sse_chunk_size,
    ) <= 0:
        raise SystemExit("all counts must be greater than zero")
    payload = asyncio.run(run(args))
    rendered = markdown_report(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
