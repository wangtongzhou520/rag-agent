"""意图树加载与模型分类。"""

import json
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.framework.chat_types import ChatMessage, ChatRequest, ChatRole
from app.framework.logging import get_logger
from app.model_runtime.routing import Tier
from app.rag.intent.cache import IntentTreeCacheManager
from app.rag.intent.node import IntentNode, NodeScore
from app.rag.intent.orm import IntentNodeRecord

logger = get_logger(__name__)


class DefaultIntentClassifier:
    def __init__(self, llm, *, engine: AsyncEngine | None = None, cache: IntentTreeCacheManager | None = None, min_score: float = 0.6) -> None:
        self._llm = llm
        self._sessions = async_sessionmaker(engine, expire_on_commit=False) if engine else None
        self._cache = cache
        self._min_score = min_score

    async def load_intent_tree(self) -> list[IntentNode]:
        if self._sessions is None:
            return []
        if self._cache:
            try:
                cached = await self._cache.get()
                if cached is not None:
                    return cached
            except Exception:
                logger.exception("意图树缓存读取失败")
        try:
            async with self._sessions() as session:
                rows = (await session.scalars(select(IntentNodeRecord).where(IntentNodeRecord.deleted == 0, IntentNodeRecord.enabled == 1).order_by(IntentNodeRecord.level, IntentNodeRecord.id))).all()
            roots = self._build_tree([self._to_domain(row) for row in rows])
            if self._cache:
                await self._cache.put(roots)
            return roots
        except Exception:
            logger.exception("意图树加载失败")
            return []

    async def classify(self, question: str, tree: list[IntentNode] | None = None) -> list[NodeScore]:
        nodes = [node for root in (tree if tree is not None else await self.load_intent_tree()) for node in self._leaves(root)]
        if not nodes:
            return []
        blocks = "\n".join(f"- id={node.id}\n  path={node.full_path or node.name}\n  description={node.description}\n  kind={node.kind}\n  examples={' / '.join(node.examples)}" for node in nodes)
        prompt = f"候选意图：\n{blocks}\n\n问题：{question}\n只输出 JSON 数组：[{{\"id\":1,\"score\":0.9,\"reason\":\"...\"}}]"
        try:
            raw = await self._llm.chat(ChatRequest(messages=[ChatMessage(role=ChatRole.SYSTEM, content="你是意图分类器，只选择最匹配的候选意图。"), ChatMessage(role=ChatRole.USER, content=prompt)], temperature=0.1, top_p=0.3), tier=Tier.STANDARD)
            values = json.loads(self._strip_fence(raw))
            if isinstance(values, dict):
                values = values.get("results", [])
            by_id = {node.id: node for node in nodes}
            scores = [NodeScore(by_id[int(item["id"])], float(item["score"]), str(item.get("reason", ""))) for item in values if int(item.get("id")) in by_id and float(item.get("score", 0)) >= self._min_score]
            return sorted(scores, key=lambda item: item.score, reverse=True)
        except Exception:
            logger.exception("意图分类失败")
            return []

    @staticmethod
    def _build_tree(nodes: list[IntentNode]) -> list[IntentNode]:
        by_code = {node.intent_code: node for node in nodes}
        roots = []
        for node in nodes:
            parent = by_code.get(node.parent_code or "")
            if parent is None:
                roots.append(node)
            else:
                parent.children.append(node)
        def fill(node: IntentNode, prefix: str = "") -> None:
            node.full_path = f"{prefix} > {node.name}" if prefix else node.name
            for child in node.children:
                fill(child, node.full_path)
        for root in roots:
            fill(root)
        return roots

    @staticmethod
    def _leaves(node: IntentNode) -> Iterable[IntentNode]:
        if node.is_leaf():
            yield node
        for child in node.children:
            yield from DefaultIntentClassifier._leaves(child)

    @staticmethod
    def _to_domain(row: IntentNodeRecord) -> IntentNode:
        return IntentNode(id=row.id, intent_code=row.intent_code, name=row.name, level=row.level, kind=row.kind, description=row.description or "", examples=tuple(row.examples or ()), parent_code=row.parent_code, collection_name=row.collection_name, collection_names=tuple(row.collection_names or ()), mcp_tool_id=row.mcp_tool_id, top_k=row.top_k)

    @staticmethod
    def _strip_fence(value: str) -> str:
        text = value.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text
            text = text.rsplit("```", 1)[0]
        return text.strip()
