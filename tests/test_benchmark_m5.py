"""M5 基准脚本的纯函数与内存 SSE 测试。"""

from argparse import Namespace

from scripts.benchmark_m5 import benchmark_sse, markdown_report, percentile, run


def test_percentile_uses_linear_interpolation() -> None:
    assert percentile([], 0.95) == 0
    assert percentile([1, 2, 3, 4, 5], 0.5) == 3
    assert percentile([0, 10], 0.95) == 9.5


async def test_sse_benchmark_counts_frames() -> None:
    result = await benchmark_sse(messages=100, chunk_size=16)

    assert result.name == "sse_sender"
    assert result.operations == 100
    assert result.throughput_per_second > 0
    assert result.rejected == 0


async def test_run_and_markdown_can_select_sse_only() -> None:
    payload = await run(
        Namespace(
            target="sse",
            redis_requests=1,
            redis_permits=1,
            redis_work_ms=1,
            pg_tasks=1,
            pg_workers=1,
            sse_messages=10,
            sse_chunk_size=16,
        )
    )
    report = markdown_report(payload)

    assert len(payload["results"]) == 1
    assert payload["results"][0]["name"] == "sse_sender"
    assert payload["parameters"]["target"] == "sse"
    assert payload["parameters"]["sseMessages"] == 10
    assert "不调用模型供应商" in report
    assert '"sseMessages": 10' in report
    assert "sse_sender" in report
