"""用户 CRUD、改密与会话失效。"""

from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.framework.exceptions import ClientException
from app.system.audit.context import AuditContext
from app.system.auth.password import hash_password, verify_password
from app.system.auth.service import AuthService
from app.system.user.enums import UserRole
from app.system.user.models import User
from app.system.user.schemas import UserCreateRequest, UserUpdateRequest


class UserService:
    def __init__(self, engine: AsyncEngine, auth: AuthService) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._auth = auth

    async def page(self, current: int, size: int, keyword: str | None = None) -> dict:
        filters = [User.deleted == 0]
        if keyword and keyword.strip():
            pattern = f"%{keyword.strip()}%"
            filters.append(or_(User.username.ilike(pattern), User.role.ilike(pattern)))
        async with self._sessions() as session:
            total = await session.scalar(select(func.count()).select_from(User).where(*filters))
            rows = (
                await session.scalars(
                    select(User)
                    .where(*filters)
                    .order_by(User.update_time.desc(), User.id.desc())
                    .offset((current - 1) * size)
                    .limit(size)
                )
            ).all()
        count = int(total or 0)
        return {
            "records": [self._snapshot(row) for row in rows],
            "total": count,
            "current": current,
            "size": size,
            "pages": max(1, (count + size - 1) // size),
        }

    async def create(self, body: UserCreateRequest) -> int:
        username = body.username.strip()
        password = body.password.strip()
        if not username or not password:
            raise ClientException("用户名或密码不能为空")
        self._ensure_username_allowed(username)
        try:
            role = UserRole.normalize(body.role)
        except ValueError as exc:
            raise ClientException(str(exc)) from exc
        async with self._sessions.begin() as session:
            await self._ensure_unique(session, username)
            row = User(
                username=username,
                password_hash=hash_password(password),
                role=role.value.upper(),
                avatar=body.avatar.strip() if body.avatar and body.avatar.strip() else None,
            )
            session.add(row)
            await session.flush()
            user_id = int(row.id)
            AuditContext.put(user_id, None, self._snapshot(row))
        return user_id

    async def update(self, user_id: int, body: UserUpdateRequest) -> None:
        async with self._sessions.begin() as session:
            row = await self._get(session, user_id)
            self._ensure_mutable(row)
            before = self._snapshot(row)
            changed = False
            if body.username is not None:
                username = body.username.strip()
                if not username:
                    raise ClientException("用户名不能为空")
                self._ensure_username_allowed(username)
                await self._ensure_unique(session, username, exclude_id=user_id)
                if row.username != username:
                    row.username = username
                    changed = True
            if body.password is not None and body.password.strip():
                row.password_hash = hash_password(body.password.strip())
                changed = True
            if body.role is not None:
                try:
                    role = UserRole.normalize(body.role)
                except ValueError as exc:
                    raise ClientException(str(exc)) from exc
                normalized_role = role.value.upper()
                if row.role != normalized_role:
                    row.role = normalized_role
                    changed = True
            if body.avatar is not None:
                avatar = body.avatar.strip() or None
                if row.avatar != avatar:
                    row.avatar = avatar
                    changed = True
            if not changed:
                AuditContext.skip()
                return
            await session.flush()
            await session.refresh(row)
            AuditContext.put(user_id, before, self._snapshot(row, password_changed=bool(body.password and body.password.strip())))
            await self._auth.invalidate_user_sessions(user_id)

    async def delete(self, user_id: int) -> None:
        async with self._sessions.begin() as session:
            row = await self._get(session, user_id)
            self._ensure_mutable(row)
            before = self._snapshot(row)
            row.deleted = 1
            AuditContext.put(user_id, before, None)
            await self._auth.invalidate_user_sessions(user_id)

    async def change_password(
        self, user_id: int, current_password: str, new_password: str
    ) -> None:
        new_password = new_password.strip()
        if not new_password:
            raise ClientException("新密码不能为空")
        async with self._sessions.begin() as session:
            row = await self._get(session, user_id)
            if not verify_password(current_password, row.password_hash):
                AuditContext.put(user_id, self._snapshot(row), None)
                raise ClientException("当前密码不正确")
            before = self._snapshot(row)
            row.password_hash = hash_password(new_password)
            AuditContext.put(
                user_id,
                before,
                self._snapshot(row, password_changed=True),
            )
            await self._auth.invalidate_user_sessions(user_id)

    @staticmethod
    async def _get(session, user_id: int) -> User:
        row = await session.scalar(
            select(User).where(User.id == user_id, User.deleted == 0)
        )
        if row is None:
            raise ClientException("用户不存在")
        return row

    @staticmethod
    async def _ensure_unique(session, username: str, exclude_id: int | None = None) -> None:
        filters = [func.lower(User.username) == username.lower()]
        if exclude_id is not None:
            filters.append(User.id != exclude_id)
        if await session.scalar(select(User.id).where(*filters).limit(1)) is not None:
            raise ClientException("用户名已存在")

    @staticmethod
    def _ensure_username_allowed(username: str) -> None:
        if username.lower() == "admin":
            raise ClientException("默认管理员用户名不可用")

    @staticmethod
    def _ensure_mutable(row: User) -> None:
        if row.username.lower() == "admin":
            raise ClientException("默认管理员不允许修改或删除")

    @staticmethod
    def _snapshot(row: User, *, password_changed: bool = False) -> dict:
        value = {
            "id": row.id,
            "username": row.username,
            "role": row.role.lower(),
            "avatar": row.avatar,
            "createTime": _epoch_millis(row.create_time),
            "updateTime": _epoch_millis(row.update_time),
        }
        if password_changed:
            value["passwordChanged"] = True
        return value


def _epoch_millis(value: datetime) -> int:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return int(aware.timestamp() * 1000)
