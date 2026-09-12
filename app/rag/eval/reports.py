"""黄金集批次报告的持久化与查询。"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.rag.eval.models import EvalReport
from app.rag.eval.schemas import EvalReportCreate


class EvalReportService:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def create(self, command: EvalReportCreate, created_by: int) -> dict:
        row = EvalReport(
            label=command.label.strip() if command.label else None,
            dataset=command.dataset.strip(),
            collections=list(dict.fromkeys(command.collections)),
            include_answers=command.include_answers,
            thresholds=command.thresholds,
            summary=command.summary,
            cases=command.cases,
            created_by=created_by,
        )
        async with self._sessions() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return self._detail(row)

    async def page(self, current: int, size: int) -> dict:
        filters = [EvalReport.deleted == 0]
        async with self._sessions() as session:
            total = await session.scalar(
                select(func.count()).select_from(EvalReport).where(*filters)
            )
            rows = (
                await session.scalars(
                    select(EvalReport)
                    .where(*filters)
                    .order_by(EvalReport.create_time.desc(), EvalReport.id.desc())
                    .offset((current - 1) * size)
                    .limit(size)
                )
            ).all()
        return {
            "records": [self._summary(row) for row in rows],
            "total": int(total or 0),
            "current": current,
            "size": size,
        }

    async def detail(self, report_id: str) -> dict | None:
        try:
            parsed = uuid.UUID(report_id)
        except ValueError:
            return None
        async with self._sessions() as session:
            row = await session.scalar(
                select(EvalReport).where(
                    EvalReport.report_id == parsed, EvalReport.deleted == 0
                )
            )
        return self._detail(row) if row else None

    @classmethod
    def _summary(cls, row: EvalReport) -> dict:
        return {
            "reportId": str(row.report_id),
            "label": row.label,
            "dataset": row.dataset,
            "collections": row.collections,
            "includeAnswers": row.include_answers,
            "summary": row.summary,
            "createdBy": row.created_by,
            "createTime": cls._epoch_millis(row.create_time),
        }

    @classmethod
    def _detail(cls, row: EvalReport) -> dict:
        return {
            **cls._summary(row),
            "thresholds": row.thresholds,
            "cases": row.cases,
        }

    @staticmethod
    def _epoch_millis(value: datetime) -> int:
        aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return int(aware.timestamp() * 1000)
