"""无会话副作用的评测答案生成器。"""

from collections.abc import Sequence

from app.framework.chat_types import ChatMessage, ChatRequest, ChatRole
from app.model_runtime.chat.service import LLMService
from app.rag.prompt.grounding import KB_GROUNDING_GUARD
from app.rag.prompt.resolver import AgentPromptResolver
from app.rag.prompt.slots import AgentPromptSlot
from app.rag.retrieval.models import RetrievedChunk
from app.rag.source.assembler import SourcesAssembler
from app.rag.source.citation import CitationContextEnricher, sanitize_attribute

DEFAULT_KB_PROMPT = (
    "你是严谨的知识库问答助手。仅依据 <knowledge-context> 中的资料回答；"
    "资料不足时明确说明。引用事实时在句末使用 [N](#cite-N)，N 必须来自 ref。"
)


class EvalAnswerGenerator:
    """复用线上 KB Prompt 与同步 Chat 路由，不创建会话或持久化消息。"""

    def __init__(self, llm: LLMService, prompt_resolver: AgentPromptResolver) -> None:
        self._llm = llm
        self._prompt_resolver = prompt_resolver

    async def generate(
        self, question: str, chunks: Sequence[RetrievedChunk]
    ) -> str:
        typed_chunks = list(chunks)
        if not typed_chunks:
            return "现有资料未提供与该问题相关的信息，无法确定。"
        assembled = SourcesAssembler().assemble(typed_chunks)
        raw_context = "\n\n".join(
            (
                '<content data-ragent-doc-id="'
                f'{sanitize_attribute(chunk.doc_id)}">'
                f"\n{chunk.text}\n</content>"
            )
            for chunk in typed_chunks
        )
        context = CitationContextEnricher().enrich(raw_context, assembled.indexes)
        prompt = await self._prompt_resolver.resolve(AgentPromptSlot.KB_ANSWER)
        system = (
            f"{prompt or DEFAULT_KB_PROMPT}\n{KB_GROUNDING_GUARD}\n"
            f"<knowledge-context>\n{context}\n</knowledge-context>"
        )
        return (
            await self._llm.chat(
                ChatRequest(
                    messages=[
                        ChatMessage(role=ChatRole.SYSTEM, content=system),
                        ChatMessage(role=ChatRole.USER, content=question),
                    ],
                    thinking=False,
                )
            )
        ).strip()
