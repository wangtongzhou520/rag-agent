"""管理控制台 Dashboard 实时统计。"""

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.framework.result import Results
from app.rag.models import Conversation, Message, RagTraceRun
from app.rag.pipeline.stream_chat import EMPTY_RETRIEVAL_TEXT
from app.system.auth.deps import require_admin
from app.system.user.models import User

NO_DOCUMENT_ANSWER = EMPTY_RETRIEVAL_TEXT
SLOW_REQUEST_MS = 20_000
_WINDOW_PATTERN = re.compile(r"^(\d+)([hHdD])$")
_TREND_METRICS = {"sessions", "messages", "activeusers", "avglatency", "quality"}

router = APIRouter(
    prefix="/admin/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_admin)],
)


@dataclass(frozen=True)
class DashboardWindow:
    label: str
    duration: timedelta


def parse_window(value: str | None, default: str) -> DashboardWindow:
    """解析 Nh/Nd 窗口；空值或非法值回落到调用方默认值。"""
    candidate = value.strip() if value else ""
    matched = _WINDOW_PATTERN.fullmatch(candidate)
    if matched and int(matched.group(1)) > 0:
        amount = int(matched.group(1))
        unit = matched.group(2).lower()
        try:
            duration = timedelta(hours=amount) if unit == "h" else timedelta(days=amount)
        except OverflowError:
            matched = None
        else:
            return DashboardWindow(candidate, duration)
    fallback = _WINDOW_PATTERN.fullmatch(default)
    if fallback is None:  # pragma: no cover - 仅防止内部默认值配置错误
        raise ValueError(f"invalid default dashboard window: {default}")
    amount = int(fallback.group(1))
    duration = timedelta(hours=amount) if fallback.group(2).lower() == "h" else timedelta(days=amount)
    return DashboardWindow(default, duration)


def _round1(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _rate(numerator: int, denominator: int) -> float:
    return _round1(numerator / denominator * 100) if denominator > 0 else 0.0


def _delta_pct(current: int, previous: int) -> float | None:
    return _round1((current - previous) / previous * 100) if previous > 0 else None


def _rounded_average(values: list[int]) -> int:
    if not values:
        return 0
    return int(Decimal(sum(values) / len(values)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1))]


