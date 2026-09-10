"""质量回归数据集加载和指标计算。"""

from pathlib import Path

import pytest

from scripts.evaluate_rag import EvalCase, load_dataset, score_case, summarize


def test_repository_dataset_is_versioned_and_loadable() -> None:
    cases = load_dataset(Path("evals/datasets/rag_quality.v1.jsonl"))

    assert len(cases) == 6
    assert len({case.id for case in cases}) == len(cases)
    assert all(case.reference_doc_ids for case in cases)


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
        passed=False,
        doc_hit=0,
        doc_recall=0,
        reciprocal_rank=0,
        context_precision=0,
        intent_accuracy=None,
        latency_ms=0,
        retrieved_doc_ids=[],
        error="offline",
    )

    summary = summarize([passed, failed])

    assert summary["completed"] == 1
    assert summary["errors"] == 1
    assert summary["docHitRate"] == 1
