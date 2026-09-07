"""确定性演示服务工单查询工具。"""

import hashlib
import random
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastmcp import FastMCP

_STATUS = ("待处理", "处理中", "已解决", "已关闭")
_PRIORITIES = ("紧急", "高", "中", "低")


def register(server: FastMCP) -> None:
    server.tool(ticket_query)


def ticket_query(
    queryType: Literal["summary", "list", "stats"] = "summary",
    status: str | None = None,
    priority: str | None = None,
    limit: int = 10,
) -> dict:
    """查询最近 30 天的模拟服务工单，可按状态和优先级过滤。"""
    limit = min(50, max(1, limit))
    today = datetime.now(UTC).date()
    seed = f"{today}|{queryType}|{status}|{priority}"
    randomizer = random.Random(int.from_bytes(hashlib.sha256(seed.encode()).digest()[:8]))
    records = [
        {
            "ticketId": f"TK-{today:%Y%m}-{index + 1:04d}",
            "title": randomizer.choice(("登录失败", "数据导入异常", "权限配置", "接口超时")),
            "status": status or randomizer.choice(_STATUS),
            "priority": priority or randomizer.choice(_PRIORITIES),
            "createdDate": (today - timedelta(days=randomizer.randint(0, 29))).isoformat(),
        }
        for index in range(limit)
    ]
    counts = {value: sum(item["status"] == value for item in records) for value in _STATUS}
    return {
        "queryType": queryType,
        "filters": {"status": status, "priority": priority},
        "statusCounts": counts,
        "records": records if queryType == "list" else [],
    }
