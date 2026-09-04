"""Pipeline 配置、同步调试任务和 PG 后台任务查询服务。"""

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.framework.async_task import AsyncTask
from app.framework.exceptions import ClientException
from app.ingestion.engine.engine import IngestionEngine
from app.ingestion.models import (
    IngestionPipeline,
    IngestionPipelineNode,
    IngestionTask,
    IngestionTaskNode,
)
from app.ingestion.schemas import (
    IngestionContext,
    NodeConfig,
    PipelineCreate,
    PipelineUpdate,
    TaskCreate,
)
from app.knowledge.models import KnowledgeVector
from app.system.audit.context import AuditContext

OUTPUT_LIMIT = 1024 * 1024


class PipelineVectorWriter:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def write(self, context: IngestionContext) -> None:
        assert context.vector_target is not None
        async with self._sessions.begin() as session:
            for item in context.embedded_chunks:
                session.add(
                    KnowledgeVector(
                        id=item.chunk.id,
                        collection_name=context.vector_target.partition,
                        content=item.chunk.content,
                        extra_metadata={
                            **item.chunk.metadata,
                            **context.metadata,
                            "task_id": context.task_id,
                            "pipeline_id": context.pipeline_id,
                            "source_type": context.source.type.value,
                            "source_location": context.source.location,
                            "chunk_index": item.chunk.chunk_index,
                            "outline_path": list(item.chunk.outline_path),
                        },
                        embedding=list(item.vector),
                    )
                )


