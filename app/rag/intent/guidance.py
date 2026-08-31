"""相近 KB 意图的歧义追问。"""

from dataclasses import dataclass
from typing import Protocol

from app.rag.intent.node import IntentKind, NodeScore, SubQuestionIntent


class AmbiguityChecker(Protocol):
    async def check(self, question: str, candidates: list[NodeScore]) -> bool: ...


@dataclass(frozen=True, slots=True)
class GuidanceDecision:
    required: bool = False
    message: str = ""
    candidates: tuple[NodeScore, ...] = ()


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
