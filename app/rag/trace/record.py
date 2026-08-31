"""RAG Trace 独立事务记录服务；写入失败不反向影响问答。"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.framework.ids import new_native_uuid7
from app.framework.logging import get_logger
from app.rag.models import RagTraceNode, RagTraceRun

logger = get_logger(__name__)


class RagTraceRecordService:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def start_run(
        self,
        conversation_id: str,
        task_id: str,
        user_id: int,
        question: str,
    ) -> tuple[str, datetime]:
        trace_id = new_native_uuid7()
        started = datetime.now(UTC).replace(tzinfo=None)
        try:
            async with self._sessions.begin() as session:
                session.add(
                    RagTraceRun(
                        trace_id=trace_id,
                        trace_name="rag-stream-chat",
                        entry_point="app.rag.pipeline.StreamChatPipeline.execute",
                        conversation_id=uuid.UUID(conversation_id),
                        task_id=uuid.UUID(task_id),
                        user_id=user_id,
                        status="RUNNING",
                        start_time=started,
                        extra_data={
                            "question": question,
                            "questionLength": len(question),
                        },
                    )
                )
        except Exception:
            logger.exception("RAG Trace run 创建失败")
        return str(trace_id), started

    async def finish_run(
        self,
        trace_id: str,
        started: datetime,
        status: str,
        error: str | None = None,
    ) -> None:
        ended = datetime.now(UTC).replace(tzinfo=None)
        try:
            async with self._sessions.begin() as session:
                row = await session.scalar(
                    select(RagTraceRun).where(
                        RagTraceRun.trace_id == uuid.UUID(trace_id)
                    )
                )
                if row is not None:
                    row.status = status
                    row.error_message = error[:1000] if error else None
                    row.end_time = ended
                    row.duration_ms = int((ended - started).total_seconds() * 1000)
        except Exception:
            logger.exception("RAG Trace run 收尾失败")

    async def record_retrieval(
        self, trace_id: str, duration_ms: int, extra: dict
    ) -> None:
        try:
            async with self._sessions.begin() as session:
                session.add(
                    RagTraceNode(
                        trace_id=uuid.UUID(trace_id),
                        node_id=new_native_uuid7(),
                        node_type="RETRIEVE",
                        node_name="retrieval-engine",
                        status="SUCCESS",
                        duration_ms=duration_ms,
                        extra_data=extra,
                    )
                )
        except Exception:
            logger.exception("RAG Trace retrieval 节点写入失败")
