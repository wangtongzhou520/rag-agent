"""按需生成推荐追问：FAST 档调用、严格 JSON 解析与消息级缓存。"""

import json
import re
import time
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.framework.chat_types import ChatMessage, ChatRequest, ChatRole
from app.framework.exceptions import ClientException
from app.framework.logging import get_logger
from app.framework.result import ErrorCode
from app.framework.sse import RecommendedQuestionsPayload, RecommendedQuestionStatus
from app.model_runtime.chat.service import LLMService
from app.model_runtime.routing import Tier
from app.rag.models import Message
from app.rag.source.citation import strip_citations
from app.rag.trace.record import RagTraceRecordService

logger = get_logger(__name__)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class RecommendedQuestionGenerator:
    def __init__(self, llm: LLMService, count: int = 3) -> None:
        self._llm = llm
        self._count = max(1, count)

    async def generate(
        self,
        question: str,
        answer: str,
        grounding_chunks: list[dict] | None,
    ) -> RecommendedQuestionsPayload:
        context = self._grounding_text(grounding_chunks)
        request = ChatRequest(
            messages=[
                ChatMessage(
                    role=ChatRole.SYSTEM,
                    content=(
                        "你负责生成简洁、具体且不重复的后续问题。"
                        f"只输出 JSON 字符串数组，最多 {self._count} 条，不要解释。"
                    ),
                ),
                ChatMessage(
                    role=ChatRole.USER,
                    content=(
                        f"原问题：\n{question[:1000]}\n\n"
                        f"回答：\n{strip_citations(answer)[:6000]}\n\n"
                        f"依据：\n{context}"
                    ),
                ),
            ],
            thinking=False,
            temperature=0.7,
            top_p=0.8,
            max_tokens=256,
        )
        raw = await self._llm.chat(request, tier=Tier.FAST)
        return self.parse(raw, self._count)

    @staticmethod
    def parse(raw: str, count: int = 3) -> RecommendedQuestionsPayload:
        text = _FENCE.sub("", raw.strip()).strip()
        try:
            values = json.loads(text)
        except (TypeError, ValueError):
            return RecommendedQuestionsPayload(
                status=RecommendedQuestionStatus.FAILED, questions=[]
            )
        if not isinstance(values, list):
            return RecommendedQuestionsPayload(
                status=RecommendedQuestionStatus.FAILED, questions=[]
            )
        questions: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not isinstance(value, str):
                continue
            question = value.strip()[:200]
            if not question or question in seen:
                continue
            seen.add(question)
            questions.append(question)
            if len(questions) >= count:
                break
        return RecommendedQuestionsPayload(
            status=(
                RecommendedQuestionStatus.SUCCESS
                if questions
                else RecommendedQuestionStatus.EMPTY
            ),
            questions=questions,
        )

    @staticmethod
    def _grounding_text(chunks: list[dict] | None) -> str:
        if not chunks:
            return "（无检索片段，仅依据问答生成）"
        lines = []
        for index, chunk in enumerate(chunks, start=1):
            name = str(chunk.get("docName") or "未命名文档")
            text = str(chunk.get("text") or "")
            lines.append(f"{index}. 【{name}】{text}")
        return "\n".join(lines)[:6000]


class RecommendedQuestionService:
    def __init__(
        self,
        engine: AsyncEngine,
        generator: RecommendedQuestionGenerator,
        trace: RagTraceRecordService | None = None,
    ) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._generator = generator
        self._trace = trace

    async def generate(self, message_id: str, user_id: int) -> RecommendedQuestionsPayload:
        parsed_id = self._parse_id(message_id)
        async with self._sessions() as session:
            message = await session.scalar(
                select(Message).where(
                    Message.id == parsed_id,
                    Message.user_id == user_id,
                    Message.role == "assistant",
                    Message.deleted == 0,
                )
            )
            if message is None:
                raise ClientException("消息不存在", code=ErrorCode.NOT_FOUND)
            if message.message_status != "NORMAL":
                return RecommendedQuestionsPayload(
                    status=RecommendedQuestionStatus.EMPTY, questions=[]
                )
            if message.recommended_questions is not None:
                questions = [str(item) for item in message.recommended_questions]
                return RecommendedQuestionsPayload(
                    status=(
                        RecommendedQuestionStatus.SUCCESS
                        if questions
                        else RecommendedQuestionStatus.EMPTY
                    ),
                    questions=questions,
                )
            question = ""
            if message.reply_to_message_id is not None:
                question = (
                    await session.scalar(
                        select(Message.content).where(
                            Message.id == message.reply_to_message_id,
                            Message.user_id == user_id,
                            Message.role == "user",
                            Message.deleted == 0,
                        )
                    )
                    or ""
                )
            answer = message.content
            grounding_chunks = message.retrieved_chunks
            conversation_id = message.conversation_id
        started = time.monotonic()
        try:
            result = await self._generator.generate(question, answer, grounding_chunks)
        except Exception:
            logger.exception("推荐追问生成失败", message_id=message_id)
            result = RecommendedQuestionsPayload(
                status=RecommendedQuestionStatus.FAILED, questions=[]
            )
        if self._trace is not None:
            await self._trace.record_recommendation(
                conversation_id,
                user_id,
                int((time.monotonic() - started) * 1000),
                str(result.status),
                len(result.questions),
            )
        if result.status is not RecommendedQuestionStatus.FAILED:
            async with self._sessions.begin() as session:
                await session.execute(
                    update(Message)
                    .where(
                        Message.id == parsed_id,
                        Message.user_id == user_id,
                        Message.deleted == 0,
                    )
                    .values(recommended_questions=result.questions)
                )
        return result

    @staticmethod
    def _parse_id(value: str) -> uuid.UUID:
        try:
            return uuid.UUID(value)
        except ValueError as exc:
            raise ClientException("消息 ID 无效") from exc
