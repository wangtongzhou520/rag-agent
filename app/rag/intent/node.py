"""意图树节点与分类结果领域模型。"""

from dataclasses import dataclass, field
from enum import IntEnum


class IntentLevel(IntEnum):
    DOMAIN = 0
    CATEGORY = 1
    TOPIC = 2


class IntentKind(IntEnum):
    KB = 0
    SYSTEM = 1
    MCP = 2


@dataclass(slots=True)
class IntentNode:
    id: int
    intent_code: str
    name: str
    level: int
    kind: int = 0
    description: str = ""
    examples: tuple[str, ...] = ()
    parent_code: str | None = None
    collection_name: str | None = None
    collection_names: tuple[str, ...] = ()
    mcp_tool_id: str | None = None
    top_k: int | None = None
    children: list["IntentNode"] = field(default_factory=list)
    full_path: str = ""

    def is_leaf(self) -> bool:
        return not self.children

    def effective_collection_names(self) -> list[str]:
        values = list(self.collection_names)
        if self.collection_name:
            values.append(self.collection_name)
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


@dataclass(frozen=True, slots=True)
class NodeScore:
    node: IntentNode
    score: float
    reason: str = ""


@dataclass(frozen=True, slots=True)
class SubQuestionIntent:
    sub_question: str
    node_scores: tuple[NodeScore, ...]
