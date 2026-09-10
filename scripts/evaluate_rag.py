"""对版本化 JSONL 数据集运行 RAG 纯检索质量回归。"""

import argparse
import asyncio
import json
import math
import os
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field


class EvalCase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    question: str
    reference_doc_ids: list[str] = Field(alias="referenceDocIds")
    intent_leaf_ids: list[str | None] = Field(
        default_factory=list, alias="intentLeafIds"
    )
    tags: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CaseResult:
    id: str
    question: str
    passed: bool
    doc_hit: float
    doc_recall: float
    reciprocal_rank: float
    context_precision: float
    intent_accuracy: float | None
    latency_ms: int
    retrieved_doc_ids: list[str]
    retrieved_context_doc_ids: list[str | None]
    retrieved_scores: list[float]
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
    return CaseResult(
        id=case.id,
        question=case.question,
        passed=bool(matching),
        doc_hit=float(bool(matching)),
        doc_recall=round(doc_recall, 4),
        reciprocal_rank=round(1 / first_rank if first_rank else 0.0, 4),
        context_precision=round(
            relevant_contexts / len(context_docs) if context_docs else 0.0, 4
        ),
        intent_accuracy=round(intent_accuracy, 4)
        if intent_accuracy is not None
        else None,
        latency_ms=int(response.get("latencyMs") or 0),
        retrieved_doc_ids=retrieved,
        retrieved_context_doc_ids=[
            str(value) if value is not None else None for value in context_docs
        ],
        retrieved_scores=[
            round(float(value), 6) for value in response.get("retrievedScores") or []
        ],
    )


def summarize(results: list[CaseResult]) -> dict[str, Any]:
    valid = [result for result in results if result.error is None]
    intent_values = [
        result.intent_accuracy
        for result in valid
        if result.intent_accuracy is not None
    ]
    latencies = sorted(result.latency_ms for result in valid)
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
        "latencyP95Ms": latencies[p95_index] if latencies else 0,
    }


def thresholds_pass(
    summary: dict[str, Any],
    *,
    min_hit_rate: float,
    min_mrr: float,
    min_context_precision: float,
    max_latency_p95_ms: int,
) -> bool:
    return bool(
        summary["errors"] == 0
        and summary["docHitRate"] >= min_hit_rate
        and summary["mrr"] >= min_mrr
        and summary["contextPrecision"] >= min_context_precision
        and summary["latencyP95Ms"] <= max_latency_p95_ms
    )


async def run_case(
    client: httpx.AsyncClient, case: EvalCase, semaphore: asyncio.Semaphore
) -> CaseResult:
    try:
        async with semaphore:
            response = await client.get("/rag/eval", params={"question": case.question})
        response.raise_for_status()
        payload = response.json()
        if str(payload.get("code")) != "0" or not isinstance(payload.get("data"), dict):
            raise ValueError(payload.get("message") or "invalid Result payload")
        return score_case(case, payload["data"])
    except Exception as exc:  # noqa: BLE001 - 每条失败必须留在批次报告中
        return CaseResult(
            id=case.id,
            question=case.question,
            passed=False,
            doc_hit=0,
            doc_recall=0,
            reciprocal_rank=0,
            context_precision=0,
            intent_accuracy=None,
            latency_ms=0,
            retrieved_doc_ids=[],
            retrieved_context_doc_ids=[],
            retrieved_scores=[],
            error=str(exc),
        )


async def run(args: argparse.Namespace) -> dict[str, Any]:
    cases = load_dataset(args.dataset)
    headers = {}
    token = os.getenv(args.token_env, "").strip()
    if token:
        headers["Authorization"] = token
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"), headers=headers, timeout=args.timeout
    ) as client:
        semaphore = asyncio.Semaphore(args.concurrency)
        results = await asyncio.gather(
            *(run_case(client, case, semaphore) for case in cases)
        )
    summary = summarize(results)
    summary["thresholdsPassed"] = thresholds_pass(
        summary,
        min_hit_rate=args.min_hit_rate,
        min_mrr=args.min_mrr,
        min_context_precision=args.min_context_precision,
        max_latency_p95_ms=args.max_latency_p95_ms,
    )
    return {
        "dataset": str(args.dataset),
        "baseUrl": args.base_url,
        "thresholds": {
            "minHitRate": args.min_hit_rate,
            "minMrr": args.min_mrr,
            "minContextPrecision": args.min_context_precision,
            "maxLatencyP95Ms": args.max_latency_p95_ms,
        },
        "summary": summary,
        "cases": [asdict(result) for result in results],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", type=Path, default=Path("evals/datasets/rag_quality.v1.jsonl")
    )
    parser.add_argument(
        "--base-url", default="http://127.0.0.1:9090/api/ragent"
    )
    parser.add_argument("--token-env", default="RAGENT_EVAL_TOKEN")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--min-hit-rate", type=float, default=0.8)
    parser.add_argument("--min-mrr", type=float, default=0.7)
    parser.add_argument("--min-context-precision", type=float, default=0.75)
    parser.add_argument("--max-latency-p95-ms", type=int, default=5000)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.concurrency <= 0 or args.timeout <= 0:
        raise SystemExit("concurrency and timeout must be greater than zero")
    if not all(
        0 <= value <= 1
        for value in (args.min_hit_rate, args.min_mrr, args.min_context_precision)
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