class DashboardService:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def overview(self, window_value: str | None = None) -> dict:
        window = parse_window(window_value, "24h")
        now = datetime.now(UTC).replace(tzinfo=None)
        start = now - window.duration
        previous_start = start - window.duration

        async with self._sessions() as session:
            total_users = await self._count(session, User, User.deleted == 0)
            new_users = await self._count_between(session, User, previous_start=start, end=now)
            total_sessions = await self._count(session, Conversation, Conversation.deleted == 0)
            current_sessions = await self._count_between(
                session, Conversation, previous_start=start, end=now
            )
            previous_sessions = await self._count_between(
                session, Conversation, previous_start=previous_start, end=start
            )
            total_messages = await self._count(session, Message, Message.deleted == 0)
            current_messages = await self._count_between(
                session, Message, previous_start=start, end=now
            )
            previous_messages = await self._count_between(
                session, Message, previous_start=previous_start, end=start
            )
            current_active = await self._active_users(session, start, now)
            previous_active = await self._active_users(session, previous_start, start)

        return {
            "window": window.label,
            "compareWindow": f"prev_{window.label}",
            "updatedAt": _epoch_millis(now),
            "kpis": {
                "totalUsers": self._kpi(total_users, new_users),
                "activeUsers": self._kpi(
                    current_active,
                    current_active - previous_active,
                    _delta_pct(current_active, previous_active),
                ),
                "totalSessions": self._kpi(total_sessions, current_sessions),
                "sessions24h": self._kpi(
                    current_sessions,
                    current_sessions - previous_sessions,
                    _delta_pct(current_sessions, previous_sessions),
                ),
                "totalMessages": self._kpi(total_messages, current_messages),
                "messages24h": self._kpi(
                    current_messages,
                    current_messages - previous_messages,
                    _delta_pct(current_messages, previous_messages),
                ),
            },
        }

    async def performance(self, window_value: str | None = None) -> dict:
        window = parse_window(window_value, "24h")
        now = datetime.now(UTC).replace(tzinfo=None)
        start = now - window.duration
        async with self._sessions() as session:
            completed_rows = (
                await session.execute(
                    select(RagTraceRun.status, func.count())
                    .where(
                        RagTraceRun.deleted == 0,
                        RagTraceRun.start_time >= start,
                        RagTraceRun.start_time < now,
                        RagTraceRun.status.in_(("SUCCESS", "ERROR")),
                    )
                    .group_by(RagTraceRun.status)
                )
            ).all()
            durations = list(
                await session.scalars(
                    select(RagTraceRun.duration_ms).where(
                        RagTraceRun.deleted == 0,
                        RagTraceRun.start_time >= start,
                        RagTraceRun.start_time < now,
                        RagTraceRun.status == "SUCCESS",
                        RagTraceRun.duration_ms > 0,
                    )
                )
            )
            assistant_total = await self._count(
                session,
                Message,
                Message.deleted == 0,
                Message.role == "assistant",
                Message.create_time >= start,
                Message.create_time < now,
            )
            no_document = await self._count(
                session,
                Message,
                Message.deleted == 0,
                Message.role == "assistant",
                Message.content == NO_DOCUMENT_ANSWER,
                Message.create_time >= start,
                Message.create_time < now,
            )

        statuses = {status: int(count) for status, count in completed_rows}
        success = statuses.get("SUCCESS", 0)
        errors = statuses.get("ERROR", 0)
        completed = success + errors
        normalized_durations = [int(value) for value in durations if value is not None]
        return {
            "window": window.label,
            "avgLatencyMs": _rounded_average(normalized_durations),
            "p95LatencyMs": _p95(normalized_durations),
            "successRate": _rate(success, completed),
            "errorRate": _rate(errors, completed),
            "noDocRate": _rate(no_document, assistant_total),
            "slowRate": _rate(
                sum(value > SLOW_REQUEST_MS for value in normalized_durations),
                len(normalized_durations),
            ),
        }

    async def trends(
        self,
        metric_value: str,
        window_value: str | None = None,
        granularity_value: str | None = None,
    ) -> dict:
        window = parse_window(window_value, "7d")
        metric = metric_value.strip().lower()
        granularity = self._granularity(granularity_value, window.duration)
        local_timezone = datetime.now().astimezone().tzinfo or UTC
        buckets = self._buckets(datetime.now(local_timezone), window.duration, granularity)
        series: list[dict] = []
        if metric in _TREND_METRICS:
            start_utc = self._to_naive_utc(buckets[0])
            end_utc = self._to_naive_utc(self._next_bucket(buckets[-1], granularity))
            async with self._sessions() as session:
                series = await self._trend_series(
                    session, metric, buckets, granularity, local_timezone, start_utc, end_utc
                )
        return {
            "metric": metric,
            "window": window.label,
            "granularity": granularity,
            "series": series,
        }

    async def _trend_series(
        self,
        session,
        metric: str,
        buckets: list[datetime],
        granularity: str,
        local_timezone: tzinfo,
        start_utc: datetime,
        end_utc: datetime,
    ) -> list[dict]:
        bucket_keys = [self._bucket_key(value, granularity) for value in buckets]
        timestamps = {key: _epoch_millis(value) for key, value in zip(bucket_keys, buckets, strict=True)}

        if metric in {"sessions", "messages", "activeusers"}:
            model = Conversation if metric == "sessions" else Message
            columns = [model.create_time]
            if metric == "activeusers":
                columns.append(Message.user_id)
            rows = (
                await session.execute(
                    select(*columns).where(
                        model.deleted == 0,
                        model.create_time >= start_utc,
                        model.create_time < end_utc,
                    )
                )
            ).all()
            counts: dict[str, int] = defaultdict(int)
            active: dict[str, set[int]] = defaultdict(set)
            for row in rows:
                key = self._bucket_key(self._as_local(row[0], local_timezone), granularity)
                if metric == "activeusers":
                    active[key].add(int(row[1]))
                else:
                    counts[key] += 1
            values = {key: len(users) for key, users in active.items()} if metric == "activeusers" else counts
            name = {"sessions": "会话数", "messages": "消息数", "activeusers": "活跃用户"}[metric]
            return [self._series(name, bucket_keys, timestamps, values)]

        if metric == "avglatency":
            rows = (
                await session.execute(
                    select(RagTraceRun.start_time, RagTraceRun.duration_ms).where(
                        RagTraceRun.deleted == 0,
                        RagTraceRun.start_time >= start_utc,
                        RagTraceRun.start_time < end_utc,
                        RagTraceRun.status == "SUCCESS",
                        RagTraceRun.duration_ms > 0,
                    )
                )
            ).all()
            grouped: dict[str, list[int]] = defaultdict(list)
            for started, duration in rows:
                grouped[self._bucket_key(self._as_local(started, local_timezone), granularity)].append(
                    int(duration)
                )
            values = {key: _round1(sum(items) / len(items)) for key, items in grouped.items()}
            return [self._series("平均响应时间", bucket_keys, timestamps, values)]

        trace_rows = (
            await session.execute(
                select(RagTraceRun.start_time, RagTraceRun.status).where(
                    RagTraceRun.deleted == 0,
                    RagTraceRun.start_time >= start_utc,
                    RagTraceRun.start_time < end_utc,
                    RagTraceRun.status.in_(("SUCCESS", "ERROR")),
                )
            )
        ).all()
        message_rows = (
            await session.execute(
                select(Message.create_time, Message.content).where(
                    Message.deleted == 0,
                    Message.role == "assistant",
                    Message.create_time >= start_utc,
                    Message.create_time < end_utc,
                )
            )
        ).all()
        completed: dict[str, int] = defaultdict(int)
        errors: dict[str, int] = defaultdict(int)
        assistant: dict[str, int] = defaultdict(int)
        no_document: dict[str, int] = defaultdict(int)
        for started, status in trace_rows:
            key = self._bucket_key(self._as_local(started, local_timezone), granularity)
            completed[key] += 1
            errors[key] += status == "ERROR"
        for created, content in message_rows:
            key = self._bucket_key(self._as_local(created, local_timezone), granularity)
            assistant[key] += 1
            no_document[key] += content == NO_DOCUMENT_ANSWER
        error_values = {key: _rate(errors[key], completed[key]) for key in bucket_keys}
        no_doc_values = {key: _rate(no_document[key], assistant[key]) for key in bucket_keys}
        return [
            self._series("错误率", bucket_keys, timestamps, error_values),
            self._series("无知识率", bucket_keys, timestamps, no_doc_values),
        ]

    @staticmethod
    async def _count(session, model, *conditions) -> int:
        value = await session.scalar(select(func.count()).select_from(model).where(*conditions))
        return int(value or 0)

    @classmethod
    async def _count_between(
        cls, session, model, *, previous_start: datetime, end: datetime
    ) -> int:
        return await cls._count(
            session,
            model,
            model.deleted == 0,
            model.create_time >= previous_start,
            model.create_time < end,
        )

    @staticmethod
    async def _active_users(session, start: datetime, end: datetime) -> int:
        value = await session.scalar(
            select(func.count(distinct(Message.user_id))).where(
                Message.deleted == 0,
                Message.create_time >= start,
                Message.create_time < end,
            )
        )
        return int(value or 0)

    @staticmethod
    def _kpi(value: int, delta: int, delta_pct: float | None = None) -> dict:
        return {"value": value, "delta": delta, "deltaPct": delta_pct}

    @staticmethod
    def _granularity(value: str | None, duration: timedelta) -> str:
        normalized = (value or "").strip().lower()
        if normalized in {"hour", "day"}:
            return normalized
        return "hour" if duration <= timedelta(hours=48) else "day"

    @staticmethod
    def _buckets(now: datetime, duration: timedelta, granularity: str) -> list[datetime]:
        if granularity == "hour":
            end = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            count = max(1, math.ceil(duration.total_seconds() / 3600))
            return [end - timedelta(hours=index) for index in range(count, 0, -1)]
        start = (now - duration).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        count = (end.date() - start.date()).days
        return [start + timedelta(days=index) for index in range(count + 1)]

    @staticmethod
    def _next_bucket(value: datetime, granularity: str) -> datetime:
        return value + (timedelta(hours=1) if granularity == "hour" else timedelta(days=1))

    @staticmethod
    def _bucket_key(value: datetime, granularity: str) -> str:
        return value.strftime("%Y-%m-%d %H:00:00" if granularity == "hour" else "%Y-%m-%d")

    @staticmethod
    def _as_local(value: datetime, timezone: tzinfo) -> datetime:
        aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return aware.astimezone(timezone)

    @staticmethod
    def _to_naive_utc(value: datetime) -> datetime:
        return value.astimezone(UTC).replace(tzinfo=None)

    @staticmethod
    def _series(name: str, keys: list[str], timestamps: dict[str, int], values) -> dict:
        return {
            "name": name,
            "points": [{"ts": timestamps[key], "value": values.get(key, 0)} for key in keys],
        }


def _epoch_millis(value: datetime) -> int:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return int(aware.timestamp() * 1000)


def _service(request: Request) -> DashboardService:
    return request.app.state.dashboard_service


@router.get("/overview")
async def overview(request: Request, window: str | None = None) -> dict:
    return Results.success(await _service(request).overview(window)).model_dump(by_alias=True)


@router.get("/performance")
async def performance(request: Request, window: str | None = None) -> dict:
    return Results.success(await _service(request).performance(window)).model_dump(by_alias=True)


@router.get("/trends")
async def trends(
    request: Request,
    metric: str = Query(..., min_length=1),
    window: str | None = None,
    granularity: str | None = None,
) -> dict:
    return Results.success(
        await _service(request).trends(metric, window, granularity)
    ).model_dump(by_alias=True)