class IngestionService:
    def __init__(
        self,
        engine: AsyncEngine,
        runner: IngestionEngine,
        *,
        embedding_model: str,
        dimension: int,
    ) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._runner = runner
        self._embedding_model = embedding_model
        self._dimension = dimension

    async def create_pipeline(self, body: PipelineCreate, user_id: int) -> str:
        self._runner.ordered_nodes(body.nodes)
        name = body.name.strip()
        async with self._sessions.begin() as session:
            await self._ensure_name(session, name)
            pipeline = IngestionPipeline(
                name=name,
                description=_clean(body.description),
                created_by=user_id,
            )
            session.add(pipeline)
            await session.flush()
            self._add_nodes(session, pipeline.id, body.nodes)
            await session.flush()
            snapshot = self._pipeline_snapshot(pipeline, body.nodes)
            AuditContext.put(pipeline.id, None, snapshot)
            return str(pipeline.id)

    async def update_pipeline(
        self, pipeline_id: int, body: PipelineUpdate, user_id: int
    ) -> None:
        if body.nodes is not None:
            self._runner.ordered_nodes(body.nodes)
        async with self._sessions.begin() as session:
            pipeline = await self._require_pipeline(session, pipeline_id)
            old_nodes = await self._load_nodes(session, pipeline_id)
            before = self._pipeline_snapshot(pipeline, old_nodes)
            if body.name is not None:
                name = body.name.strip()
                await self._ensure_name(session, name, pipeline_id)
                pipeline.name = name
            if body.description is not None:
                pipeline.description = _clean(body.description)
            if body.nodes is not None:
                await session.execute(
                    delete(IngestionPipelineNode).where(
                        IngestionPipelineNode.pipeline_id == pipeline_id
                    )
                )
                self._add_nodes(session, pipeline_id, body.nodes)
            pipeline.updated_by = user_id
            await session.flush()
            nodes = body.nodes if body.nodes is not None else old_nodes
            after = self._pipeline_snapshot(pipeline, nodes)
            if before == after:
                AuditContext.skip()
            else:
                AuditContext.put(pipeline_id, before, after)

    async def get_pipeline(self, pipeline_id: int) -> dict:
        async with self._sessions() as session:
            pipeline = await self._require_pipeline(session, pipeline_id)
            nodes = await self._load_nodes(session, pipeline_id)
            return self._pipeline_snapshot(pipeline, nodes)

    async def page_pipelines(self, page_no: int, page_size: int, keyword: str | None) -> dict:
        page_no, page_size = _page(page_no, page_size)
        filters = [IngestionPipeline.deleted == 0]
        if keyword and keyword.strip():
            filters.append(IngestionPipeline.name.ilike(f"%{keyword.strip()}%"))
        async with self._sessions() as session:
            total = await session.scalar(
                select(func.count()).select_from(IngestionPipeline).where(*filters)
            )
            pipelines = (
                await session.scalars(
                    select(IngestionPipeline)
                    .where(*filters)
                    .order_by(IngestionPipeline.update_time.desc(), IngestionPipeline.id.desc())
                    .offset((page_no - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
            records = []
            for pipeline in pipelines:
                records.append(
                    self._pipeline_snapshot(
                        pipeline, await self._load_nodes(session, pipeline.id)
                    )
                )
        return _page_result(records, int(total or 0), page_no, page_size)

    async def delete_pipeline(self, pipeline_id: int) -> None:
        async with self._sessions.begin() as session:
            pipeline = await self._require_pipeline(session, pipeline_id)
            active = await session.scalar(
                select(func.count())
                .select_from(IngestionTask)
                .where(
                    IngestionTask.pipeline_id == pipeline_id,
                    IngestionTask.status.in_(("pending", "running")),
                    IngestionTask.deleted == 0,
                )
            )
            if active:
                raise ClientException("流水线存在运行中任务，不能删除")
            before = self._pipeline_snapshot(
                pipeline, await self._load_nodes(session, pipeline_id)
            )
            pipeline.deleted = 1
            nodes = (
                await session.scalars(
                    select(IngestionPipelineNode).where(
                        IngestionPipelineNode.pipeline_id == pipeline_id
                    )
                )
            ).all()
            for node in nodes:
                node.deleted = 1
            AuditContext.put(pipeline_id, before, None)

    async def run_task(
        self,
        body: TaskCreate,
        user_id: int,
        *,
        raw_bytes: bytes | None = None,
    ) -> dict:
        if body.source.type.value == "file" and not raw_bytes:
            raise ClientException("file 来源必须上传文件")
        if body.source.type.value != "file" and not body.source.location:
            raise ClientException("远程来源地址不能为空")
        async with self._sessions() as session:
            pipeline = await self._require_pipeline(session, body.pipeline_id)
            nodes = await self._load_nodes(session, pipeline.id)
        self._runner.ordered_nodes(nodes)
        now = _utc_now()
        async with self._sessions.begin() as session:
            task = IngestionTask(
                pipeline_id=body.pipeline_id,
                source_type=body.source.type.value,
                source_location=body.source.location,
                source_file_name=body.source.file_name,
                status="running",
                metadata_json=body.metadata,
                started_at=now,
                created_by=user_id,
            )
            session.add(task)
            await session.flush()
            task_id = task.id
        from app.core.ingest.models import VectorTarget

        target = (
            VectorTarget(body.vector_space_id, self._embedding_model, self._dimension)
            if body.vector_space_id
            else None
        )
        context = IngestionContext(
            task_id=task_id,
            pipeline_id=body.pipeline_id,
            source=body.source,
            metadata=dict(body.metadata),
            vector_target=target,
            raw_bytes=raw_bytes,
        )
        status = await self._runner.execute(nodes, context)
        completed = _utc_now()
        async with self._sessions.begin() as session:
            task = await session.get(IngestionTask, task_id)
            assert task is not None
            task.status = status
            task.chunk_count = len(context.chunks)
            task.error_message = context.error
            task.source_file_name = context.source.file_name
            task.metadata_json = {
                **context.metadata,
                **({"keywords": context.keywords} if context.keywords else {}),
                **({"questions": context.questions} if context.questions else {}),
            }
            task.logs_json = [
                {
                    "nodeId": log.node_id,
                    "nodeType": log.node_type,
                    "status": log.status,
                    "durationMs": log.duration_ms,
                    "message": log.message,
                    "error": log.error,
                }
                for log in context.logs
            ]
            task.completed_at = completed
            for order, log in enumerate(context.logs, 1):
                session.add(
                    IngestionTaskNode(
                        task_id=task_id,
                        pipeline_id=body.pipeline_id,
                        node_id=log.node_id,
                        node_type=log.node_type,
                        node_order=order,
                        status=log.status,
                        duration_ms=log.duration_ms,
                        message=log.message[:512],
                        error_message=log.error,
                        output_json=_limited_json(log.output),
                    )
                )
        AuditContext.put(
            task_id,
            None,
            {"pipelineId": body.pipeline_id, "status": status, "chunkCount": len(context.chunks)},
        )
        return {
            "taskId": str(task_id),
            "pipelineId": body.pipeline_id,
            "status": status,
            "chunkCount": len(context.chunks),
            "message": "OK" if status == "completed" else context.error or "执行失败",
        }

    async def get_task(self, task_id: int) -> dict:
        async with self._sessions() as session:
            task = await self._require_task(session, task_id)
            return self._task_snapshot(task)

    async def page_tasks(self, page_no: int, page_size: int, status: str | None) -> dict:
        page_no, page_size = _page(page_no, page_size)
        filters = [IngestionTask.deleted == 0]
        if status and status.strip():
            normalized = status.strip().lower()
            if normalized not in {"pending", "running", "failed", "completed"}:
                raise ClientException("任务状态不合法")
            filters.append(IngestionTask.status == normalized)
        async with self._sessions() as session:
            total = await session.scalar(
                select(func.count()).select_from(IngestionTask).where(*filters)
            )
            rows = (
                await session.scalars(
                    select(IngestionTask)
                    .where(*filters)
                    .order_by(IngestionTask.create_time.desc(), IngestionTask.id.desc())
                    .offset((page_no - 1) * page_size)
                    .limit(page_size)
                )
            ).all()
        return _page_result(
            [self._task_snapshot(row) for row in rows], int(total or 0), page_no, page_size
        )

    async def task_nodes(self, task_id: int) -> list[dict]:
        async with self._sessions() as session:
            await self._require_task(session, task_id)
            rows = (
                await session.scalars(
                    select(IngestionTaskNode)
                    .where(
                        IngestionTaskNode.task_id == task_id,
                        IngestionTaskNode.deleted == 0,
                    )
                    .order_by(IngestionTaskNode.node_order, IngestionTaskNode.id)
                )
            ).all()
        return [self._task_node_snapshot(row) for row in rows]

    async def page_async_tasks(
        self, current: int, size: int, status: str | None, task_type: str | None
    ) -> dict:
        current, size = _page(current, size)
        filters = [AsyncTask.deleted == 0]
        if status and status.strip():
            filters.append(AsyncTask.status == status.strip().lower())
        if task_type and task_type.strip():
            filters.append(AsyncTask.task_type == task_type.strip())
        async with self._sessions() as session:
            total = await session.scalar(select(func.count()).select_from(AsyncTask).where(*filters))
            rows = (
                await session.scalars(
                    select(AsyncTask)
                    .where(*filters)
                    .order_by(AsyncTask.create_time.desc(), AsyncTask.id.desc())
                    .offset((current - 1) * size)
                    .limit(size)
                )
            ).all()
        return _page_result([self._async_snapshot(row) for row in rows], int(total or 0), current, size)

    @staticmethod
    def _add_nodes(session, pipeline_id: int, nodes: list[NodeConfig]) -> None:
        for node in nodes:
            session.add(
                IngestionPipelineNode(
                    pipeline_id=pipeline_id,
                    node_id=node.node_id,
                    node_type=node.node_type.value,
                    next_node_id=node.next_node_id,
                    settings_json=node.settings,
                    condition_json=node.condition,
                )
            )

    @staticmethod
    async def _load_nodes(session, pipeline_id: int) -> list[NodeConfig]:
        rows = (
            await session.scalars(
                select(IngestionPipelineNode)
                .where(
                    IngestionPipelineNode.pipeline_id == pipeline_id,
                    IngestionPipelineNode.deleted == 0,
                )
                .order_by(IngestionPipelineNode.id)
            )
        ).all()
        return [
            NodeConfig(
                id=row.id,
                nodeId=row.node_id,
                nodeType=row.node_type,
                settings=row.settings_json or {},
                condition=row.condition_json,
                nextNodeId=row.next_node_id,
            )
            for row in rows
        ]

    @staticmethod
    async def _require_pipeline(session, pipeline_id: int) -> IngestionPipeline:
        row = await session.scalar(
            select(IngestionPipeline).where(
                IngestionPipeline.id == pipeline_id, IngestionPipeline.deleted == 0
            )
        )
        if row is None:
            raise ClientException("流水线不存在")
        return row

    @staticmethod
    async def _require_task(session, task_id: int) -> IngestionTask:
        row = await session.scalar(
            select(IngestionTask).where(IngestionTask.id == task_id, IngestionTask.deleted == 0)
        )
        if row is None:
            raise ClientException("入库任务不存在")
        return row

    @staticmethod
    async def _ensure_name(session, name: str, exclude_id: int | None = None) -> None:
        filters = [func.lower(IngestionPipeline.name) == name.lower(), IngestionPipeline.deleted == 0]
        if exclude_id is not None:
            filters.append(IngestionPipeline.id != exclude_id)
        if await session.scalar(select(IngestionPipeline.id).where(*filters).limit(1)) is not None:
            raise ClientException("流水线名称已存在")

    @staticmethod
    def _pipeline_snapshot(row: IngestionPipeline, nodes: list[NodeConfig]) -> dict:
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "createdBy": row.created_by,
            "nodes": [node.model_dump(by_alias=True, mode="json") for node in nodes],
            "createTime": _epoch_millis(row.create_time),
            "updateTime": _epoch_millis(row.update_time),
        }

    @staticmethod
    def _task_snapshot(row: IngestionTask) -> dict:
        return {
            "id": row.id,
            "pipelineId": row.pipeline_id,
            "sourceType": row.source_type,
            "sourceLocation": row.source_location,
            "sourceFileName": row.source_file_name,
            "status": row.status,
            "chunkCount": row.chunk_count,
            "errorMessage": row.error_message,
            "logs": row.logs_json or [],
            "metadata": row.metadata_json or {},
            "startedAt": _epoch_millis(row.started_at),
            "completedAt": _epoch_millis(row.completed_at),
            "createdBy": row.created_by,
            "createTime": _epoch_millis(row.create_time),
            "updateTime": _epoch_millis(row.update_time),
        }

    @staticmethod
    def _task_node_snapshot(row: IngestionTaskNode) -> dict:
        try:
            output = json.loads(row.output_json) if row.output_json else None
        except json.JSONDecodeError:
            output = row.output_json
        return {
            "id": row.id,
            "taskId": row.task_id,
            "pipelineId": row.pipeline_id,
            "nodeId": row.node_id,
            "nodeType": row.node_type,
            "nodeOrder": row.node_order,
            "status": row.status,
            "durationMs": row.duration_ms,
            "message": row.message,
            "errorMessage": row.error_message,
            "output": output,
            "createTime": _epoch_millis(row.create_time),
            "updateTime": _epoch_millis(row.update_time),
        }

    @staticmethod
    def _async_snapshot(row: AsyncTask) -> dict:
        return {
            "id": row.id,
            "eventId": str(row.event_id),
            "taskType": row.task_type,
            "bizKey": row.biz_key,
            "status": row.status,
            "retryCount": row.retry_count,
            "maxRetries": row.max_retries,
            "nextRetryAt": _epoch_millis(row.next_retry_at),
            "leaseUntil": _epoch_millis(row.lease_until),
            "errorMessage": row.error_message,
            "createTime": _epoch_millis(row.create_time),
            "updateTime": _epoch_millis(row.update_time),
        }


def _clean(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _epoch_millis(value: datetime | None) -> int | None:
    if value is None:
        return None
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return int(aware.timestamp() * 1000)


def _page(current: int, size: int) -> tuple[int, int]:
    return max(1, current), max(1, min(100, size))


def _page_result(records: list, total: int, current: int, size: int) -> dict:
    return {
        "records": records,
        "total": total,
        "current": current,
        "size": size,
        "pages": max(1, (total + size - 1) // size),
    }


def _limited_json(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, default=str)
    data = raw.encode("utf-8")
    if len(data) <= OUTPUT_LIMIT:
        return raw
    suffix = f"... [输出过大，已截断，原始大小: {len(data)} 字节]"
    budget = OUTPUT_LIMIT - len(suffix.encode("utf-8")) - 2
    prefix = data[:budget].decode("utf-8", errors="ignore")
    return json.dumps(prefix + suffix, ensure_ascii=False)
