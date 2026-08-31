"""查询词映射管理接口模型。"""

from pydantic import BaseModel, ConfigDict, Field


class MappingApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class QueryTermMappingWrite(MappingApiModel):
    source_term: str = Field(alias="sourceTerm")
    target_term: str = Field(alias="targetTerm")
    match_type: int = Field(default=1, alias="matchType")
    priority: int | None = 100
    enabled: bool = True
    domain: str | None = None
    remark: str | None = None


class QueryTermMappingVO(QueryTermMappingWrite):
    id: int


class MappingPage(MappingApiModel):
    records: list[QueryTermMappingVO]
    total: int
    current: int
    size: int
