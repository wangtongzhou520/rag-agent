"""确定性演示销售查询工具。"""

import hashlib
import random
from datetime import UTC, datetime
from typing import Literal

from fastmcp import FastMCP

_REGIONS = ("华东", "华南", "华北", "西南")
_PRODUCTS = ("企业版", "专业版", "基础版")


def register(server: FastMCP) -> None:
    server.tool(sales_query)


def sales_query(
    period: Literal["本月", "上月", "本季度", "上季度", "本年"] = "本月",
    queryType: Literal["summary", "ranking", "detail", "trend"] = "summary",
    region: str | None = None,
    product: str | None = None,
    limit: int = 10,
) -> dict:
    """查询模拟销售汇总、排行、明细或趋势，可按地区和产品过滤。"""
    limit = min(50, max(1, limit))
    today = datetime.now(UTC).date()
    randomizer = _randomizer(period, queryType, region, product)
    records = [
        {
            "orderId": f"SO-{today:%Y%m}-{index + 1:04d}",
            "region": region or randomizer.choice(_REGIONS),
            "product": product or randomizer.choice(_PRODUCTS),
            "amountWan": round(randomizer.uniform(3, 180), 2),
        }
        for index in range(limit)
    ]
    total = round(sum(float(item["amountWan"]) for item in records), 2)
    return {
        "period": period,
        "queryType": queryType,
        "filters": {"region": region, "product": product},
        "totalAmountWan": total,
        "orderCount": len(records),
        "records": records if queryType in {"detail", "ranking"} else [],
    }


def _randomizer(*values: object) -> random.Random:
    seed = "|".join(str(value or "") for value in values)
    seed += datetime.now(UTC).date().isoformat()
    return random.Random(int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8]))
