import os
from collections.abc import AsyncIterator

os.environ.setdefault("RAGENT_DATASOURCE__AUTO_DDL", "false")

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.main import app


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    if os.environ.get("RAGENT_RUN_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(reason="设置 RAGENT_RUN_INTEGRATION=1 后运行 Docker 集成测试")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with LifespanManager(app) as manager:
        transport = ASGITransport(app=manager.app, raise_app_exceptions=True)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as async_client:
            yield async_client
