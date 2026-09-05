"""Agent Profile 槽位架构、缓存回落与管理接口守卫测试。"""

from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.admin.agents.router import router
from app.admin.agents.service import AgentAdminService
from app.framework.exceptions import ClientException
from app.rag.prompt.cache import AgentPromptCache
from app.rag.prompt.resolver import AgentPromptResolver
from app.rag.prompt.slots import AgentPromptSlot, effective_slot_total
from app.system.auth.deps import require_admin


class MemoryRedis:
    def __init__(self) -> None:
        self.value: str | None = None
        self.deleted: list[str] = []
        self.expiry: int | None = None

    async def get(self, key: str) -> str | None:
        return self.value

    async def set(self, key: str, value: str, ex: int) -> None:
        self.value = value
        self.expiry = ex

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.value = None


class CachedPrompts:
    async def get(self) -> dict[str, str]:
        return {
            "SYSTEM_CHAT": "定制回答",
            "RECOMMENDED_QUESTIONS": "{question}|{answer}|{chunks}|{count}",
        }

    async def set(self, value: dict[str, str]) -> None:
        raise AssertionError("缓存命中时不应回填")


def test_slot_effectiveness_matches_workflow_and_agent_architectures() -> None:
    assert effective_slot_total("workflow") == 6
    assert effective_slot_total("agent") == 4
    assert AgentPromptSlot.AGENT_MAIN.definition.effective("workflow") is False
    assert AgentPromptSlot.MCP_ANSWER.definition.effective("agent") is False
    assert AgentPromptSlot.KB_ANSWER.definition.effective("agent") is True


def test_required_placeholders_are_rejected_with_stable_message() -> None:
    with pytest.raises(ClientException) as error:
        AgentAdminService._validate_placeholders(
            AgentPromptSlot.RECOMMENDED_QUESTIONS,
            "问题：{question}，回答：{answer}",
        )

    assert error.value.message == "「推荐问题」缺少必需占位符：{chunks}、{count}"


async def test_prompt_cache_uses_one_hour_ttl_and_clear_key() -> None:
    redis = MemoryRedis()
    cache = AgentPromptCache(cast(object, redis), "ragent:")

    await cache.set({"SYSTEM_CHAT": "你好"})
    assert redis.expiry == 3600
    assert await cache.get() == {"SYSTEM_CHAT": "你好"}

    await cache.clear()
    assert redis.deleted == ["ragent:agent:resolved-prompts"]


async def test_resolver_uses_cached_prompt_and_renders_placeholders() -> None:
    resolver = AgentPromptResolver(
        cast(AsyncEngine, object()), cast(AgentPromptCache, CachedPrompts())
    )

    assert await resolver.resolve(AgentPromptSlot.SYSTEM_CHAT) == "定制回答"
    assert (
        await resolver.render(
            AgentPromptSlot.RECOMMENDED_QUESTIONS,
            {"question": "Q", "answer": "A", "chunks": "C", "count": 3},
        )
        == "Q|A|C|3"
    )


def test_all_agent_management_routes_require_admin() -> None:
    assert len(router.routes) == 8
    for route in router.routes:
        calls = {dependency.call for dependency in route.dependant.dependencies}
        assert require_admin in calls
