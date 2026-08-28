"""模型档位选择和三态熔断状态机测试。"""

import asyncio

from app.model_runtime.routing import (
    CircuitState,
    ModelCandidate,
    ModelHealthStore,
    ModelSelector,
    Tier,
    TierPlan,
)


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


def candidates() -> dict[str, ModelCandidate]:
    return {
        "fast": ModelCandidate("fast", "bailian", "qwen-flash"),
        "think": ModelCandidate("think", "bailian", "qwen-max", supports_thinking=True),
        "disabled": ModelCandidate("disabled", "bailian", "disabled", enabled=False),
        "local": ModelCandidate("local", "ollama", "qwen-local", priority=2),
    }


async def test_selector_thinking_wins_override_and_preferred_is_deduplicated() -> None:
    selector = ModelSelector(
        candidates(),
        {
            Tier.FAST: TierPlan(("fast",), 5000),
            Tier.STANDARD: TierPlan(("fast", "think"), 30000),
            Tier.DEEP: TierPlan(("think", "fast"), 120000),
        },
    )

    targets = await selector.build_tier_targets(
        thinking=True,
        override=Tier.FAST,
        preferred_model_id="think",
    )

    assert [target.id for target in targets] == ["think"]
    assert targets[0].tier is Tier.DEEP
    assert targets[0].timeout_ms == 120000


async def test_selector_filters_disabled_missing_and_unconfigured_provider() -> None:
    selector = ModelSelector(
        candidates(),
        {Tier.STANDARD: TierPlan(("disabled", "missing", "local", "fast"), 30000)},
        configured_providers={"bailian"},
    )

    targets = await selector.build_tier_targets(thinking=False)

    assert [target.id for target in targets] == ["fast"]


async def test_non_chat_selection_uses_default_then_priority_and_id() -> None:
    selector = ModelSelector({}, {})
    items = [
        ModelCandidate("z", "ollama", "z", priority=1),
        ModelCandidate("a", "ollama", "a", priority=1),
        ModelCandidate("default", "ollama", "d", priority=99),
    ]

    targets = await selector.select_candidates(items, default_model="default")

    assert [target.id for target in targets] == ["default", "a", "z"]


async def test_health_store_opens_after_threshold_and_allows_one_probe() -> None:
    clock = FakeClock()
    health = ModelHealthStore(failure_threshold=2, open_duration_ms=30000, clock=clock)

    first = await health.allow_call("model")
    assert first is not None and not first.is_probe
    await health.mark_failure("model")
    assert not await health.is_unavailable("model")
    await health.mark_failure("model")
    assert await health.is_unavailable("model")
    assert await health.allow_call("model") is None

    clock.value += 30
    probe = await health.allow_call("model")
    assert probe is not None and probe.is_probe
    assert await health.allow_call("model") is None
    await health.mark_success("model")
    state, failures, open_until = await health.snapshot("model")
    assert (state, failures, open_until) == (CircuitState.CLOSED, 0, 0.0)


async def test_half_open_release_requires_matching_token_and_allows_retry() -> None:
    clock = FakeClock()
    health = ModelHealthStore(open_duration_ms=1000, clock=clock)
    await health.mark_failure("model")
    await health.mark_failure("model")
    clock.value += 1
    probe = await health.allow_call("model")
    assert probe is not None and probe.is_probe

    wrong = type(probe)(probe.model_id, probe.token + 1)
    assert not await health.release_half_open_permit(wrong)
    assert await health.allow_call("model") is None
    assert await health.release_half_open_permit(probe)
    retry = await health.allow_call("model")
    assert retry is not None and retry.is_probe


async def test_half_open_failure_reopens_until_duration() -> None:
    clock = FakeClock()
    health = ModelHealthStore(open_duration_ms=1000, clock=clock)
    await health.mark_failure("model")
    await health.mark_failure("model")
    clock.value += 1
    probe = await health.allow_call("model")
    assert probe is not None
    await health.mark_failure("model")
    assert await health.allow_call("model") is None
    clock.value += 1
    assert (await health.allow_call("model")).is_probe


async def test_concurrent_half_open_calls_only_issue_one_probe() -> None:
    clock = FakeClock()
    health = ModelHealthStore(open_duration_ms=1000, clock=clock)
    await health.mark_failure("model")
    await health.mark_failure("model")
    clock.value += 1

    permits = await asyncio.gather(*(health.allow_call("model") for _ in range(20)))

    assert sum(permit is not None and permit.is_probe for permit in permits) == 1
