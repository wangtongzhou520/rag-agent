"""审计记录独立落库与管理查询。"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.framework.exceptions import ClientException
from app.system.audit.diff import collect_diff
from app.system.audit.models import BizChangeLog


@dataclass(frozen=True)
class AuditRecord:
    biz_type: str
    biz_id: str
    operation_type: str
    action_desc: str
    before: Any
    after: Any
    operator_id: str
    operator_name: str | None
    operator_role: str | None
    success: bool
    error_message: str | None
    class_name: str
    method_name: str
    ip: str | None
    user_agent: str | None


class AuditRecordService:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def record(self, value: AuditRecord) -> None:
        async with self._sessions.begin() as session:
            session.add(
                BizChangeLog(
                    biz_type=_limit(value.biz_type, 64),
                    biz_id=_limit(value.biz_id or "UNKNOWN", 64),
                    operation_type=_limit(value.operation_type, 32),
                    action_desc=_limit(value.action_desc, 512),
                    before_snapshot=value.before,
                    after_snapshot=value.after,
                    change_diff=collect_diff(value.before, value.after),
                    operator_id=_limit(value.operator_id or "SYSTEM", 64),
                    operator_name=_optional_limit(value.operator_name, 128),
                    operator_role=_optional_limit(value.operator_role, 64),
                    success=value.success,
                    error_message=value.error_message,
                    class_name=_limit(value.class_name, 255),
                    method_name=_limit(value.method_name, 255),
                    ip=_optional_limit(value.ip, 64),
                    user_agent=_optional_limit(value.user_agent, 512),
                )
            )


class AuditQueryService:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def page(
        self,
        current: int,
        size: int,
        *,
        biz_type: str | None = None,
        biz_id: str | None = None,
        operation_type: str | None = None,
        operator_id: str | None = None,
        operator_name: str | None = None,
        success: bool | None = None,
        begin_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> dict:
        filters = []
        if biz_type:
            filters.append(BizChangeLog.biz_type == biz_type.strip().upper())
        if biz_id:
            filters.append(BizChangeLog.biz_id.ilike(f"%{biz_id.strip()}%"))
        if operation_type:
            filters.append(BizChangeLog.operation_type == operation_type.strip().upper())
        if operator_id:
            filters.append(BizChangeLog.operator_id == operator_id.strip())
        if operator_name:
            filters.append(BizChangeLog.operator_name.ilike(f"%{operator_name.strip()}%"))
        if success is not None:
            filters.append(BizChangeLog.success == success)
        if begin_time:
            filters.append(BizChangeLog.create_time >= begin_time)
        if end_time:
            filters.append(BizChangeLog.create_time <= end_time)
        async with self._sessions() as session:
            total = await session.scalar(
                select(func.count()).select_from(BizChangeLog).where(*filters)
            )
            rows = (
                await session.scalars(
                    select(BizChangeLog)
                    .where(*filters)
                    .order_by(BizChangeLog.create_time.desc(), BizChangeLog.id.desc())
                    .offset((current - 1) * size)
                    .limit(size)
                )
            ).all()
        count = int(total or 0)
        return {
            "records": [self._to_dict(row) for row in rows],
            "total": count,
            "current": current,
            "size": size,
            "pages": max(1, (count + size - 1) // size),
        }

    async def get(self, log_id: int) -> dict:
        async with self._sessions() as session:
            row = await session.get(BizChangeLog, log_id)
        if row is None:
            raise ClientException("变更审计日志不存在")
        return self._to_dict(row)

    @staticmethod
    def _to_dict(row: BizChangeLog) -> dict:
        return {
            "id": row.id,
            "bizType": row.biz_type,
            "bizId": row.biz_id,
            "operationType": row.operation_type,
            "actionDesc": row.action_desc,
            "beforeSnapshot": row.before_snapshot,
            "afterSnapshot": row.after_snapshot,
            "changeDiff": row.change_diff,
            "operatorId": row.operator_id,
            "operatorName": row.operator_name,
            "operatorRole": row.operator_role,
            "success": row.success,
            "errorMessage": row.error_message,
            "className": row.class_name,
            "methodName": row.method_name,
            "ip": row.ip,
            "userAgent": row.user_agent,
            "createTime": _epoch_millis(row.create_time),
        }


def _limit(value: str, size: int) -> str:
    return str(value)[:size]


def _optional_limit(value: str | None, size: int) -> str | None:
    return _limit(value, size) if value else None


def _epoch_millis(value: datetime) -> int:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return int(aware.timestamp() * 1000)
