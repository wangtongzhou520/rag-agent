"""可编排入库引擎：校验单链，顺序执行六类真实节点。"""

import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any

import httpx

from app.core.chunk.models import ChunkBudget, EmbeddedChunk
from app.core.chunk.service import ChunkingService, render_block
from app.core.ingest.kernel import ChunkEmbeddingService
from app.core.parser.detector import MimeTypeDetector
from app.core.parser.models import HeadingBlock
from app.core.parser.registry import ParseProfile, ParserRegistry
from app.framework.chat_types import ChatMessage, ChatRequest, ChatRole
from app.framework.exceptions import ClientException
from app.ingestion.engine.condition import ConditionEvaluator
from app.ingestion.schemas import IngestionContext, IngestionNodeType, NodeConfig, NodeLog
from app.model_runtime.chat.service import LLMService
from app.model_runtime.routing import Tier

IndexWriter = Callable[[IngestionContext], Awaitable[None]]


class IngestionEngine:
    def __init__(
        self,
        detector: MimeTypeDetector,
        registry: ParserRegistry,
        chunking: ChunkingService,
        embedding: ChunkEmbeddingService,
        llm: LLMService,
        http: httpx.AsyncClient,
        index_writer: IndexWriter,
    ) -> None:
        self._detector = detector
        self._registry = registry
        self._chunking = chunking
        self._embedding = embedding
        self._llm = llm
        self._http = http
        self._index_writer = index_writer
        self._conditions = ConditionEvaluator()

    def ordered_nodes(self, nodes: list[NodeConfig]) -> list[NodeConfig]:
        if not nodes:
            raise ClientException("流水线至少需要一个节点")
        by_id = {node.node_id: node for node in nodes}
        if len(by_id) != len(nodes):
            raise ClientException("流水线节点 ID 不能重复")
        referenced: set[str] = set()
        for node in nodes:
            if node.next_node_id:
                if node.next_node_id not in by_id:
                    raise ClientException(f"找不到下一个节点: {node.next_node_id}")
                referenced.add(node.next_node_id)
        starts = [node for node in nodes if node.node_id not in referenced]
        if not starts:
            raise ClientException("未找到起始节点")
        if len(starts) > 1:
            raise ClientException("流水线存在多个起始节点")
        ordered: list[NodeConfig] = []
        seen: set[str] = set()
        current: NodeConfig | None = starts[0]
        while current:
            if current.node_id in seen:
                raise ClientException(f"流水线存在环: {current.node_id}")
            seen.add(current.node_id)
            ordered.append(current)
            current = by_id.get(current.next_node_id) if current.next_node_id else None
        if len(ordered) != len(nodes):
            raise ClientException("流水线包含不可达节点")
        return ordered

    async def execute(self, nodes: list[NodeConfig], context: IngestionContext) -> str:
        for node in self.ordered_nodes(nodes):
            if not self._conditions.evaluate(node.condition, context):
                context.logs.append(
                    NodeLog(node.node_id, node.node_type.value, "skipped", 0, "Skipped: 条件未满足")
                )
                continue
            started = time.perf_counter()
            try:
                message = await self._execute_node(node, context)
                context.logs.append(
                    NodeLog(
                        node.node_id,
                        node.node_type.value,
                        "success",
                        _elapsed(started),
                        message,
                        output=self._output(node, context),
                    )
                )
            except Exception as exc:  # noqa: BLE001 节点错误是任务结果，不回滚运行日志
                context.error = str(exc)
                context.logs.append(
                    NodeLog(
                        node.node_id,
                        node.node_type.value,
                        "failed",
                        _elapsed(started),
                        "节点执行失败",
                        error=str(exc),
                        output=self._output(node, context),
                    )
                )
                return "failed"
        return "completed"

    async def _execute_node(self, node: NodeConfig, context: IngestionContext) -> str:
        match node.node_type:
            case IngestionNodeType.FETCHER:
                return await self._fetch(context)
            case IngestionNodeType.PARSER:
                return self._parse(context, node.settings)
            case IngestionNodeType.ENHANCER:
                return await self._enhance(context, node.settings)
            case IngestionNodeType.CHUNKER:
                return await self._chunk(context, node.settings)
            case IngestionNodeType.ENRICHER:
                return await self._enrich(context, node.settings)
            case IngestionNodeType.INDEXER:
                if not context.embedded_chunks:
                    raise ClientException("索引节点没有可写入的分块")
                if context.vector_target is None:
                    raise ClientException("索引节点需要 vectorSpaceId")
                await self._index_writer(context)
                return f"已写入 {len(context.embedded_chunks)} 个向量"
        raise ClientException(f"不支持的节点类型: {node.node_type}")

    async def _fetch(self, context: IngestionContext) -> str:
        if context.raw_bytes:
            context.mime_type = self._detector.detect(context.raw_bytes, context.source.file_name)
            return "已使用上传文件，跳过远程获取"
        if not context.source.location:
            raise ClientException("链接地址不能为空")
        headers = {}
        for key, value in context.source.credentials.items():
            headers["Authorization" if key.lower() == "token" else key] = (
                f"Bearer {value}" if key.lower() == "token" else value
            )
        response = await self._http.get(context.source.location, headers=headers)
        response.raise_for_status()
        context.raw_bytes = response.content
        if not context.raw_bytes:
            raise ClientException("远程文件内容为空")
        context.mime_type = response.headers.get("content-type", "").split(";", 1)[0] or self._detector.detect(
            context.raw_bytes, context.source.file_name
        )
        if not context.source.file_name:
            context.source.file_name = httpx.URL(context.source.location).path.rsplit("/", 1)[-1] or "remote"
        return f"已获取 {len(context.raw_bytes)} 字节"

    def _parse(self, context: IngestionContext, settings: dict) -> str:
        if not context.raw_bytes:
            raise ClientException("解析节点没有输入文件")
        context.mime_type = context.mime_type or self._detector.detect(
            context.raw_bytes, context.source.file_name
        )
        self._validate_rules(context.mime_type, settings.get("rules") or [])
        parser = self._registry.require(context.mime_type, str(ParseProfile.FAST))
        context.parsed = parser.parse_structured(
            context.raw_bytes,
            context.mime_type,
            {"sourceFile": context.source.file_name, "documentId": context.task_id},
        )
        rendered = []
        for block in context.parsed.blocks:
            if isinstance(block, HeadingBlock):
                rendered.append(f"{'#' * max(1, min(6, block.level))} {block.text}")
            else:
                value = render_block(block)
                if value:
                    rendered.append(value)
        context.raw_text = "\n\n".join(rendered)
        return f"{parser.name} 解析完成，共 {len(context.parsed.blocks)} 个内容块"

    @staticmethod
    def _validate_rules(mime: str, rules: list[dict]) -> None:
        if not rules:
            return
        aliases = {
            "pdf": "application/pdf",
            "markdown": "text/markdown",
            "md": "text/markdown",
            "text": "text/",
            "excel": "spreadsheet",
            "xlsx": "spreadsheet",
        }
        for rule in rules:
            expected = str(rule.get("mimeType", "")).strip().lower()
            token = aliases.get(expected, expected)
            if expected in {"*", "all", "default"} or token in mime.lower():
                return
        raise ClientException(f"文件类型不符合要求: {mime}")

    async def _enhance(self, context: IngestionContext, settings: dict) -> str:
        tasks = settings.get("tasks") or []
        if not tasks:
            return "没有配置文档增强任务"
        for task in tasks:
            task_type = str(task.get("type", "")).strip().lower()
            source = context.raw_text if task_type == "context_enhance" else context.enhanced_text or context.raw_text
            if not source:
                continue
            result = await self._ask(task, source, context, settings.get("modelId"))
            if task_type == "context_enhance":
                context.enhanced_text = result.strip()
            elif task_type == "keywords":
                context.keywords = _string_list(result)
            elif task_type == "questions":
                context.questions = _string_list(result)
            elif task_type == "metadata":
                context.metadata.update(_json_object(result))
            else:
                raise ClientException(f"不支持的增强任务: {task_type}")
        return f"已执行 {len(tasks)} 个文档增强任务"

    async def _chunk(self, context: IngestionContext, settings: dict) -> str:
        if context.parsed is None:
            raise ClientException("分块节点需要先执行解析节点")
        if context.vector_target is None:
            raise ClientException("分块节点需要 vectorSpaceId")
        raw_size = int(settings.get("chunkSize", 1024))
        size = None if raw_size == -1 else max(128, raw_size if raw_size > 0 else 1024)
        overlap = int(settings.get("overlapSize", 128))
        overlap = max(0, overlap)
        if size is not None:
            overlap = min(overlap, size - 1)
        budget = ChunkBudget(
            max_chars=size,
            overlap_chars=overlap,
            rows_per_chunk=max(1, int(settings.get("rowsPerChunk", 50))),
        )
        context.chunks = self._chunking.chunk(context.parsed.blocks, budget)
        if not context.chunks:
            raise ClientException("分块结果为空")
        context.embedded_chunks = await self._embedding.embed(context.chunks, context.vector_target)
        return f"分块并向量化完成，共 {len(context.chunks)} 块"

    async def _enrich(self, context: IngestionContext, settings: dict) -> str:
        tasks = settings.get("tasks") or []
        if not context.chunks or not tasks:
            return "没有需要执行的块级富集任务"
        updated = []
        for chunk in context.chunks:
            extras = dict(chunk.metadata)
            if settings.get("attachDocumentMetadata", True):
                extras.update(context.metadata)
            for task in tasks:
                task_type = str(task.get("type", "")).strip().lower()
                result = await self._ask(task, chunk.content, context, settings.get("modelId"), chunk.chunk_index)
                if task_type == "keywords":
                    extras["keywords"] = _string_list(result)
                elif task_type == "summary":
                    extras["summary"] = result.strip()
                elif task_type == "metadata":
                    extras.update(_json_object(result))
                else:
                    raise ClientException(f"不支持的块级富集任务: {task_type}")
            updated.append(replace(chunk, metadata=extras))
        vectors = [item.vector for item in context.embedded_chunks]
        context.chunks = updated
        context.embedded_chunks = [EmbeddedChunk(chunk, vector) for chunk, vector in zip(updated, vectors, strict=True)]
        return f"已富集 {len(updated)} 个分块"

    async def _ask(
        self,
        task: dict,
        content: str,
        context: IngestionContext,
        model_id: str | None,
        chunk_index: int | None = None,
    ) -> str:
        task_type = str(task.get("type", ""))
        defaults = {
            "context_enhance": "整理文档格式并保留全部核心信息，直接输出整理后的正文。",
            "keywords": "提取关键词并只输出 JSON 字符串数组。",
            "questions": "生成可由文档回答的问题并只输出 JSON 字符串数组。",
            "metadata": "抽取结构化信息并只输出 JSON 对象。",
            "summary": "用一到三句话概括片段，直接输出摘要。",
        }
        system = str(task.get("systemPrompt") or defaults.get(task_type, "处理给定文本。"))
        template = str(task.get("userPromptTemplate") or "{{text}}")
        values = {
            "text": content,
            "content": content,
            "mimeType": context.mime_type or "",
            "taskId": str(context.task_id),
            "pipelineId": str(context.pipeline_id),
            "chunkIndex": "" if chunk_index is None else str(chunk_index),
        }
        for key, value in values.items():
            template = template.replace("{{" + key + "}}", value)
        return await self._llm.chat(
            ChatRequest(
                messages=[
                    ChatMessage(role=ChatRole.SYSTEM, content=system),
                    ChatMessage(role=ChatRole.USER, content=template),
                ],
                temperature=0.1,
            ),
            tier=Tier.FAST,
            preferred_model_id=str(model_id) if model_id else None,
        )

    @staticmethod
    def _output(node: NodeConfig, context: IngestionContext) -> dict[str, Any]:
        match node.node_type:
            case IngestionNodeType.FETCHER:
                return {"source": context.source.type.value, "mimeType": context.mime_type, "rawBytesLength": len(context.raw_bytes or b"")}
            case IngestionNodeType.PARSER:
                return {"mimeType": context.mime_type, "rawTextLength": len(context.raw_text), "blockCount": len(context.parsed.blocks) if context.parsed else 0}
            case IngestionNodeType.ENHANCER:
                return {"enhancedTextLength": len(context.enhanced_text), "keywords": context.keywords, "questions": context.questions, "metadata": context.metadata}
            case IngestionNodeType.CHUNKER | IngestionNodeType.ENRICHER | IngestionNodeType.INDEXER:
                return {"chunkCount": len(context.chunks), "totalChars": sum(len(item.content) for item in context.chunks), "embeddingDim": len(context.embedded_chunks[0].vector) if context.embedded_chunks else 0}
        return {}


def _elapsed(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _json_value(raw: str) -> Any:
    value = raw.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    starts = [index for index in (value.find("["), value.find("{")) if index >= 0]
    if starts:
        value = value[min(starts) :]
    for end in (value.rfind("]"), value.rfind("}")):
        if end >= 0:
            try:
                return json.loads(value[: end + 1])
            except json.JSONDecodeError:
                continue
    return None


def _string_list(raw: str) -> list[str]:
    value = _json_value(raw)
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _json_object(raw: str) -> dict[str, Any]:
    value = _json_value(raw)
    return value if isinstance(value, dict) else {}
