"""对版本化 JSONL 数据集运行 RAG 检索与可选答案质量回归。"""

import argparse
import asyncio
import json
import math
import os
import statistics
import sys
import unicodedata
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field


class EvalCase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    question: str
    reference_doc_ids: list[str] = Field(alias="referenceDocIds")
    reference_answer: str = Field(default="", alias="referenceAnswer")
    expected_keywords: list[str] = Field(default_factory=list, alias="expectedKeywords")
    intent_leaf_ids: list[str | None] = Field(
        default_factory=list, alias="intentLeafIds"
    )
    tags: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CaseResult:
    id: str
    question: str
    reference_answer: str
    expected_keywords: list[str]
    passed: bool
    doc_hit: float
    doc_recall: float
    reciprocal_rank: float
    context_precision: float
    intent_accuracy: float | None
    answer_keyword_recall: float | None
    answer_complete: float | None
    latency_ms: int
    answer_latency_ms: int | None
    answer: str | None
    retrieved_doc_ids: list[str]
    retrieved_context_doc_ids: list[str | None]
    retrieved_scores: list[float]
    semantic_score: float | None = None
    semantic_verdict: str | None = None
    semantic_reason: str | None = None
    semantic_contradictions: list[str] | None = None
    error: str | None = None


def load_dataset(path: Path) -> list[EvalCase]:
    cases: list[EvalCase] = []
    seen: set[str] = set()
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        case = EvalCase.model_validate_json(line)
        if case.id in seen:
            raise ValueError(f"duplicate case id at line {line_number}: {case.id}")
        if not case.question.strip() or not case.reference_doc_ids:
            raise ValueError(f"invalid case at line {line_number}: question/docs required")
        seen.add(case.id)
        cases.append(case)
    if not cases:
        raise ValueError("dataset is empty")
    return cases


def score_case(case: EvalCase, response: dict[str, Any]) -> CaseResult:
    retrieved = [str(value) for value in response.get("retrievedDocIds") or []]
    context_docs = response.get("retrievedContextDocIds") or []
    expected = set(case.reference_doc_ids)
    matching = expected.intersection(retrieved)
    first_rank = next(
        (index for index, value in enumerate(retrieved, 1) if value in expected), None
    )
    relevant_contexts = sum(value in expected for value in context_docs if value)
    expected_intents = case.intent_leaf_ids
    actual_intents = response.get("intentLeafIds") or []
    intent_accuracy = None
    if expected_intents:
        matched = sum(
            expected_value is not None
            and index < len(actual_intents)
            and str(actual_intents[index]) == expected_value
            for index, expected_value in enumerate(expected_intents)
        )
        comparable = sum(value is not None for value in expected_intents)
        intent_accuracy = matched / comparable if comparable else None
    doc_recall = len(matching) / len(expected)
    answer_value = response.get("answer")
    answer = str(answer_value) if answer_value is not None else None
    answer_keyword_recall = None
    answer_complete = None
    if answer is not None and case.expected_keywords:
        normalized_answer = normalize_fact_text(answer)
        matched_keywords = sum(
            any(
                normalize_fact_text(option) in normalized_answer
                for option in keyword.split("|")
                if option.strip()
            )
            for keyword in case.expected_keywords
        )
        answer_keyword_recall = round(
            matched_keywords / len(case.expected_keywords), 4
        )
        answer_complete = float(matched_keywords == len(case.expected_keywords))
    return CaseResult(
        id=case.id,
        question=case.question,
        reference_answer=case.reference_answer,
        expected_keywords=case.expected_keywords,
        passed=bool(matching) and answer_complete != 0,
        doc_hit=float(bool(matching)),
        doc_recall=round(doc_recall, 4),
        reciprocal_rank=round(1 / first_rank if first_rank else 0.0, 4),
        context_precision=round(
            relevant_contexts / len(context_docs) if context_docs else 0.0, 4
        ),
        intent_accuracy=round(intent_accuracy, 4)
        if intent_accuracy is not None
        else None,
        answer_keyword_recall=answer_keyword_recall,
        answer_complete=answer_complete,
        latency_ms=int(response.get("latencyMs") or 0),
        answer_latency_ms=(
            int(response["answerLatencyMs"])
            if response.get("answerLatencyMs") is not None
            else None
        ),
        answer=answer,
        retrieved_doc_ids=retrieved,
        retrieved_context_doc_ids=[
            str(value) if value is not None else None for value in context_docs
        ],
        retrieved_scores=[
            round(float(value), 6) for value in response.get("retrievedScores") or []
        ],
    )


