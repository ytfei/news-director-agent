"""数值事实仓储。

幂等键怎么定（这是本表唯一的难点）：
一条事实的身份 = **来源条目 + 指标名 + 标的 + 时点**。
不含数值本身 —— 因为上游修订数据时（如更正为 85.3%），我们想更新那一行，
而不是再插一行。所以 key 由"谁在什么时候说了哪个指标"决定，数值是可变的载荷。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.base import Metric, NormalizedItem
from app.lib.hash import json_safe, sha256_hex
from app.models.market import MarketFact


def fact_key(
    item_external_id: str, metric: Metric, observed_at: datetime | None = None
) -> str:
    """一条事实的幂等键。

    刻意不含 `value`：上游更正数值时应更新同一行，而不是产生第二条事实。
    """
    parts = [
        item_external_id,
        metric.name,
        metric.ts_code or "",
        metric.period or "",
        (observed_at or metric.observed_at).isoformat() if (observed_at or metric.observed_at) else "",
    ]
    return sha256_hex("|".join(parts))[:32]


def build_rows(
    item: NormalizedItem,
    connector_id: uuid.UUID,
    *,
    raw_document_id: uuid.UUID | None = None,
    news_item_id: uuid.UUID | None = None,
) -> list[dict]:
    """把统一信封里的数值事实转成待插入的行。

    放在仓储层的模块函数里，是为了能在**不连数据库**的情况下单测幂等键与字段映射。
    """
    rows: list[dict] = []
    for metric in item.metrics:
        observed = metric.observed_at or item.published_at
        rows.append(
            {
                "source_connector_id": connector_id,
                "raw_document_id": raw_document_id,
                "news_item_id": news_item_id,
                "external_id": fact_key(item.external_id, metric, observed),
                "name": metric.name,
                "value": Decimal(metric.value),
                "unit": metric.unit,
                "period": metric.period,
                "ts_code": metric.ts_code,
                "observed_at": observed,
                # jsonb 落库前必须 sanitize：UUID / NaN 都不是合法 JSON 值
                "attributes": json_safe(metric.attributes),
                "payload": json_safe(
                    {
                        "item_external_id": item.external_id,
                        "source_name": item.source_name,
                        "provenance": item.provenance.model_dump(mode="json", exclude_none=True),
                        "metric": metric.model_dump(mode="json"),
                    }
                ),
            }
        )
    return rows


class MarketFactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_many(self, rows: list[dict]) -> int:
        """按 (连接器, external_id) 幂等写入；返回受影响的条数。

        冲突时更新数值本身 —— 上游修订数据比我们保留旧值更重要。
        """
        if not rows:
            return 0
        ins = pg_insert(MarketFact).values(rows)
        stmt = (
            ins.on_conflict_do_update(
                index_elements=["source_connector_id", "external_id"],
                index_where=text("deleted_at IS NULL"),
                set_={
                    "value": ins.excluded.value,
                    "unit": ins.excluded.unit,
                    "period": ins.excluded.period,
                    "observed_at": ins.excluded.observed_at,
                    "attributes": ins.excluded.attributes,
                    "payload": ins.excluded.payload,
                    "updated_at": func.now(),
                },
            )
            .returning(MarketFact.id)
        )
        result = await self.session.execute(stmt)
        return len(result.scalars().all())

    async def upsert_from_item(
        self,
        item: NormalizedItem,
        connector_id: uuid.UUID,
        *,
        raw_document_id: uuid.UUID | None = None,
        news_item_id: uuid.UUID | None = None,
    ) -> int:
        """把一个统一信封里的数值事实落库。无 metrics 时是 no-op。"""
        if not item.metrics:
            return 0
        rows = build_rows(
            item,
            connector_id,
            raw_document_id=raw_document_id,
            news_item_id=news_item_id,
        )
        return await self.upsert_many(rows)

    # ---------------- 读取 ----------------

    def list_query(
        self,
        *,
        ts_code: str | None = None,
        name: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> Select:
        stmt = select(MarketFact).where(MarketFact.deleted_at.is_(None))
        if ts_code:
            stmt = stmt.where(MarketFact.ts_code == ts_code)
        if name:
            stmt = stmt.where(MarketFact.name == name)
        if since:
            stmt = stmt.where(MarketFact.observed_at >= since)
        if until:
            stmt = stmt.where(MarketFact.observed_at <= until)
        # 时间序列：新的在前；没有观测时间的排最后
        return stmt.order_by(MarketFact.observed_at.desc().nullslast(), MarketFact.created_at.desc())

    async def list_facts(
        self,
        *,
        ts_code: str | None = None,
        name: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MarketFact]:
        stmt = self.list_query(ts_code=ts_code, name=name, since=since, until=until)
        rows = await self.session.execute(stmt.limit(limit).offset(offset))
        return list(rows.scalars().all())

    async def count(self) -> int:
        return int(
            (
                await self.session.execute(
                    select(func.count()).select_from(MarketFact).where(
                        MarketFact.deleted_at.is_(None)
                    )
                )
            ).scalar_one()
        )


__all__ = ["MarketFactRepository", "build_rows", "fact_key"]
