"""Cache mixin for JudgeIntelService."""

import json
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select

from app.database import get_db_context

from ._models import JudgeCacheDB


class CacheMixin:
    """Cache helpers for judge data persistence."""

    async def _get_cache(self, judge_id: int) -> JudgeCacheDB | None:
        """Retrieve the cache row for a judge, or None."""
        async with get_db_context() as db:
            result = await db.execute(
                select(JudgeCacheDB).where(JudgeCacheDB.judge_id == str(judge_id))
            )
            return result.scalars().first()

    def _ensure_serializable(self, data: Any) -> Any:
        """Ensure data is JSON-serializable (convert datetimes to ISO strings)."""
        if isinstance(data, datetime | date):
            return data.isoformat()
        if isinstance(data, dict):
            return {k: self._ensure_serializable(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._ensure_serializable(v) for v in data]
        return data

    async def _set_cache(
        self,
        judge_id: int,
        judge_data: dict,
        opinions_data: dict | None = None,
    ):
        """Insert or update the cache row for a judge."""
        async with get_db_context() as db:
            result = await db.execute(
                select(JudgeCacheDB).where(JudgeCacheDB.judge_id == str(judge_id))
            )
            row = result.scalars().first()
            # cached_at is TIMESTAMP WITHOUT TIME ZONE — store naive UTC so
            # asyncpg doesn't reject a tz-aware datetime on Postgres.
            now = datetime.now(UTC).replace(tzinfo=None)

            safe_judge = self._ensure_serializable(judge_data)
            safe_opinions = (
                self._ensure_serializable(opinions_data) if opinions_data is not None else None
            )

            if row:
                row.judge_data = safe_judge
                if safe_opinions is not None:
                    row.opinions_data = safe_opinions
                row.cached_at = now
            else:
                row = JudgeCacheDB(
                    judge_id=str(judge_id),
                    judge_data=safe_judge,
                    opinions_data=safe_opinions,
                    cached_at=now,
                )
                db.add(row)

    async def _delete_cache(self, judge_id: int):
        """Delete cache row for a judge."""
        async with get_db_context() as db:
            result = await db.execute(
                select(JudgeCacheDB).where(JudgeCacheDB.judge_id == str(judge_id))
            )
            row = result.scalars().first()
            if row:
                await db.delete(row)

    def _parse_judge_data(self, row: JudgeCacheDB) -> dict:
        """Parse a cache row back into judge_data dict."""
        data = row.judge_data
        if isinstance(data, str):
            return json.loads(data)
        return data if data else {}

    def _parse_opinions_data(self, row: JudgeCacheDB) -> dict:
        """Parse a cache row back into opinions_data dict."""
        data = row.opinions_data
        if isinstance(data, str):
            return json.loads(data)
        return data if data else {}
