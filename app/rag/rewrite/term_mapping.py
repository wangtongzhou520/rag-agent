"""查询词映射和无模型规则拆分。"""

import json
import re
from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.framework.chat_types import ChatMessage, ChatRequest, ChatRole
from app.framework.logging import get_logger
from app.model_runtime.routing import Tier
from app.rag.rewrite.cache import QueryTermMappingCacheManager
from app.rag.rewrite.models import QueryTermMapping, RewriteResult
from app.rag.rewrite.orm import QueryTermMappingRecord

logger = get_logger(__name__)


class QueryTermMappingUtil:
    @staticmethod
    def apply_mapping(text: str, mapping: QueryTermMapping) -> str:
        """按精确规则顺序替换；目标词已经存在时跳过，避免重复膨胀。"""
        source = mapping.source_term.strip()
        target = mapping.target_term.strip()
        if mapping.match_type != 1 or not source or not target or source == target:
            return text
        result = text
        offset = 0
        while True:
            index = result.find(source, offset)
            if index < 0:
                return result
            if not result.startswith(target, index):
                result = result[:index] + target + result[index + len(source) :]
                offset = index + len(target)
            else:
                offset = index + len(source)


class QueryTermMappingService:
    def __init__(
        self,
        mappings: Iterable[QueryTermMapping] = (),
        *,
        engine: AsyncEngine | None = None,
        cache: QueryTermMappingCacheManager | None = None,
    ) -> None:
        self._mappings = tuple(mappings) if engine is None else None
        self._sessions = (
            async_sessionmaker(engine, expire_on_commit=False) if engine else None
        )
        self._cache = cache

    def normalize(self, question: str) -> str:
        normalized = question.strip()
        for mapping in self._ordered_mappings(self._mappings or ()):
            if mapping.enabled:
                normalized = QueryTermMappingUtil.apply_mapping(normalized, mapping)
        return normalized

    async def normalize_async(self, question: str) -> str:
        normalized = question.strip()
        for mapping in self._ordered_mappings(await self.load_mappings()):
            if mapping.enabled:
                normalized = QueryTermMappingUtil.apply_mapping(normalized, mapping)
        return normalized

    async def load_mappings(self) -> list[QueryTermMapping]:
        if self._sessions is None:
            return list(self._mappings or ())
        if self._cache is not None:
            try:
                cached = await self._cache.get()
                if cached is not None:
                    return cached
            except Exception:
                logger.exception("查询词映射缓存读取失败")
        try:
            async with self._sessions() as session:
                rows = (
                    await session.scalars(
                        select(QueryTermMappingRecord)
                        .where(
                            QueryTermMappingRecord.enabled == 1,
                            QueryTermMappingRecord.deleted == 0,
                        )
                        .order_by(
                            QueryTermMappingRecord.priority.is_(None).desc(),
                            QueryTermMappingRecord.priority.desc(),
                            func.length(QueryTermMappingRecord.source_term).desc(),
                            QueryTermMappingRecord.id,
                        )
                    )
                ).all()
            mappings = [self._to_domain(row) for row in rows]
            if self._cache is not None:
                try:
                    await self._cache.put(mappings)
                except Exception:
                    logger.exception("查询词映射缓存写入失败")
            return mappings
        except Exception:
            logger.exception("查询词映射加载失败，使用空映射")
            return []

    async def list_mappings(
        self, current: int, size: int, keyword: str | None = None
    ) -> tuple[list[QueryTermMapping], int]:
        if self._sessions is None:
            values = list(self._mappings or ())
            return values, len(values)
        current = max(1, current)
        size = min(100, max(1, size))
        filters = [QueryTermMappingRecord.deleted == 0]
        if keyword and keyword.strip():
            term = f"%{keyword.strip()}%"
            filters.append(
                (QueryTermMappingRecord.source_term.ilike(term))
                | (QueryTermMappingRecord.target_term.ilike(term))
            )
        async with self._sessions() as session:
            total = await session.scalar(
                select(func.count()).select_from(QueryTermMappingRecord).where(*filters)
            )
            rows = (
                await session.scalars(
                    select(QueryTermMappingRecord)
                    .where(*filters)
                    .order_by(QueryTermMappingRecord.id.desc())
                    .offset((current - 1) * size)
                    .limit(size)
                )
            ).all()
        return [self._to_domain(row) for row in rows], int(total or 0)

    async def get_mapping(self, mapping_id: int) -> QueryTermMapping:
        if self._sessions is None:
            for mapping in self._mappings or ():
                if mapping.id == mapping_id:
                    return mapping
            raise ValueError("查询词映射不存在")
        async with self._sessions() as session:
            row = await session.scalar(
                select(QueryTermMappingRecord).where(
                    QueryTermMappingRecord.id == mapping_id,
                    QueryTermMappingRecord.deleted == 0,
                )
            )
        if row is None:
            raise ValueError("查询词映射不存在")
        return self._to_domain(row)

    async def create_mapping(self, mapping: QueryTermMapping, user_id: int) -> int:
        self._validate(mapping)
        if self._sessions is None:
            raise RuntimeError("查询词映射未配置数据库")
        async with self._sessions.begin() as session:
            row = QueryTermMappingRecord(
                source_term=mapping.source_term.strip(),
                target_term=mapping.target_term.strip(),
                match_type=mapping.match_type,
                priority=mapping.priority,
                enabled=int(mapping.enabled),
                domain=mapping.domain,
                remark=mapping.remark,
                created_by=user_id,
            )
            session.add(row)
            await session.flush()
            mapping_id = row.id
        await self._evict()
        return int(mapping_id)

    async def update_mapping(
        self, mapping_id: int, mapping: QueryTermMapping, user_id: int
    ) -> None:
        self._validate(mapping)
        if self._sessions is None:
            raise RuntimeError("查询词映射未配置数据库")
        async with self._sessions.begin() as session:
            row = await session.scalar(
                select(QueryTermMappingRecord).where(
                    QueryTermMappingRecord.id == mapping_id,
                    QueryTermMappingRecord.deleted == 0,
                )
            )
            if row is None:
                raise ValueError("查询词映射不存在")
            row.source_term = mapping.source_term.strip()
            row.target_term = mapping.target_term.strip()
            row.match_type = mapping.match_type
            row.priority = mapping.priority
            row.enabled = int(mapping.enabled)
            row.domain = mapping.domain
            row.remark = mapping.remark
            row.updated_by = user_id
        await self._evict()

    async def delete_mapping(self, mapping_id: int) -> None:
        if self._sessions is None:
            raise RuntimeError("查询词映射未配置数据库")
        async with self._sessions.begin() as session:
            row = await session.scalar(
                select(QueryTermMappingRecord).where(
                    QueryTermMappingRecord.id == mapping_id,
                    QueryTermMappingRecord.deleted == 0,
                )
            )
            if row is None:
                raise ValueError("查询词映射不存在")
            row.deleted = 1
        await self._evict()

    async def _evict(self) -> None:
        if self._cache is not None:
            try:
                await self._cache.evict()
            except Exception:
                logger.exception("查询词映射缓存清理失败")

    @staticmethod
    def _validate(mapping: QueryTermMapping) -> None:
        if not mapping.source_term.strip() or not mapping.target_term.strip():
            raise ValueError("源词和目标词不能为空")
        if mapping.match_type not in {1, 2, 3, 4}:
            raise ValueError("match_type 必须在 1 到 4 之间")

    @staticmethod
    def _to_domain(row: QueryTermMappingRecord) -> QueryTermMapping:
        return QueryTermMapping(
            id=row.id,
            domain=row.domain,
            source_term=row.source_term,
            target_term=row.target_term,
            match_type=row.match_type,
            priority=row.priority,
            enabled=bool(row.enabled),
            remark=row.remark,
        )

    @staticmethod
    def _ordered_mappings(mappings: Iterable[QueryTermMapping]) -> list[QueryTermMapping]:
        return sorted(
            mappings,
            key=lambda item: (
                item.priority is not None,
                -(item.priority or 0),
                -len(item.source_term),
            ),
        )


