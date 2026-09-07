"""知识库异步任务状态语义测试。"""

import uuid
from types import SimpleNamespace

from app.framework.task_queue import ClaimedTask
from app.knowledge.models import KnowledgeDocument, KnowledgeDocumentChunkLog
from app.knowledge.tasks import KnowledgeTaskHandler


class FakeSession:
    def __init__(self) -> None:
        self.document = SimpleNamespace(status="pending")
        self.log = SimpleNamespace(status="pending", error_message=None, end_time=None)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    def begin(self):
        return self

    async def get(self, model, _key):
        if model is KnowledgeDocument:
            return self.document
        if model is KnowledgeDocumentChunkLog:
            return self.log
        return None


async def test_chunk_retry_stays_running_until_terminal_failure() -> None:
    session = FakeSession()
    handler = object.__new__(KnowledgeTaskHandler)
    handler._sessions = session
    task = ClaimedTask(
        id=1,
        event_id=uuid.uuid4(),
        task_type="chunk-document",
        biz_key="doc:5",
        payload={"docId": 5, "logId": 7},
        retry_count=1,
        max_retries=5,
    )

    await handler.mark_retry_or_failed(task, "temporary error", terminal=False)

    assert session.document.status == "running"
    assert session.log.status == "running"
    assert session.log.error_message == "temporary error"
    assert session.log.end_time is None

    await handler.mark_retry_or_failed(task, "terminal error", terminal=True)

    assert session.document.status == "failed"
    assert session.log.status == "failed"
    assert session.log.error_message == "terminal error"
    assert session.log.end_time is not None
