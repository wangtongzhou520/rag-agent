"""Agent Profile CRUD、槽位校验、默认配置与缓存失效。"""

from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.admin.agents.schemas import AgentProfileWrite
from app.framework.exceptions import ClientException
from app.rag.prompt.cache import AgentPromptCache
from app.rag.prompt.grounding import KB_GROUNDING_GUARD
from app.rag.prompt.models import AgentProfile, AgentPrompt
from app.rag.prompt.slots import (
    GROUP_NAMES,
    AgentPromptSlot,
    effective_slot_total,
)
from app.system.audit.context import AuditContext

BUILTIN_AGENT_NAME = "默认助手"
BUILTIN_PROMPTS: dict[AgentPromptSlot, str] = {
    AgentPromptSlot.SYSTEM_CHAT: (
        "保持友好、简洁，直接回答用户；不要编造知识库来源或引用。"
    ),
    AgentPromptSlot.MCP_ANSWER: (
        "依据 <tool-context> 中的实时工具结果回答用户。"
        "不得把工具结果标成知识库引用。"
    ),
    AgentPromptSlot.MIXED_ANSWER: (
        "综合知识库资料和实时工具结果回答用户，明确区分资料来源；"
        "不要补充上下文中不存在的事实。"
    ),
    AgentPromptSlot.AGENT_MAIN: (
        "以严谨、直接的方式处理任务：先判断用户目标，再按需使用工具，"
        "最后给出可以核验的结论。"
    ),
    AgentPromptSlot.KB_ANSWER: (
        "仅依据 <knowledge-context> 中的资料回答；"
        "资料不足时明确说明。引用事实时在句末使用 [N](#cite-N)，N 必须来自 ref。"
        f"{KB_GROUNDING_GUARD}"
    ),
    AgentPromptSlot.CONVERSATION_SUMMARY: (
        "将会话压缩为不超过 {summary_max_chars} 个字符的事实摘要，保留用户目标、"
        "关键约束与未完成事项，不添加新信息。"
    ),
    AgentPromptSlot.RECOMMENDED_QUESTIONS: (
        "根据原问题、回答和依据生成简洁、具体且不重复的后续问题。"
        "只输出 JSON 字符串数组，最多 {count} 条，不要解释。\n\n"
        "原问题：\n{question}\n\n回答：\n{answer}\n\n依据：\n{chunks}"
    ),
}