class RuleBasedRewriteService:
    """模型关闭或不可用时的确定性改写兜底。"""

    _SEPARATOR = re.compile(r"[?？。；;\n]+")

    def __init__(self, mappings: QueryTermMappingService | None = None) -> None:
        self._mappings = mappings or QueryTermMappingService()

    async def rewrite_with_split(
        self, question: str, history: Iterable[object] = ()
    ) -> RewriteResult:
        del history
        normalized = await self._mappings.normalize_async(question)
        parts = [part.strip() for part in self._SEPARATOR.split(normalized) if part.strip()]
        sub_questions = tuple(
            part if part.endswith(("?", "？")) else f"{part}？" for part in parts
        ) or (normalized,)
        return RewriteResult(normalized, sub_questions)


class ModelRewriteService:
    """FAST 档模型改写；任何异常或非法输出都回退规则拆分。"""

    _SYSTEM = (
        "你是检索问题改写器。将用户问题改写为适合知识库检索的完整问题，"
        "并在确有多个独立问题时拆分。只输出 JSON："
        '{"rewrite":"...","sub_questions":["..."]}。'
    )

    def __init__(
        self,
        llm,
        mappings: QueryTermMappingService | None = None,
        *,
        enabled: bool = True,
    ) -> None:
        self._llm = llm
        self._rules = RuleBasedRewriteService(mappings)
        self._enabled = enabled

    async def rewrite_with_split(
        self, question: str, history: Iterable[object] = ()
    ) -> RewriteResult:
        normalized = await self._rules._mappings.normalize_async(question)
        fallback = await self._rules.rewrite_with_split(normalized)
        if not self._enabled:
            return fallback
        messages = [ChatMessage(role=ChatRole.SYSTEM, content=self._SYSTEM)]
        history_items = [item for item in history if getattr(item, "role", None) in {ChatRole.USER, ChatRole.ASSISTANT, "user", "assistant"}]
        for item in history_items[-4:]:
            messages.append(ChatMessage(role=ChatRole(item.role), content=str(getattr(item, "content", ""))))
        messages.append(ChatMessage(role=ChatRole.USER, content=normalized))
        try:
            raw = await self._llm.chat(
                ChatRequest(messages=messages, temperature=0.1, top_p=0.3),
                tier=Tier.FAST,
            )
            data = json.loads(self._strip_fence(raw))
            rewritten = str(data.get("rewrite", "")).strip()
            if not rewritten:
                return fallback
            values = data.get("sub_questions") or [rewritten]
            sub_questions = tuple(str(value).strip() for value in values if str(value).strip())
            return RewriteResult(rewritten, sub_questions or (rewritten,))
        except Exception:
            logger.exception("模型问题改写失败，使用规则兜底")
            return fallback

    @staticmethod
    def _strip_fence(value: str) -> str:
        text = value.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
        return text.strip()
