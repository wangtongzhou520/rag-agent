"""Prompt 槽位唯一枚举及架构生效规则。"""

from dataclasses import dataclass
from enum import StrEnum

from app.framework.exceptions import ClientException


class PromptGroup(StrEnum):
    WORKFLOW = "WORKFLOW"
    AGENT = "AGENT"
    COMMON = "COMMON"


@dataclass(frozen=True, slots=True)
class SlotDefinition:
    key: str
    display_name: str
    group: PromptGroup
    required_placeholders: tuple[str, ...] = ()

    def effective(self, mode: str) -> bool:
        normalized = mode.strip().upper()
        return self.group is PromptGroup.COMMON or self.group.value == normalized

    def inactive_reason(self, mode: str) -> str | None:
        if self.effective(mode):
            return None
        if self.group is PromptGroup.AGENT:
            return "WorkFlow 模式不经过 ReAct 架构"
        if self.key == "MCP_ANSWER":
            return "Agent 模式下改用原生工具调用，无独立的数据合成环节"
        if self.key == "SYSTEM_CHAT":
            return "Agent 模式下由主 Agent 直接应答"
        return "Agent 模式下由主 Agent 综合多个工具的结果"


class AgentPromptSlot(StrEnum):
    SYSTEM_CHAT = "SYSTEM_CHAT"
    MCP_ANSWER = "MCP_ANSWER"
    MIXED_ANSWER = "MIXED_ANSWER"
    AGENT_MAIN = "AGENT_MAIN"
    KB_ANSWER = "KB_ANSWER"
    CONVERSATION_SUMMARY = "CONVERSATION_SUMMARY"
    RECOMMENDED_QUESTIONS = "RECOMMENDED_QUESTIONS"

    @classmethod
    def require(cls, value: str) -> "AgentPromptSlot":
        try:
            return cls(value.strip().upper())
        except ValueError as exc:
            raise ClientException(f"未知的提示词：{value}") from exc

    @property
    def definition(self) -> SlotDefinition:
        return SLOT_DEFINITIONS[self]


SLOT_DEFINITIONS = {
    AgentPromptSlot.SYSTEM_CHAT: SlotDefinition(
        AgentPromptSlot.SYSTEM_CHAT.value, "闲聊 / 关于助手", PromptGroup.WORKFLOW
    ),
    AgentPromptSlot.MCP_ANSWER: SlotDefinition(
        AgentPromptSlot.MCP_ANSWER.value, "MCP 问答", PromptGroup.WORKFLOW
    ),
    AgentPromptSlot.MIXED_ANSWER: SlotDefinition(
        AgentPromptSlot.MIXED_ANSWER.value, "混合问答", PromptGroup.WORKFLOW
    ),
    AgentPromptSlot.AGENT_MAIN: SlotDefinition(
        AgentPromptSlot.AGENT_MAIN.value, "Agent 人设", PromptGroup.AGENT
    ),
    AgentPromptSlot.KB_ANSWER: SlotDefinition(
        AgentPromptSlot.KB_ANSWER.value, "知识库问答", PromptGroup.COMMON
    ),
    AgentPromptSlot.CONVERSATION_SUMMARY: SlotDefinition(
        AgentPromptSlot.CONVERSATION_SUMMARY.value,
        "会话压缩",
        PromptGroup.COMMON,
        ("summary_max_chars",),
    ),
    AgentPromptSlot.RECOMMENDED_QUESTIONS: SlotDefinition(
        AgentPromptSlot.RECOMMENDED_QUESTIONS.value,
        "推荐问题",
        PromptGroup.COMMON,
        ("answer", "chunks", "count", "question"),
    ),
}

GROUP_NAMES = {
    PromptGroup.WORKFLOW: "WorkFlow 专属",
    PromptGroup.AGENT: "Agent 专属",
    PromptGroup.COMMON: "通用",
}


def effective_slot_total(mode: str) -> int:
    return sum(slot.definition.effective(mode) for slot in AgentPromptSlot)
