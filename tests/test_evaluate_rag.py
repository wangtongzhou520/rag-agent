"""质量回归数据集加载和指标计算。"""

import asyncio
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from scripts.evaluate_rag import (
    EvalCase,
    load_dataset,
    run_case,
    score_case,
    summarize,
    thresholds_pass,
)


def test_repository_dataset_is_versioned_and_loadable() -> None:
    cases = load_dataset(Path("evals/datasets/rag_quality.v2.jsonl"))

    assert len(cases) == 30
    assert len({case.id for case in cases}) == len(cases)
    assert all(case.reference_doc_ids for case in cases)
    assert all(case.reference_answer for case in cases)
    assert all(case.expected_keywords for case in cases)


def test_duplicate_dataset_ids_are_rejected(tmp_path: Path) -> None:
    dataset = tmp_path / "duplicate.jsonl"
    line = '{"id":"one","question":"Q","referenceDocIds":["doc"]}\n'
    dataset.write_text(line + line, encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate case id"):
        load_dataset(dataset)


def test_score_case_calculates_retrieval_and_intent_metrics() -> None:
    case = EvalCase(
        id="one",
        question="Q",
        referenceDocIds=["doc-a", "doc-b"],
        intentLeafIds=["7"],
    )

    result = score_case(
        case,
        {
            "retrievedDocIds": ["noise", "doc-b", "doc-a"],
            "retrievedContextDocIds": ["noise", "doc-b", "doc-b", None],
            "intentLeafIds": ["7"],
            "latencyMs": 42,
        },
    )

    assert result.doc_hit == 1
    assert result.doc_recall == 1
    assert result.reciprocal_rank == 0.5
    assert result.context_precision == 0.5
    assert result.intent_accuracy == 1


def test_score_case_normalizes_and_scores_answer_facts() -> None:
    case = EvalCase(
        id="answer",
        question="Q",
        referenceDocIds=["doc"],
        referenceAnswer="30 个自然日内提交。",
        expectedKeywords=["30个自然日", "发起报销|提交报销"],
    )

    result = score_case(
        case,
        {
            "retrievedDocIds": ["doc"],
            "retrievedContextDocIds": ["doc"],
            "answer": "请在 30 个自然日内发起报销。[1](#cite-1)",
            "answerLatencyMs": 321,
        },
    )

    assert result.answer_keyword_recall == 1
    assert result.answer_complete == 1
    assert result.answer_latency_ms == 321
    assert result.passed is True
    summary = summarize([result])
    assert summary["answerKeywordRecall"] == 1
    assert summary["answerCompleteRate"] == 1
    assert summary["answerLatencyP95Ms"] == 321


def test_summarize_keeps_errors_out_of_metric_denominators() -> None:
    passed = score_case(
        EvalCase(id="ok", question="Q", referenceDocIds=["doc"]),
        {
            "retrievedDocIds": ["doc"],
            "retrievedContextDocIds": ["doc"],
            "latencyMs": 20,
        },
    )
    failed = passed.__class__(
        id="error",
        question="Q2",
        reference_answer="",
        expected_keywords=[],
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
        error="offline",
    )

    summary = summarize([passed, failed])

    assert summary["completed"] == 1
    assert summary["errors"] == 1
    assert summary["docHitRate"] == 1


def test_quality_gate_includes_noise_latency_and_errors() -> None:
    summary = {
        "errors": 0,
        "docHitRate": 1.0,
        "mrr": 1.0,
        "contextPrecision": 0.8167,
        "latencyP95Ms": 3453,
    }
    limits = {
        "min_hit_rate": 0.8,
        "min_mrr": 0.7,
        "min_context_precision": 0.75,
        "max_latency_p95_ms": 5000,
    }

    assert thresholds_pass(summary, **limits) is True
    assert thresholds_pass({**summary, "contextPrecision": 0.74}, **limits) is False
    assert thresholds_pass({**summary, "latencyP95Ms": 5001}, **limits) is False
    assert thresholds_pass({**summary, "errors": 1}, **limits) is False


def test_quality_gate_can_require_answer_metrics() -> None:
    summary = {
        "errors": 0,
        "docHitRate": 1.0,
        "mrr": 1.0,
        "contextPrecision": 0.95,
        "latencyP95Ms": 1200,
        "answerKeywordRecall": 0.92,
        "answerCompleteRate": 0.83,
    }
    limits = {
        "min_hit_rate": 0.8,
        "min_mrr": 0.7,
        "min_context_precision": 0.75,
        "max_latency_p95_ms": 5000,
        "min_answer_keyword_recall": 0.9,
        "min_answer_complete_rate": 0.8,
    }

    assert thresholds_pass(summary, **limits) is True
    assert thresholds_pass(
        {**summary, "answerKeywordRecall": 0.89}, **limits
    ) is False
    assert thresholds_pass(
        {**summary, "answerCompleteRate": 0.79}, **limits
    ) is False


def test_semantic_judge_metrics_are_optional_and_gateable() -> None:
    base = score_case(
        EvalCase(id="semantic", question="Q", referenceDocIds=["doc"]),
        {
            "retrievedDocIds": ["doc"],
            "retrievedContextDocIds": ["doc"],
            "latencyMs": 20,
        },
    )
    results = [
        replace(base, semantic_score=0.95, semantic_verdict="PASS"),
        replace(base, id="partial", semantic_score=0.65, semantic_verdict="PARTIAL"),
    ]

    summary = summarize(results)

    assert summary["semanticScore"] == 0.8
    assert summary["semanticPassRate"] == 0.5
    limits = {
        "min_hit_rate": 0.8,
        "min_mrr": 0.7,
        "min_context_precision": 0.75,
        "max_latency_p95_ms": 5000,
    }
    assert thresholds_pass(summary, **limits) is True
    assert thresholds_pass(summary, **limits, min_semantic_score=0.8) is True
    assert thresholds_pass(summary, **limits, min_semantic_score=0.81) is False


async def test_run_case_can_collect_semantic_judge_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/judge"):
            return httpx.Response(
                200,
                json={
                    "code": "0",
                    "message": "ok",
                    "data": {
                        "score": 0.92,
                        "verdict": "PASS",
                        "contradictions": [],
                        "reason": "事实一致",
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "code": "0",
                "message": "ok",
                "data": {
                    "retrievedDocIds": ["doc"],
                    "retrievedContextDocIds": ["doc"],
                    "retrievedScores": [0.9],
                    "answer": "标准答案",
                    "answerLatencyMs": 100,
                    "latencyMs": 20,
                },
            },
        )

    case = EvalCase(
        id="judge",
        question="问题",
        referenceDocIds=["doc"],
        referenceAnswer="标准答案",
        expectedKeywords=["标准答案"],
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        result = await run_case(
            client,
            case,
            asyncio.Semaphore(1),
            ["baseline"],
            include_answer=True,
            judge_answers=True,
        )

    assert result.error is None
    assert result.semantic_score == 0.92
    assert result.semantic_verdict == "PASS"
