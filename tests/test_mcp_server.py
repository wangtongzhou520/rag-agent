from fastmcp import Client

from mcp_server.main import mcp


async def test_mcp_server_metadata_and_placeholder_tool() -> None:
    assert mcp.name == "ragent-mcp-server"
    assert mcp.version == "0.0.1"

    async with Client(mcp) as client:
        tools = await client.list_tools()
        weather = next(tool for tool in tools if tool.name == "weather_query")
        assert weather.inputSchema["required"] == ["city"]

        result = await client.call_tool(
            "weather_query",
            {"city": "Beijing"},
            raise_on_error=False,
        )

    assert result.is_error is False
    assert result.structured_content == {
        "city": "Beijing",
        "weather": "sunny",
        "temperature": 26,
        "unit": "celsius",
    }
