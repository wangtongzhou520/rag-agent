from datetime import datetime, timedelta, timezone

from app.rag.trace.query import RagTraceQueryService


def test_trace_time_serialization_marks_naive_database_values_as_utc() -> None:
    value = datetime.fromisoformat("2026-09-02T12:34:56.789123")

    assert RagTraceQueryService._epoch_millis(value) == 1_788_352_496_789


def test_trace_time_serialization_normalizes_aware_values_to_utc() -> None:
    china_time = datetime(
        2026,
        9,
        2,
        20,
        34,
        56,
        tzinfo=timezone(timedelta(hours=8)),
    )

    assert RagTraceQueryService._epoch_millis(china_time) == 1_788_352_496_000
