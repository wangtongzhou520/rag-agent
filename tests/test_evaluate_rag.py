"""质量回归数据集加载和指标计算。"""

import asyncio
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from scripts.evaluate_rag import (
    EvalCase,
    is_abstention,
    load_dataset,
    run_case,
    score_case,
    select_cases,
    summarize,
    thresholds_pass,
)


def test_repository_dataset_is_versioned_and_loadable() -> None:
    cases = load_dataset(Path("evals/datasets/rag_quality.v3.jsonl"))

    assert len(cases) == 42
    assert len({case.id for case in cases}) == len(cases)
    assert all(case.reference_doc_ids for case in cases)
    assert all(case.reference_answer for case in cases)
    assert all(case.expected_keywords for case in cases)
    assert len([case for case in cases if "hard" in case.tags]) == 12


def test_select_cases_filters_by_all_tags_before_limit() -> None:
    cases = [
        EvalCase(id="one", question="Q1", referenceDocIds=["doc"], tags=["hard"]),
        EvalCase(
            id="two",
            question="Q2",
            referenceDocIds=["doc"],
            tags=["hard", "cross-doc"],
        ),
        EvalCase(
            id="three",
            question="Q3",
            referenceDocIds=["doc"],
            tags=["hard", "cross-doc"],
        ),
    ]

    selected = select_cases(cases, ["hard", "cross-doc"], 1)

    assert [case.id for case in selected] == ["two"]


def test_select_cases_rejects_empty_result() -> None:
    cases = [EvalCase(id="one", question="Q", referenceDocIds=["doc"])]

    with pytest.raises(ValueError, match="no evaluation cases"):
        select_cases(cases, ["missing"], None)


def test_duplicate_dataset_ids_are_rejected(tmp_path: Path) -> None:
    dataset = tmp_path / "duplicate.jsonl"
    line = '{"id":"one","question":"Q","referenceDocIds":["doc"]}\n'
    dataset.write_text(line + line, encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate case id"):
        load_dataset(dataset)


def test_unanswerable_dataset_allows_empty_reference_docs(tmp_path: Path) -> None:
    dataset = tmp_path / "unanswerable.jsonl"
    dataset.write_text(
        '{"id":"unknown","question":"Q","answerable":false,'
        '"referenceDocIds":[],"referenceAnswer":"资料未说明"}\n',
        encoding="utf-8",
    )

    cases = load_dataset(dataset)

    assert cases[0].answerable is False
    assert cases[0].reference_doc_ids == []


def test_dataset_rejects_answerability_doc_mismatch(tmp_path: Path) -> None:
    dataset = tmp_path / "invalid.jsonl"
    dataset.write_text(
        '{"id":"unknown","question":"Q","answerable":false,'
        '"referenceDocIds":["doc"]}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unanswerable cases must not declare docs"):
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


def test_score_case_rewards_grounded_abstention_without_evidence() -> None:
    case = EvalCase(
        id="unknown",
        question="Q",
        answerable=False,
        referenceDocIds=[],
        referenceAnswer="现有资料未说明。",
    )

    result = score_case(
        case,
        {
            "retrievedDocIds": [],
            "retrievedContextDocIds": [],
            "answer": "现有资料未说明该事项，无法确定。",
        },
    )

    assert result.passed is True
    assert result.doc_hit == 1
    assert result.abstained is True
    assert result.answer_complete == 1
    summary = summarize([result])
    assert summary["answerCompleteRate"] is None
    assert summary["unanswerableAbstentionRate"] == 1
    assert summary["unanswerableNoEvidenceRate"] == 1


def test_score_case_flags_irrelevant_evidence_and_unsupported_answer() -> None:
    case = EvalCase(
        id="unknown",
        question="Q",
        answerable=False,
        referenceDocIds=[],
    )

    result = score_case(
        case,
        {
            "retrievedDocIds": ["unrelated"],
            "retrievedContextDocIds": ["unrelated"],
            "answer": "答案是 10 天。",
        },
    )

    assert result.passed is False
    assert result.doc_hit == 1
    assert result.context_precision == 1
    assert result.no_evidence is False
    assert result.abstained is False
    assert result.answer_complete == 0


def test_abstention_detection_does_not_confuse_boundary_negation() -> None:
    assert is_abstention("提供的资料未说明海外住宿标准。") is True
    assert is_abstention("资料未指定必须使用哪一种沟通工具。") is True
    assert is_abstention("无法确认试用期员工是否适用不同额度。") is True
    assert is_abstention("当前资料未包含客户赔偿比例信息。") is True
    assert is_abstention("资料中未说明工具，现有资料未明确。") is True
    assert is_abstention("资料未提及折现，因此不能折现。") is False
    assert is_abstention("正好 5000 元不需要财务负责人复核。") is False


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


def test_quality_gate_can_require_unanswerable_abstention() -> None:
    summary = {
        "errors": 0,
        "docHitRate": 1.0,
        "mrr": 1.0,
        "contextPrecision": 1.0,
        "latencyP95Ms": 1200,
        "unanswerableAbstentionRate": 0.875,
    }
    limits = {
        "min_hit_rate": 0.8,
        "min_mrr": 0.7,
        "min_context_precision": 0.75,
        "max_latency_p95_ms": 5000,
    }

    assert (
        thresholds_pass(
            summary, **limits, min_unanswerable_abstention_rate=0.8
        )
        is True
    )
    assert (
        thresholds_pass(
            summary, **limits, min_unanswerable_abstention_rate=0.9
        )
        is False
    )


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
                    "retrievedContexts": ["标准答案和补充依据"],
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
