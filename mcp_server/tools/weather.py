"""确定性演示天气工具；不依赖外部天气服务。"""

import hashlib
import random
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

_CITIES = {
    "北京": 39.9,
    "上海": 31.2,
    "广州": 23.1,
    "深圳": 22.5,
    "杭州": 30.3,
    "成都": 30.6,
    "武汉": 30.6,
    "西安": 34.3,
}
_WEATHER = ("晴", "多云", "阴", "小雨")


def register(server: FastMCP) -> None:
    server.tool(weather_query)


def weather_query(
    city: str,
    queryType: Literal["current", "forecast"] = "current",
    days: int = 3,
) -> dict:
    """查询国内主要城市的当前天气或未来天气；days 范围为 1–7。"""
    city = city.strip()
    if city not in _CITIES:
        raise ToolError(f"暂不支持查询该城市，当前支持：{'、'.join(_CITIES)}")
    days = min(7, max(1, days))
    today = datetime.now(UTC).date()
    count = 1 if queryType == "current" else days
    forecasts = [_forecast(city, today + timedelta(days=index)) for index in range(count)]
    return {
        "city": city,
        "queryType": queryType,
        "updatedDate": today.isoformat(),
        "forecasts": forecasts,
    }


def _forecast(city: str, target: date) -> dict:
    digest = hashlib.sha256(f"{city}:{target.isoformat()}".encode()).digest()
    randomizer = random.Random(int.from_bytes(digest[:8]))
    latitude = _CITIES[city]
    month = target.month
    seasonal = 30 if 6 <= month <= 8 else 18 if 3 <= month <= 5 or 9 <= month <= 11 else 6
    base = seasonal - (latitude - 25) * 0.45
    low = round(base - 3 - randomizer.random() * 3)
    high = round(base + 3 + randomizer.random() * 4)
    return {
        "date": target.isoformat(),
        "weather": randomizer.choice(_WEATHER),
        "lowCelsius": low,
        "highCelsius": high,
        "humidity": randomizer.randint(35, 85),
    }
