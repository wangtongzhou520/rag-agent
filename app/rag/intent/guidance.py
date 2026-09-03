"""相近 KB 意图的歧义追问。"""

import json
from dataclasses import dataclass
from typing import Protocol

from app.framework.chat_types import ChatMessage, ChatRequest, ChatRole
from app.framework.logging import get_logger
from app.framework.sse import GuidanceOption, GuidancePayload
from app.model_runtime.routing import Tier
from app.rag.intent.node import IntentKind, NodeScore, SubQuestionIntent

logger = get_logger(__name__)


class AmbiguityChecker(Protocol):
    async def check(self, question: str, candidates: list[NodeScore]) -> bool: ...


class ModelAmbiguityChecker:
    """用 FAST 档模型复核临界分数区间；失败时保守地要求澄清。"""

    _SYSTEM = (
        "你是知识库检索歧义检查器。判断用户问题是否无法在候选知识领域中唯一归类。"
        "只输出 JSON 对象："
        '{"ambiguous":true,"category_ids":[1,2],"reason":"..."}。'
        "当多个候选都合理且问题没有给出明确领域时 ambiguous=true。"
    )

    def __init__(self, llm) -> None:
        self._llm = llm

    async def check(self, question: str, candidates: list[NodeScore]) -> bool:
        candidate_data = [
            {
                "id": item.node.id,
                "name": item.node.full_path or item.node.name,
                "score": round(item.score, 6),
                "reason": item.reason,
            }
            for item in candidates
        ]
        prompt = json.dumps(
            {"question": question, "candidates": candidate_data},
            ensure_ascii=False,
        )
        try:
            raw = await self._llm.chat(
                ChatRequest(
                    messages=[
                        ChatMessage(role=ChatRole.SYSTEM, content=self._SYSTEM),
                        ChatMessage(role=ChatRole.USER, content=prompt),
                    ],
                    temperature=0.1,
                    top_p=0.3,
                ),
                tier=Tier.FAST,
            )
            value = json.loads(self._strip_fence(raw))
            ambiguous = value.get("ambiguous") if isinstance(value, dict) else None
            if not isinstance(ambiguous, bool):
                raise TypeError("ambiguous 必须是布尔值")
            return ambiguous
        except Exception:
            logger.exception("意图歧义二次判断失败，按需要澄清降级")
            return True

    @staticmethod
    def _strip_fence(value: str) -> str:
        text = value.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text
            text = text.rsplit("```", 1)[0]
        return text.strip()


@dataclass(frozen=True, slots=True)
class GuidanceDecision:
    required: bool = False
    message: str = ""
    candidates: tuple[NodeScore, ...] = ()

    def payload(self, question: str) -> GuidancePayload:
        original = question.strip()
        labels = [score.node.full_path or score.node.name for score in self.candidates]
        options = [
            GuidanceOption(
                id=score.node.id,
                intent_code=score.node.intent_code,
                label=label,
                query=_scoped_query(original, f"知识范围：{label}"),
            )
            for score, label in zip(self.candidates, labels, strict=True)
        ]
        return GuidancePayload(
            prompt="请选择更接近你问题的知识范围",
            original_question=original,
            options=options,
            all_query=(
                _scoped_query(original, f"知识范围：{'、'.join(labels)}")
                if len(labels) > 1
                else None
            ),
        )


class IntentGuidanceService:
    def __init__(
        self,
        *,
        enabled: bool = True,
        score_ratio: float = 0.8,
        margin: float = 0.15,
        max_options: int = 6,
        checker: AmbiguityChecker | None = None,
    ) -> None:
        self._enabled = enabled
        self._score_ratio = score_ratio
        self._margin = margin
        self._max_options = max(2, max_options)
        self._checker = checker

    async def detect(
        self, question: str, intents: list[SubQuestionIntent]
    ) -> GuidanceDecision:
        if not self._enabled or len(intents) != 1:
            return GuidanceDecision()
        candidates = sorted(
            (
                score
                for score in intents[0].node_scores
                if score.node.kind == IntentKind.KB and score.score >= 0.35
            ),
            key=lambda item: item.score,
            reverse=True,
        )
        candidates = self._best_per_category(candidates)
        if len(candidates) < 2 or candidates[0].score <= 0:
            return GuidanceDecision()
        normalized = "".join(char.lower() for char in question if char.isalnum())
        if any(
            len(score.node.name.strip()) >= 2
            and "".join(char.lower() for char in score.node.name if char.isalnum())
            in normalized
            for score in candidates
        ):
            return GuidanceDecision()
        ratio = candidates[1].score / candidates[0].score
        lower_bound = self._score_ratio - self._margin
        if ratio < lower_bound:
            return GuidanceDecision()
        ambiguous = ratio >= self._score_ratio
        if not ambiguous:
            if self._checker is None:
                ambiguous = True
            else:
                try:
                    ambiguous = await self._checker.check(question, candidates)
                except Exception:  # noqa: BLE001
                    ambiguous = True
        if not ambiguous:
            return GuidanceDecision()
        selected = tuple(candidates[: self._max_options])
        options = "\n".join(
            f"{index}) {score.node.full_path or score.node.name}"
            for index, score in enumerate(selected, start=1)
        )
        message = (
            f"关于{question.strip()}，在知识库中检索到了以下内容：\n"
            f"{options}\n\n"
            '请问你具体想了解哪个？请回复数字选择（可多选，如 1,2），或回复“都/全部”'
        )
        return GuidanceDecision(True, message, selected)

    @staticmethod
    def _best_per_category(candidates: list[NodeScore]) -> list[NodeScore]:
        """同一 DOMAIN/CATEGORY 下多个主题只保留最高分，避免伪歧义。"""
        grouped: dict[str, NodeScore] = {}
        for candidate in candidates:
            parts = [
                part.strip()
                for part in candidate.node.full_path.split(">")
                if part.strip()
            ]
            key = " > ".join(parts[:2]) if len(parts) >= 3 else " > ".join(parts)
            key = key or candidate.node.intent_code
            grouped.setdefault(key, candidate)
        return list(grouped.values())


def _scoped_query(question: str, suffix: str) -> str:
    decorated = f"（{suffix}）"
    return f"{question[: max(0, 4000 - len(decorated))]}{decorated}"