def normalize_fact_text(value: str) -> str:
    """统一全半角、大小写并去掉标点空白，降低格式差异对事实匹配的影响。"""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def summarize(results: list[CaseResult]) -> dict[str, Any]:
    valid = [result for result in results if result.error is None]
    intent_values = [
        result.intent_accuracy
        for result in valid
        if result.intent_accuracy is not None
    ]
    latencies = sorted(result.latency_ms for result in valid)
    answer_latencies = sorted(
        result.answer_latency_ms
        for result in valid
        if result.answer_latency_ms is not None
    )
    semantic_scores = [
        result.semantic_score
        for result in valid
        if result.semantic_score is not None
    ]
    semantic_verdicts = [
        result.semantic_verdict
        for result in valid
        if result.semantic_verdict is not None
    ]
    p95_index = max(0, min(len(latencies) - 1, math.ceil(len(latencies) * 0.95) - 1))
    mean = lambda values: round(statistics.fmean(values), 4) if values else 0.0
    return {
        "total": len(results),
        "completed": len(valid),
        "errors": len(results) - len(valid),
        "docHitRate": mean([result.doc_hit for result in valid]),
        "docRecall": mean([result.doc_recall for result in valid]),
        "mrr": mean([result.reciprocal_rank for result in valid]),
        "contextPrecision": mean([result.context_precision for result in valid]),
        "intentAccuracy": mean(intent_values) if intent_values else None,
        "answerKeywordRecall": mean(
            [
                result.answer_keyword_recall
                for result in valid
                if result.answer_keyword_recall is not None
            ]
        )
        if any(result.answer_keyword_recall is not None for result in valid)
        else None,
        "answerCompleteRate": mean(
            [
                result.answer_complete
                for result in valid
                if result.answer_complete is not None
            ]
        )
        if any(result.answer_complete is not None for result in valid)
        else None,
        "latencyP95Ms": latencies[p95_index] if latencies else 0,
        "answerLatencyP95Ms": (
            answer_latencies[
                max(
                    0,
                    min(
                        len(answer_latencies) - 1,
                        math.ceil(len(answer_latencies) * 0.95) - 1,
                    ),
                )
            ]
            if answer_latencies
            else None
        ),
        "semanticScore": mean(semantic_scores) if semantic_scores else None,
        "semanticPassRate": (
            round(semantic_verdicts.count("PASS") / len(semantic_verdicts), 4)
            if semantic_verdicts
            else None
        ),
    }


def thresholds_pass(
    summary: dict[str, Any],
    *,
    min_hit_rate: float,
    min_mrr: float,
    min_context_precision: float,
    max_latency_p95_ms: int,
    min_answer_keyword_recall: float | None = None,
    min_answer_complete_rate: float | None = None,
    min_semantic_score: float | None = None,
) -> bool:
    return bool(
        summary["errors"] == 0
        and summary["docHitRate"] >= min_hit_rate
        and summary["mrr"] >= min_mrr
        and summary["contextPrecision"] >= min_context_precision
        and summary["latencyP95Ms"] <= max_latency_p95_ms
        and (
            min_answer_keyword_recall is None
            or (
                summary["answerKeywordRecall"] is not None
                and summary["answerKeywordRecall"] >= min_answer_keyword_recall
            )
        )
        and (
            min_answer_complete_rate is None
            or (
                summary["answerCompleteRate"] is not None
                and summary["answerCompleteRate"] >= min_answer_complete_rate
            )
        )
        and (
            min_semantic_score is None
            or (
                summary["semanticScore"] is not None
                and summary["semanticScore"] >= min_semantic_score
            )
        )
    )


