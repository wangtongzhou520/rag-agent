"""意图树 API 模型。"""

from pydantic import BaseModel, ConfigDict, Field


class IntentNodeWrite(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    kb_id: int | None = Field(None, alias="kbId")
    intent_code: str = Field(alias="intentCode")
    name: str
    level: int = 0
    parent_code: str | None = Field(None, alias="parentCode")
    description: str | None = None
    examples: list[str] = []
    collection_name: str | None = Field(None, alias="collectionName")
    collection_names: list[str] = Field(default_factory=list, alias="collectionNames")
    kind: int = 0
    mcp_tool_id: str | None = Field(None, alias="mcpToolId")
    top_k: int | None = Field(None, alias="topK")
    enabled: bool = True


class IntentNodeVO(IntentNodeWrite):
    id: int
    full_path: str = Field("", alias="fullPath")
    children: list["IntentNodeVO"] = []

