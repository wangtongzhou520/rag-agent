from fastmcp import Client

from mcp_server.main import mcp


async def test_mcp_server_metadata_and_business_tools() -> None:
    assert mcp.name == "ragent-mcp-server"
    assert mcp.version == "0.0.1"

    async with Client(mcp) as client:
        tools = await client.list_tools()
        assert {tool.name for tool in tools} == {
            "weather_query",
            "sales_query",
            "ticket_query",
        }
        weather = next(tool for tool in tools if tool.name == "weather_query")
        assert weather.inputSchema["required"] == ["city"]

        result = await client.call_tool(
            "weather_query",
            {"city": "北京", "queryType": "forecast", "days": 3},
            raise_on_error=False,
        )

    assert result.is_error is False
    assert result.structured_content["city"] == "北京"
    assert result.structured_content["queryType"] == "forecast"
    assert len(result.structured_content["forecasts"]) == 3


async def test_mcp_tool_error_is_returned_as_protocol_error_result() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool(
            "weather_query", {"city": "不存在"}, raise_on_error=False
        )

    assert result.is_error is True
    assert "暂不支持查询该城市" in result.content[0].text