async def run_case(
    client: httpx.AsyncClient,
    case: EvalCase,
    semaphore: asyncio.Semaphore,
    collections: list[str],
    include_answer: bool,
    judge_answers: bool,
) -> CaseResult:
    try:
        async with semaphore:
            params = [("question", case.question)]
            params.extend(("collection", value) for value in collections)
            if include_answer:
                params.append(("includeAnswer", "true"))
            response = await client.get("/rag/eval", params=params)
        response.raise_for_status()
        payload = response.json()
        if str(payload.get("code")) != "0" or not isinstance(payload.get("data"), dict):
            raise ValueError(payload.get("message") or "invalid Result payload")
        result = score_case(case, payload["data"])
        if judge_answers:
            try:
                async with semaphore:
                    judge_response = await client.post(
                        "/rag/eval/judge",
                        json={
                            "question": case.question,
                            "referenceAnswer": case.reference_answer,
                            "candidateAnswer": result.answer,
                            "expectedKeywords": case.expected_keywords,
                            "contexts": payload["data"].get("retrievedContexts")
                            or [],
                        },
                    )
                judge_response.raise_for_status()
                judge_payload = judge_response.json()
                judge_data = judge_payload.get("data")
                if str(judge_payload.get("code")) != "0" or not isinstance(
                    judge_data, dict
                ):
                    raise ValueError(
                        judge_payload.get("message") or "invalid judge response"
                    )
                result = replace(
                    result,
                    semantic_score=round(float(judge_data["score"]), 4),
                    semantic_verdict=str(judge_data["verdict"]),
                    semantic_reason=str(judge_data["reason"]),
                    semantic_contradictions=[
                        str(value) for value in judge_data.get("contradictions") or []
                    ],
                )
            except Exception as exc:  # noqa: BLE001 - 裁判错误必须使该题显式失败
                return replace(result, passed=False, error=f"judge: {exc}")
        return result
    except Exception as exc:  # noqa: BLE001 - 每条失败必须留在批次报告中
        return CaseResult(
            id=case.id,
            question=case.question,
            reference_answer=case.reference_answer,
            expected_keywords=case.expected_keywords,
            passed=False,
            doc_hit=0,
            doc_recall=0,
            reciprocal_rank=0,
            context_precision=0,
            intent_accuracy=None,
            answer_keyword_recall=None,
            answer_complete=None,
            latency_ms=0,
            answer_latency_ms=None,
            answer=None,
            retrieved_doc_ids=[],
            retrieved_context_doc_ids=[],
            retrieved_scores=[],
            error=str(exc),
        )


