"""RAG Trace 查询服务。"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.rag.models import RagTraceNode, RagTraceRun


class RagTraceQueryService:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def page_runs(
        self,
        current: int,
        size: int,
        *,
        trace_id: str | None = None,
        conversation_id: str | None = None,
        task_id: str | None = None,
        status: str | None = None,
    ) -> dict:
        filters = [RagTraceRun.deleted == 0]
        for value, column in (
            (trace_id, RagTraceRun.trace_id),
            (conversation_id, RagTraceRun.conversation_id),
            (task_id, RagTraceRun.task_id),
        ):
            if value:
                try:
                    filters.append(column == uuid.UUID(value))
                except ValueError:
                    return {"records": [], "total": 0, "current": current, "size": size}
        if status:
            filters.append(RagTraceRun.status == status.upper())
        async with self._sessions() as session:
            total = await session.scalar(
                select(func.count()).select_from(RagTraceRun).where(*filters)
            )
            rows = (
                await session.scalars(
                    select(RagTraceRun)
                    .where(*filters)
                    .order_by(RagTraceRun.start_time.desc(), RagTraceRun.id.desc())
                    .offset((current - 1) * size)
                    .limit(size)
                )
            ).all()
        return {
            "records": [self._run(row) for row in rows],
            "total": int(total or 0),
            "current": current,
            "size": size,
        }

    async def detail(self, trace_id: str) -> dict | None:
        parsed = self._uuid(trace_id)
        if parsed is None:
            return None
        async with self._sessions() as session:
            run = await session.scalar(
                select(RagTraceRun).where(
                    RagTraceRun.trace_id == parsed, RagTraceRun.deleted == 0
                )
            )
            nodes = (
                await session.scalars(
                    select(RagTraceNode)
                    .where(
                        RagTraceNode.trace_id == parsed,
                        RagTraceNode.deleted == 0,
                    )
                    .order_by(RagTraceNode.id)
                )
            ).all()
        if run is None:
            return None
        return {"run": self._run(run), "nodes": [self._node(node) for node in nodes]}

    async def nodes(self, trace_id: str) -> list[dict]:
        detail = await self.detail(trace_id)
        return detail["nodes"] if detail else []

    @staticmethod
    def _uuid(value: str) -> uuid.UUID | None:
        try:
            return uuid.UUID(value)
        except ValueError:
            return None

    @staticmethod
    def _run(row: RagTraceRun) -> dict:
        return {
            "traceId": str(row.trace_id),
            "traceName": row.trace_name,
            "entryPoint": row.entry_point,
            "conversationId": str(row.conversation_id),
            "taskId": str(row.task_id),
            "userId": row.user_id,
            "status": row.status,
            "errorMessage": row.error_message,
            "durationMs": row.duration_ms,
            "question": (row.extra_data or {}).get("question"),
            "startTime": row.start_time.isoformat(),
            "endTime": row.end_time.isoformat() if row.end_time else None,
        }

    @staticmethod
    def _node(row: RagTraceNode) -> dict:
        return {
            "nodeId": str(row.node_id),
            "nodeType": row.node_type,
            "nodeName": row.node_name,
            "status": row.status,
            "durationMs": row.duration_ms,
            "extraData": row.extra_data,
        }
