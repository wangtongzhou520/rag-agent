"""运行时设置脱敏、模型状态与权限契约测试。"""

import json
from types import SimpleNamespace

from app.admin.runtime.router import router
from app.admin.runtime.service import RuntimeSettingsService
from app.framework.config import get_settings
from app.model_runtime.routing import ModelHealthStore
from app.system.auth.deps import require_admin


async def test_runtime_snapshot_masks_secrets_and_reports_circuit_state() -> None:
    settings = get_settings().model_copy(deep=True)
    settings.ai.providers.bailian.api_key = "abcdef1234567890"
    health = ModelHealthStore(failure_threshold=2, open_duration_ms=30_000)
    await health.mark_failure("qwen-plus")
    await health.mark_failure("qwen-plus")
    service = RuntimeSettingsService(settings, SimpleNamespace(health=health))

    snapshot = await service.snapshot()

    assert snapshot["readOnly"] is True
    assert snapshot["ai"]["providers"]["bailian"]["apiKey"] == "abcdef***7890"
    assert snapshot["ai"]["providers"]["bailian"]["configured"] is True
    assert snapshot["ai"]["chat"]["tiers"]["standard"]["candidates"][0] == "qwen3-max"
    qwen_plus = next(
        item
        for item in snapshot["ai"]["chat"]["candidates"]
        if item["id"] == "qwen-plus"
    )
    assert qwen_plus["availability"] == "circuit_open"
    assert qwen_plus["health"]["state"] == "open"
    assert qwen_plus["health"]["retryAfterMs"] > 0
    qwen_deep = next(
        item
        for item in snapshot["ai"]["chat"]["candidates"]
        if item["id"] == "qwen3-max"
    )
    assert qwen_deep["supportsThinking"] is True
    default_embedding = snapshot["ai"]["embedding"]["candidates"][0]
    assert default_embedding["isDefault"] is True
    assert "abcdef1234567890" not in json.dumps(snapshot)


def test_runtime_settings_route_requires_admin() -> None:
    assert len(router.routes) == 1
    route = router.routes[0]
    assert route.path == "/rag/settings"
    assert require_admin in {
        dependency.call for dependency in route.dependant.dependencies
    }