async def run(args: argparse.Namespace) -> dict[str, Any]:
    cases = load_dataset(args.dataset)
    if args.limit is not None:
        cases = cases[: args.limit]
    headers = {}
    token = os.getenv(args.token_env, "").strip()
    if token:
        headers["Authorization"] = token
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"), headers=headers, timeout=args.timeout
    ) as client:
        semaphore = asyncio.Semaphore(args.concurrency)
        results = await asyncio.gather(
            *(
                run_case(
                    client,
                    case,
                    semaphore,
                    args.collection,
                    args.with_answers,
                    args.judge_answers,
                )
                for case in cases
            )
        )
    summary = summarize(results)
    summary["thresholdsPassed"] = thresholds_pass(
        summary,
        min_hit_rate=args.min_hit_rate,
        min_mrr=args.min_mrr,
        min_context_precision=args.min_context_precision,
        max_latency_p95_ms=args.max_latency_p95_ms,
        min_answer_keyword_recall=(
            args.min_answer_keyword_recall if args.with_answers else None
        ),
        min_answer_complete_rate=(
            args.min_answer_complete_rate if args.with_answers else None
        ),
        min_semantic_score=args.min_semantic_score if args.judge_answers else None,
    )
    payload = {
        "dataset": str(args.dataset),
        "baseUrl": args.base_url,
        "collections": args.collection,
        "includeAnswers": args.with_answers,
        "label": args.label,
        "thresholds": {
            "minHitRate": args.min_hit_rate,
            "minMrr": args.min_mrr,
            "minContextPrecision": args.min_context_precision,
            "maxLatencyP95Ms": args.max_latency_p95_ms,
            "minAnswerKeywordRecall": (
                args.min_answer_keyword_recall if args.with_answers else None
            ),
            "minAnswerCompleteRate": (
                args.min_answer_complete_rate if args.with_answers else None
            ),
            "minSemanticScore": (
                args.min_semantic_score if args.judge_answers else None
            ),
        },
        "summary": summary,
        "cases": [asdict(result) for result in results],
    }
    if args.publish_report:
        async with httpx.AsyncClient(
            base_url=args.base_url.rstrip("/"), headers=headers, timeout=args.timeout
        ) as client:
            response = await client.post("/rag/eval/reports", json=payload)
            response.raise_for_status()
            published = response.json()
            if str(published.get("code")) != "0" or not isinstance(
                published.get("data"), dict
            ):
                raise ValueError(published.get("message") or "invalid report response")
            payload["reportId"] = published["data"].get("reportId")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", type=Path, default=Path("evals/datasets/rag_quality.v2.jsonl")
    )
    parser.add_argument(
        "--base-url", default="http://127.0.0.1:9090/api/ragent"
    )
    parser.add_argument("--token-env", default="RAGENT_EVAL_TOKEN")
    parser.add_argument(
        "--collection",
        action="append",
        default=None,
        help="limit retrieval to a collection; repeat for multiple collections",
    )
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument(
        "--limit",
        type=int,
        help="run only the first N cases for smoke testing",
    )
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument(
        "--with-answers",
        action="store_true",
        help="generate grounded answers and enable answer quality gates",
    )
    parser.add_argument(
        "--judge-answers",
        action="store_true",
        help="generate answers and ask the model judge for semantic correctness",
    )
    parser.add_argument("--min-hit-rate", type=float, default=0.8)
    parser.add_argument("--min-mrr", type=float, default=0.7)
    parser.add_argument("--min-context-precision", type=float, default=0.75)
    parser.add_argument("--max-latency-p95-ms", type=int, default=5000)
    parser.add_argument("--min-answer-keyword-recall", type=float, default=0.9)
    parser.add_argument("--min-answer-complete-rate", type=float, default=0.8)
    parser.add_argument(
        "--min-semantic-score",
        type=float,
        help="optional semantic-score gate; omitted means observation only",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--publish-report",
        action="store_true",
        help="persist this batch in the deployed admin report history",
    )
    parser.add_argument("--label", help="optional human-readable report label")
    args = parser.parse_args()
    if args.collection is None:
        args.collection = ["m5_quality_baseline"]
    if args.min_semantic_score is not None:
        args.judge_answers = True
    if args.judge_answers:
        args.with_answers = True
    return args


def main() -> None:
    args = parse_args()
    if (
        args.concurrency <= 0
        or args.timeout <= 0
        or (args.limit is not None and args.limit <= 0)
    ):
        raise SystemExit("concurrency, timeout and limit must be greater than zero")
    if not all(
        0 <= value <= 1
        for value in (
            args.min_hit_rate,
            args.min_mrr,
            args.min_context_precision,
            args.min_answer_keyword_recall,
            args.min_answer_complete_rate,
            *(
                [args.min_semantic_score]
                if args.min_semantic_score is not None
                else []
            ),
        )
    ):
        raise SystemExit("thresholds must be between zero and one")
    if args.max_latency_p95_ms <= 0:
        raise SystemExit("max latency must be greater than zero")
    payload = asyncio.run(run(args))
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    sys.stdout.write(rendered + "\n")
    if not payload["summary"]["thresholdsPassed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
