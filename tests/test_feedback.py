"""消息反馈入口参数边界测试。"""

from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.framework.exceptions import ClientException
from app.rag.feedback import MessageFeedbackService


async def test_feedback_rejects_invalid_vote_before_database_access() -> None:
    service = MessageFeedbackService(cast(AsyncEngine, None))

    with pytest.raises(ClientException, match="反馈值必须为 1 或 -1"):
        await service.submit("not-used", user_id=1, vote=0)
