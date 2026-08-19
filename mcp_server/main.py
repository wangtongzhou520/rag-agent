"""独立 MCP 工具服务（Streamable HTTP，默认 :9099）。

使用独立 fastmcp 包（FastMCP 3，底层为 MCP SDK v2 引擎）。
python -m mcp_server.main 启动；业务工具见 mcp_server/tools/，随 M4 接入。
"""

import os

from fastmcp import FastMCP

mcp = FastMCP("ragent-mcp-server", version="0.0.1")


@mcp.tool
def weather_query(city: str) -> dict:
    """查询城市天气（占位实现，返回模拟数据）。"""
    return {
        "city": city,
        "weather": "sunny",
        "temperature": 26,
        "unit": "celsius",
    }


# TODO(M4): 注册业务工具（sales / ticket / youcom_search），见 06 文档


def main() -> None:
    host = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_SERVER_PORT", "9099"))
    mcp.run(transport="http", host=host, port=port)


if __name__ == "__main__":
    main()
