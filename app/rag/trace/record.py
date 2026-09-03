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

    async def record_recommendation(
        self,
        conversation_id: uuid.UUID,
        user_id: int,
        duration_ms: int,
        status: str,
        question_count: int,
    ) -> None:
        """把按需推荐生成挂到该会话最近一次 RAG run，不反向影响接口。"""
        try:
            async with self._sessions.begin() as session:
                trace_id = await session.scalar(
                    select(RagTraceRun.trace_id)
                    .where(
                        RagTraceRun.conversation_id == conversation_id,
                        RagTraceRun.user_id == user_id,
                    )
                    .order_by(RagTraceRun.create_time.desc())
                    .limit(1)
                )
                if trace_id is None:
                    return
                session.add(
                    RagTraceNode(
                        trace_id=trace_id,
                        node_id=new_native_uuid7(),
                        node_type="RECOMMEND_GEN",
                        node_name="recommended-question-gen",
                        status=status,
                        duration_ms=max(0, duration_ms),
                        extra_data={"questionCount": question_count},
                    )
                )
        except Exception:
            logger.exception("RAG Trace 推荐追问节点写入失败")
