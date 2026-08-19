"""健康检查接口冒烟测试。"""

from httpx import AsyncClient


async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "0"
    assert body["data"] == {"status": "UP"}
    assert body["requestId"] == resp.headers["X-Request-ID"]


async def test_health_propagates_valid_request_id(client: AsyncClient) -> None:
    resp = await client.get("/health", headers={"X-Request-ID": "test-request-123"})
    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"] == "test-request-123"
    assert resp.json()["requestId"] == "test-request-123"
