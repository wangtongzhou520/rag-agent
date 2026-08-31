"""多子问题意图并行解析与总量封顶。"""

import asyncio

from app.rag.intent.classifier import DefaultIntentClassifier
from app.rag.intent.node import SubQuestionIntent
from app.rag.rewrite.models import RewriteResult


class IntentResolver:
    def __init__(self, classifier: DefaultIntentClassifier, *, max_per_question: int = 3, max_total: int = 3) -> None:
        self._classifier = classifier
        self._max_per_question = max_per_question
        self._max_total = max_total

    async def resolve(self, rewrite_result: RewriteResult) -> list[SubQuestionIntent]:
        async def one(question: str) -> SubQuestionIntent:
            try:
                scores = (await self._classifier.classify(question))[: self._max_per_question]
            except Exception:  # noqa: BLE001
                scores = []
            return SubQuestionIntent(question, tuple(scores))
        results = list(await asyncio.gather(*(one(question) for question in rewrite_result.sub_questions)))
        if sum(len(item.node_scores) for item in results) <= self._max_total:
            return results
        kept: list[SubQuestionIntent] = []
        quota = self._max_total
        for item in results:
            scores = item.node_scores[:1] if quota else ()
            quota -= len(scores)
            kept.append(SubQuestionIntent(item.sub_question, tuple(scores)))
        rest = sorted(((score, index) for index, item in enumerate(results) for score in item.node_scores[1:]), key=lambda value: value[0].score, reverse=True)
        mutable = [list(item.node_scores) for item in kept]
        for score, index in rest:
            if quota <= 0:
                break
            mutable[index].append(score)
            quota -= 1
        return [SubQuestionIntent(results[index].sub_question, tuple(scores)) for index, scores in enumerate(mutable)]
