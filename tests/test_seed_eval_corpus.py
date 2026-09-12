"""评测语料播种脚本的纯函数行为。"""

from pathlib import Path

import pytest

from scripts.seed_eval_corpus import (
    KnowledgeBase,
    SeedError,
    build_summary,
    chunk_required,
    pick_collection,
    select_uploads,
    split_documents,
    unwrap,
)


def test_unwrap_returns_data_and_rejects_business_error() -> None:
    assert unwrap({"code": "0", "data": {"id": 1}}) == {"id": 1}

    with pytest.raises(SeedError, match="无管理员权限"):
        unwrap({"code": "403", "message": "无管理员权限"})


def test_pick_collection_requires_exact_collection_name() -> None:
    records = [
        {"id": 7, "name": "其他集合", "collectionName": "other_collection"},
        {"id": 9, "name": "M5 基线", "collectionName": "m5_quality_baseline"},
    ]

    picked = pick_collection(records, "m5_quality_baseline")

    assert picked == KnowledgeBase(id=9, name="M5 基线", collection_name="m5_quality_baseline")
    assert pick_collection(records, "m5_quality_baseline_v2") is None


def test_select_uploads_skips_existing_documents_in_stable_order() -> None:
    files = [
        Path("evals/corpus/reimbursement_policy.md"),
        Path("evals/corpus/leave_policy.md"),
        Path("evals/corpus/incident_response.md"),
    ]

    selected = select_uploads(files, {"leave_policy.md"})

    assert [path.name for path in selected] == [
        "incident_response.md",
        "reimbursement_policy.md",
    ]


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ({"status": "success", "chunkCount": 2}, False),
        ({"status": "success", "chunkCount": 0}, True),
        ({"status": "pending", "chunkCount": 0}, True),
        ({"status": "running", "chunkCount": 0}, True),
        ({"status": "failed", "chunkCount": 0}, True),
    ],
)
def test_chunk_required_covers_lifecycle(document: dict, expected: bool) -> None:
    assert chunk_required(document) is expected


def test_split_documents_groups_lifecycle_states() -> None:
    documents = [
        {"id": 1, "status": "success", "chunkCount": 2},
        {"id": 2, "status": "running", "chunkCount": 0},
        {"id": 3, "status": "failed", "chunkCount": 0},
        {"id": 4, "status": "success", "chunkCount": 0},
    ]

    ready, running, failed = split_documents(documents)

    assert [item["id"] for item in ready] == [1]
    assert [item["id"] for item in running] == [2, 4]
    assert [item["id"] for item in failed] == [3]


def test_build_summary_marks_seeded_only_when_nothing_left() -> None:
    kb = KnowledgeBase(id=1, name="M5", collection_name="m5_quality_baseline")
    documents = [
        {"id": 2, "docName": "b.md", "status": "success", "chunkCount": 1},
        {"id": 1, "docName": "a.md", "status": "success", "chunkCount": 3},
    ]

    summary = build_summary("http://127.0.0.1:9090/api/ragent", kb.collection_name, kb, documents)

    assert summary["seeded"] is True
    assert summary["failedCount"] == 0
    assert [item["docName"] for item in summary["documents"]] == ["a.md", "b.md"]

    pending = build_summary(
        "http://127.0.0.1:9090/api/ragent",
        kb.collection_name,
        kb,
        [{"id": 3, "docName": "c.md", "status": "running", "chunkCount": 0}],
    )

    assert pending["seeded"] is False
    assert pending["runningCount"] == 1
