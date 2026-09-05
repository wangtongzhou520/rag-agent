"""Agent Prompt 两级回落解析与安全占位符渲染。"""

from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.rag.prompt.cache import AgentPromptCache
from app.rag.prompt.models import AgentProfile, AgentPrompt
from app.rag.prompt.slots import AgentPromptSlot


class AgentPromptResolver:
    def __init__(self, engine: AsyncEngine, cache: AgentPromptCache) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._cache = cache

    async def resolve_all(self) -> dict[str, str]:
        cached = await self._cache.get()
        if cached is not None:
            return cached
        async with self._sessions() as session:
            profiles = (
                await session.scalars(
                    select(AgentProfile).where(
                        AgentProfile.deleted == 0,
                        (AgentProfile.builtin == 1) | (AgentProfile.active == 1),
                    )
                )
            ).all()
            builtin = next((item for item in profiles if item.builtin == 1), None)
            active = next((item for item in profiles if item.active == 1), None)
            ids = [item.id for item in (builtin, active) if item is not None]
            prompts = (
                await session.scalars(
                    select(AgentPrompt).where(
                        AgentPrompt.agent_id.in_(ids), AgentPrompt.deleted == 0
                    )
                )
            ).all() if ids else []
        by_agent: dict[int, dict[str, str]] = {}
        for prompt in prompts:
            if prompt.content and prompt.content.strip():
                by_agent.setdefault(prompt.agent_id, {})[prompt.slot_key] = prompt.content.strip()
        resolved: dict[str, str] = {}
        if builtin is not None:
            resolved.update(by_agent.get(builtin.id, {}))
        if active is not None:
            resolved.update(by_agent.get(active.id, {}))
        await self._cache.set(resolved)
        return resolved

    async def resolve(self, slot: AgentPromptSlot | str) -> str:
        key = AgentPromptSlot.require(str(slot)).value
        return (await self.resolve_all()).get(key, "")

    async def render(
        self, slot: AgentPromptSlot | str, values: Mapping[str, object]
    ) -> str:
        content = await self.resolve(slot)
        for key, value in values.items():
            content = content.replace("{" + key + "}", str(value))
        return _cleanup(content)


def _cleanup(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.strip().splitlines()).strip()
