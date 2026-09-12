"""把 evals/corpus 播种到指定部署的隔离评测知识库。

用途：让真实 RAG 质量门禁可以在一台全新部署上无人值守地跑起来。脚本会创建（或复用）
``collectionName=m5_quality_baseline`` 的知识库、上传缺失语料、触发分块并等待向量化结束。
对已完成的文档是幂等的：状态为 success 且已有 chunk 的文档不会重复上传或重建，可反复执行。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

READY_STATUS = "success"
FAILED_STATUS = "failed"
DEFAULT_COLLECTION = "m5_quality_baseline"
DEFAULT_EMBEDDING_MODEL = "qwen3.7-text-embedding"
DEFAULT_CORPUS = Path("evals/corpus")


class SeedError(RuntimeError):
    """播种过程中的可诊断错误。"""


@dataclass(frozen=True)
class KnowledgeBase:
    id: int
    name: str
    collection_name: str


def unwrap(payload: dict[str, Any]) -> Any:
    """校验 Result<T> 包装，失败时抛出携带服务端 message 的错误。"""

    if str(payload.get("code")) != "0":
        raise SeedError(str(payload.get("message") or f"unexpected payload: {payload}"))
    return payload.get("data")


def pick_collection(records: list[dict[str, Any]], collection_name: str) -> KnowledgeBase | None:
    """按 collectionName 精确匹配知识库，避免复用同名的其他集合。"""

    for record in records:
        if str(record.get("collectionName")) == collection_name:
            return KnowledgeBase(
                id=int(record["id"]),
                name=str(record.get("name") or ""),
                collection_name=collection_name,
            )
    return None


def select_uploads(files: list[Path], existing_names: set[str]) -> list[Path]:
    """只上传知识库里还不存在的语料文件，保持脚本可重复执行。"""

    return sorted(
        (path for path in files if path.name not in existing_names),
        key=lambda path: path.name,
    )


def chunk_required(document: dict[str, Any]) -> bool:
    """未完成、失败或没有产出 chunk 的文档需要（重新）触发分块。"""

    status = str(document.get("status"))
    if status == FAILED_STATUS:
        return True
    if status != READY_STATUS:
        return True
    return int(document.get("chunkCount") or 0) <= 0


def split_documents(
    documents: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """把文档切成 (就绪, 处理中, 失败) 三组，供等待循环判定。"""

    ready: list[dict[str, Any]] = []
    running: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for document in documents:
        status = str(document.get("status"))
        if status == FAILED_STATUS:
            failed.append(document)
        elif status == READY_STATUS and int(document.get("chunkCount") or 0) > 0:
            ready.append(document)
        else:
            running.append(document)
    return ready, running, failed


def build_summary(
    base_url: str,
    collection: str,
    kb: KnowledgeBase,
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    ready, running, failed = split_documents(documents)
    return {
        "baseUrl": base_url,
        "collection": collection,
        "knowledgeBaseId": kb.id,
        "documents": [
            {
                "id": int(document["id"]),
                "docName": str(document.get("docName")),
                "status": str(document.get("status")),
                "chunkCount": int(document.get("chunkCount") or 0),
            }
            for document in sorted(documents, key=lambda item: int(item["id"]))
        ],
        "readyCount": len(ready),
        "runningCount": len(running),
        "failedCount": len(failed),
        "seeded": len(failed) == 0 and not running,
    }


async def list_bases(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    response = await client.get("/knowledge-base", params={"current": 1, "size": 100})
    response.raise_for_status()
    data = unwrap(response.json())
    records = (data or {}).get("records") or []
    return [record for record in records if isinstance(record, dict)]


async def ensure_base(
    client: httpx.AsyncClient,
    collection: str,
    name: str,
    embedding_model: str,
) -> tuple[KnowledgeBase, bool]:
    existing = pick_collection(await list_bases(client), collection)
    if existing is not None:
        return existing, False
    response = await client.post(
        "/knowledge-base",
        json={
            "name": name,
            "embeddingModel": embedding_model,
            "collectionName": collection,
        },
    )
    response.raise_for_status()
    kb_id = int(unwrap(response.json()))
    return KnowledgeBase(id=kb_id, name=name, collection_name=collection), True


async def list_documents(client: httpx.AsyncClient, kb_id: int) -> list[dict[str, Any]]:
    response = await client.get(f"/knowledge-base/{kb_id}/docs", params={"current": 1, "size": 100})
    response.raise_for_status()
    data = unwrap(response.json())
    records = (data or {}).get("records") or []
    return [record for record in records if isinstance(record, dict)]


async def upload_document(client: httpx.AsyncClient, kb_id: int, path: Path) -> dict[str, Any]:
    response = await client.post(
        f"/knowledge-base/{kb_id}/docs/upload",
        files={"file": (path.name, path.read_bytes(), "text/markdown")},
        data={"sourceType": "file"},
    )
    response.raise_for_status()
    document = unwrap(response.json())
    if not isinstance(document, dict):
        raise SeedError(f"upload of {path.name} returned no document")
    return document


async def trigger_chunk(client: httpx.AsyncClient, doc_id: int) -> None:
    response = await client.post(f"/knowledge-base/docs/{doc_id}/chunk")
    response.raise_for_status()
    unwrap(response.json())


async def wait_until_seeded(
    client: httpx.AsyncClient,
    kb_id: int,
    wait_timeout: float,
    poll_interval: float,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + wait_timeout
    documents = await list_documents(client, kb_id)
    while True:
        _, running, failed = split_documents(documents)
        if failed:
            names = ", ".join(str(item.get("docName")) for item in failed)
            raise SeedError(f"ingestion failed for: {names}")
        if not running:
            return documents
        if time.monotonic() >= deadline:
            names = ", ".join(f"{item.get('docName')}({item.get('status')})" for item in running)
            raise SeedError(f"timed out waiting for ingestion: {names}")
        await asyncio.sleep(poll_interval)
        documents = await list_documents(client, kb_id)


async def run(args: argparse.Namespace) -> dict[str, Any]:
    corpus_files = sorted(path for path in args.corpus.iterdir() if path.is_file())
    if not corpus_files:
        raise SystemExit(f"no corpus files found in {args.corpus}")
    headers: dict[str, str] = {}
    token = os.getenv(args.token_env, "").strip()
    if token:
        headers["Authorization"] = token
    base_url = args.base_url.rstrip("/")
    async with httpx.AsyncClient(
        base_url=base_url, headers=headers, timeout=args.timeout
    ) as client:
        kb, created = await ensure_base(client, args.collection, args.kb_name, args.embedding_model)
        documents = await list_documents(client, kb.id)
        uploads = select_uploads(corpus_files, {str(item.get("docName")) for item in documents})
        uploaded = [await upload_document(client, kb.id, path) for path in uploads]
        known = {**{int(item["id"]): item for item in documents}}
        for item in uploaded:
            known[int(item["id"])] = item
        triggered = 0
        for doc_id in sorted(known):
            if chunk_required(known[doc_id]):
                await trigger_chunk(client, doc_id)
                triggered += 1
        documents = await wait_until_seeded(client, kb.id, args.wait_timeout, args.poll_interval)
    summary = build_summary(base_url, args.collection, kb, documents)
    summary["knowledgeBaseCreated"] = created
    summary["uploaded"] = [path.name for path in uploads]
    summary["chunkTriggered"] = triggered
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS, help="corpus directory")
    parser.add_argument("--base-url", default="http://127.0.0.1:9090/api/ragent")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--kb-name", default="M5 质量基线")
    parser.add_argument("--token-env", default="RAGENT_EVAL_TOKEN")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--wait-timeout", type=float, default=600)
    parser.add_argument("--poll-interval", type=float, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.timeout <= 0 or args.wait_timeout <= 0 or args.poll_interval <= 0:
        raise SystemExit("timeout, wait-timeout and poll-interval must be positive")
    if not args.corpus.is_dir():
        raise SystemExit(f"corpus directory not found: {args.corpus}")
    return args


def main() -> None:
    args = parse_args()
    try:
        payload = asyncio.run(run(args))
    except SeedError as exc:
        raise SystemExit(str(exc)) from exc
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    sys.stdout.write(rendered + "\n")


if __name__ == "__main__":
    main()