class AgentAdminService:
    def __init__(
        self,
        engine: AsyncEngine,
        cache: AgentPromptCache,
        mode: str,
    ) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._cache = cache
        self._mode = mode.strip().upper()

    async def ensure_builtin(self) -> None:
        """幂等补齐内置 Agent 和默认槽位，不覆盖部署方已有默认内容。"""
        changed = False
        async with self._sessions.begin() as session:
            builtin = await session.scalar(
                select(AgentProfile).where(
                    AgentProfile.builtin == 1, AgentProfile.deleted == 0
                )
            )
            if builtin is None:
                has_active = await session.scalar(
                    select(AgentProfile.id).where(
                        AgentProfile.active == 1, AgentProfile.deleted == 0
                    )
                )
                builtin = AgentProfile(
                    name=BUILTIN_AGENT_NAME,
                    description="系统内置回落配置",
                    avatar="compass",
                    builtin=1,
                    active=0 if has_active is not None else 1,
                )
                session.add(builtin)
                await session.flush()
                changed = True
            existing = set(
                (
                    await session.scalars(
                        select(AgentPrompt.slot_key).where(
                            AgentPrompt.agent_id == builtin.id,
                            AgentPrompt.deleted == 0,
                        )
                    )
                ).all()
            )
            for slot, content in BUILTIN_PROMPTS.items():
                if slot.value not in existing:
                    session.add(
                        AgentPrompt(
                            agent_id=builtin.id,
                            slot_key=slot.value,
                            content=content,
                        )
                    )
                    changed = True
        if changed:
            await self._cache.clear()

    async def list_profiles(self) -> dict:
        async with self._sessions() as session:
            profiles = (
                await session.scalars(
                    select(AgentProfile)
                    .where(AgentProfile.deleted == 0)
                    .order_by(
                        AgentProfile.builtin.desc(),
                        AgentProfile.create_time,
                        AgentProfile.id,
                    )
                )
            ).all()
            profile_ids = [row.id for row in profiles]
            configured = await self._configured_slots(session, profile_ids)
        return {
            "mode": self._mode,
            "effectiveSlotTotal": effective_slot_total(self._mode),
            "agents": [self._snapshot(row, configured.get(row.id, set())) for row in profiles],
        }

    async def create(self, body: AgentProfileWrite, user_id: int) -> str:
        name, description, avatar = self._normalize(body)
        async with self._sessions.begin() as session:
            await self._ensure_name(session, name)
            row = AgentProfile(
                name=name,
                description=description,
                avatar=avatar,
                builtin=0,
                active=0,
                create_by=user_id,
                update_by=user_id,
            )
            session.add(row)
            await session.flush()
            AuditContext.put(row.id, None, self._snapshot(row, set()))
        await self._cache.clear()
        return str(row.id)

    async def update(self, agent_id: int, body: AgentProfileWrite, user_id: int) -> None:
        name, description, avatar = self._normalize(body)
        async with self._sessions.begin() as session:
            row = await self._require_profile(session, agent_id)
            self._ensure_mutable(row)
            slots = (await self._configured_slots(session, [agent_id])).get(agent_id, set())
            before = self._snapshot(row, slots)
            await self._ensure_name(session, name, exclude_id=agent_id)
            changed = (row.name, row.description, row.avatar) != (
                name,
                description,
                avatar,
            )
            if not changed:
                AuditContext.skip()
                return
            row.name = name
            row.description = description
            row.avatar = avatar
            row.update_by = user_id
            await session.flush()
            AuditContext.put(agent_id, before, self._snapshot(row, slots))
        await self._cache.clear()

    async def delete(self, agent_id: int) -> None:
        async with self._sessions.begin() as session:
            row = await self._require_profile(session, agent_id)
            self._ensure_mutable(row)
            if row.active == 1:
                raise ClientException("该智能体正在激活中，请先激活其他智能体再删除")
            slots = (await self._configured_slots(session, [agent_id])).get(agent_id, set())
            before = self._snapshot(row, slots)
            row.deleted = 1
            prompts = (
                await session.scalars(
                    select(AgentPrompt).where(
                        AgentPrompt.agent_id == agent_id, AgentPrompt.deleted == 0
                    )
                )
            ).all()
            for prompt in prompts:
                prompt.deleted = 1
            AuditContext.put(agent_id, before, None)
        await self._cache.clear()

    async def activate(self, agent_id: int, user_id: int) -> None:
        async with self._sessions.begin() as session:
            target = await self._require_profile(session, agent_id)
            if target.active == 1:
                AuditContext.skip()
                return
            before = {"id": target.id, "name": target.name, "active": False}
            await session.execute(
                update(AgentProfile)
                .where(AgentProfile.active == 1, AgentProfile.deleted == 0)
                .values(active=0)
            )
            target.active = 1
            target.update_by = user_id
            await session.flush()
            AuditContext.put(
                target.id,
                before,
                {"id": target.id, "name": target.name, "active": True},
            )
        await self._cache.clear()

    async def prompts(self, agent_id: int) -> dict:
        async with self._sessions() as session:
            row = await self._require_profile(session, agent_id)
            builtin = await session.scalar(
                select(AgentProfile).where(
                    AgentProfile.builtin == 1, AgentProfile.deleted == 0
                )
            )
            values = {
                prompt.slot_key: prompt.content or ""
                for prompt in (
                    await session.scalars(
                        select(AgentPrompt).where(
                            AgentPrompt.agent_id == agent_id,
                            AgentPrompt.deleted == 0,
                        )
                    )
                ).all()
                if prompt.slot_key in {slot.value for slot in AgentPromptSlot}
            }
        return {
            "agentId": row.id,
            "agentName": row.name,
            "builtin": bool(row.builtin),
            "defaultAgentName": builtin.name if builtin is not None else "",
            "mode": self._mode,
            "slots": [
                {
                    "slotKey": slot.value,
                    "displayName": slot.definition.display_name,
                    "group": slot.definition.group.value,
                    "groupName": GROUP_NAMES[slot.definition.group],
                    "effective": slot.definition.effective(self._mode),
                    "inactiveReason": slot.definition.inactive_reason(self._mode),
                    "requiredPlaceholders": list(slot.definition.required_placeholders),
                    "content": values.get(slot.value, ""),
                }
                for slot in AgentPromptSlot
            ],
        }

    async def save_prompt(
        self,
        agent_id: int,
        slot_key: str,
        content: str | None,
        user_id: int,
    ) -> None:
        slot = AgentPromptSlot.require(slot_key)
        normalized = content.strip() if content and content.strip() else None
        self._validate_placeholders(slot, normalized)
        async with self._sessions.begin() as session:
            profile = await self._require_profile(session, agent_id)
            self._ensure_mutable(profile)
            prompt = await session.scalar(
                select(AgentPrompt).where(
                    AgentPrompt.agent_id == agent_id,
                    AgentPrompt.slot_key == slot.value,
                    AgentPrompt.deleted == 0,
                )
            )
            before = {"slotKey": slot.value, "content": prompt.content if prompt else None}
            if prompt is None:
                if normalized is None:
                    AuditContext.skip()
                    return
                prompt = AgentPrompt(
                    agent_id=agent_id,
                    slot_key=slot.value,
                    content=normalized,
                    create_by=user_id,
                    update_by=user_id,
                )
                session.add(prompt)
            else:
                if prompt.content == normalized:
                    AuditContext.skip()
                    return
                prompt.content = normalized
                prompt.update_by = user_id
            profile.update_by = user_id
            AuditContext.put(
                agent_id,
                before,
                {"slotKey": slot.value, "content": normalized},
            )
        await self._cache.clear()

    async def default_prompt(self, slot_key: str) -> str:
        slot = AgentPromptSlot.require(slot_key)
        async with self._sessions() as session:
            builtin_id = await session.scalar(
                select(AgentProfile.id).where(
                    AgentProfile.builtin == 1, AgentProfile.deleted == 0
                )
            )
            if builtin_id is None:
                return ""
            value = await session.scalar(
                select(AgentPrompt.content).where(
                    AgentPrompt.agent_id == builtin_id,
                    AgentPrompt.slot_key == slot.value,
                    AgentPrompt.deleted == 0,
                )
            )
        return value or ""

    @staticmethod
    async def _require_profile(session, agent_id: int) -> AgentProfile:
        row = await session.scalar(
            select(AgentProfile).where(
                AgentProfile.id == agent_id, AgentProfile.deleted == 0
            )
        )
        if row is None:
            raise ClientException("智能体不存在")
        return row

    @staticmethod
    async def _configured_slots(session, agent_ids: list[int]) -> dict[int, set[str]]:
        if not agent_ids:
            return {}
        known = {slot.value for slot in AgentPromptSlot}
        rows = (
            await session.execute(
                select(AgentPrompt.agent_id, AgentPrompt.slot_key).where(
                    AgentPrompt.agent_id.in_(agent_ids),
                    AgentPrompt.deleted == 0,
                    AgentPrompt.content.is_not(None),
                    func.length(func.trim(AgentPrompt.content)) > 0,
                )
            )
        ).all()
        result: dict[int, set[str]] = {}
        for agent_id, slot_key in rows:
            if slot_key in known:
                result.setdefault(agent_id, set()).add(slot_key)
        return result

    @staticmethod
    async def _ensure_name(session, name: str, exclude_id: int | None = None) -> None:
        filters = [func.lower(AgentProfile.name) == name.lower()]
        if exclude_id is not None:
            filters.append(AgentProfile.id != exclude_id)
        if await session.scalar(select(AgentProfile.id).where(*filters).limit(1)) is not None:
            raise ClientException("智能体名称已存在")

    def _snapshot(self, row: AgentProfile, configured: set[str]) -> dict:
        effective = sum(
            AgentPromptSlot(slot).definition.effective(self._mode) for slot in configured
        )
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "avatar": row.avatar,
            "builtin": bool(row.builtin),
            "active": bool(row.active),
            "effectiveSlots": effective,
            "inactiveSlots": len(configured) - effective,
            "createTime": _epoch_millis(row.create_time),
            "updateTime": _epoch_millis(row.update_time),
        }

    @staticmethod
    def _normalize(body: AgentProfileWrite) -> tuple[str, str | None, str | None]:
        name = body.name.strip()
        if not name:
            raise ClientException("智能体名称不能为空")
        description = body.description.strip() if body.description else None
        avatar = body.avatar.strip() if body.avatar else None
        if avatar and len(avatar) > 32:
            raise ClientException("头像标识过长")
        return name, description or None, avatar or None

    @staticmethod
    def _ensure_mutable(row: AgentProfile) -> None:
        if row.builtin == 1:
            raise ClientException("内置智能体不可编辑或删除，如需调整请复制一份新建")

    @staticmethod
    def _validate_placeholders(slot: AgentPromptSlot, content: str | None) -> None:
        if content is None:
            return
        missing = sorted(
            placeholder
            for placeholder in slot.definition.required_placeholders
            if "{" + placeholder + "}" not in content
        )
        if missing:
            rendered = "、".join("{" + item + "}" for item in missing)
            raise ClientException(
                f"「{slot.definition.display_name}」缺少必需占位符：{rendered}"
            )


def _epoch_millis(value: datetime) -> int:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return int(aware.timestamp() * 1000)
