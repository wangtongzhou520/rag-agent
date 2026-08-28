"""模型候选选择、容错执行与进程内三态熔断。

本模块只做路由决策与通用的容错循环，不创建 HTTP 客户端，也不感知具体协议：
``ModelRoutingExecutor`` 通过注入的 caller 回调发起调用，provider client 由
调用层以 ``{provider: client}`` 注册表注入，避免路由策略和协议适配相互耦合。
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeVar

from app.framework.exceptions import RemoteException
from app.framework.logging import get_logger

logger = get_logger(__name__)


class Tier(StrEnum):
    FAST = "fast"
    STANDARD = "standard"
    DEEP = "deep"


class ModelProvider(StrEnum):
    OLLAMA = "ollama"
    BAILIAN = "bailian"
    SILICONFLOW = "siliconflow"
    AIHUBMIX = "aihubmix"
    NOOP = "noop"


class ModelCapability(StrEnum):
    CHAT = "chat"
    EMBEDDING = "embedding"
    RERANK = "rerank"
    VLM = "vlm"


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    """物理模型注册项；候选顺序由档位或 priority 决定。"""

    id: str
    provider: str
    model: str
    url: str | None = None
    dimension: int | None = None
    priority: int = 100
    enabled: bool = True
    supports_thinking: bool = False


@dataclass(frozen=True, slots=True)
class TierPlan:
    """一个 chat 档位的有序候选引用和超时预算。"""

    candidates: tuple[str, ...]
    timeout_ms: int

    def __post_init__(self) -> None:
        if self.timeout_ms <= 0:
            raise ValueError("tier timeout_ms must be positive")


@dataclass(frozen=True, slots=True)
class ModelTarget:
    """下沉到调用层的候选目标，包含本次档位的超时预算。"""

    candidate: ModelCandidate
    tier: Tier | None = None
    timeout_ms: int | None = None

    @property
    def id(self) -> str:
        return self.candidate.id


@dataclass(frozen=True, slots=True)
class CallPermit:
    """熔断调用许可；token 非零表示 HALF_OPEN 探测名额。"""

    model_id: str
    token: int = 0

    @property
    def is_probe(self) -> bool:
        return self.token != 0


@dataclass(slots=True)
class _HealthEntry:
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    open_until: float = 0.0
    half_open_token: int = 0


class ModelHealthStore:
    """进程内模型熔断器。

    每个 model id 独立维护状态。所有检查和状态迁移共用同一把 asyncio 锁，
    因此 OPEN 到期时最多只有一个协程拿到 HALF_OPEN 探测 token。
    """

    def __init__(
        self,
        failure_threshold: int = 2,
        open_duration_ms: int = 30000,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if open_duration_ms <= 0:
            raise ValueError("open_duration_ms must be positive")
        self.failure_threshold = failure_threshold
        self.open_duration_s = open_duration_ms / 1000
        self._clock = clock or time.monotonic
        self._entries: dict[str, _HealthEntry] = {}
        self._lock = asyncio.Lock()
        self._token_seq = 0

    def _entry(self, model_id: str) -> _HealthEntry:
        return self._entries.setdefault(model_id, _HealthEntry())

    async def is_unavailable(self, model_id: str) -> bool:
        async with self._lock:
            entry = self._entry(model_id)
            now = self._clock()
            return (entry.state is CircuitState.OPEN and entry.open_until > now) or (
                entry.state is CircuitState.HALF_OPEN and entry.half_open_token != 0
            )

    async def allow_call(self, model_id: str) -> CallPermit | None:
        """获取普通调用许可，或在 OPEN 到期时获取唯一探测许可。"""
        async with self._lock:
            entry = self._entry(model_id)
            now = self._clock()
            if entry.state is CircuitState.OPEN:
                if entry.open_until > now:
                    return None
                entry.state = CircuitState.HALF_OPEN
                self._token_seq += 1
                entry.half_open_token = self._token_seq
                return CallPermit(model_id, entry.half_open_token)
            if entry.state is CircuitState.HALF_OPEN:
                if entry.half_open_token:
                    return None
                self._token_seq += 1
                entry.half_open_token = self._token_seq
                return CallPermit(model_id, entry.half_open_token)
            return CallPermit(model_id)

    async def mark_success(self, model_id: str) -> None:
        async with self._lock:
            self._entries[model_id] = _HealthEntry()

    async def mark_failure(self, model_id: str) -> None:
        async with self._lock:
            entry = self._entry(model_id)
            now = self._clock()
            if entry.state is CircuitState.HALF_OPEN:
                entry.state = CircuitState.OPEN
                entry.open_until = now + self.open_duration_s
                entry.consecutive_failures = 0
                entry.half_open_token = 0
                return
            if entry.state is CircuitState.OPEN:
                return
            entry.consecutive_failures += 1
            if entry.consecutive_failures >= self.failure_threshold:
                entry.state = CircuitState.OPEN
                entry.open_until = now + self.open_duration_s
                entry.consecutive_failures = 0

    async def release_half_open_permit(self, permit: CallPermit) -> bool:
        """释放取消/中断的探测名额；迟到或错误 token 不得影响新一轮探测。"""
        if not permit.is_probe:
            return False
        async with self._lock:
            entry = self._entry(permit.model_id)
            if (
                entry.state is CircuitState.HALF_OPEN
                and entry.half_open_token == permit.token
            ):
                entry.half_open_token = 0
                return True
            return False

    async def snapshot(self, model_id: str) -> tuple[CircuitState, int, float]:
        """返回测试和观测使用的不可变状态快照。"""
        async with self._lock:
            entry = self._entry(model_id)
            return entry.state, entry.consecutive_failures, entry.open_until


class ModelSelector:
    """根据请求意图生成有序、已过滤的模型目标列表。"""

    def __init__(
        self,
        candidates: Mapping[str, ModelCandidate],
        tiers: Mapping[str | Tier, TierPlan],
        *,
        default_tier: str | Tier = Tier.STANDARD,
        deep_thinking_tier: str | Tier | None = Tier.DEEP,
        health_store: ModelHealthStore | None = None,
        configured_providers: set[str] | None = None,
    ) -> None:
        self.candidates = dict(candidates)
        self.tiers = {str(key): value for key, value in tiers.items()}
        self.default_tier = str(default_tier)
        self.deep_thinking_tier = str(deep_thinking_tier) if deep_thinking_tier else None
        self.health_store = health_store
        self.configured_providers = configured_providers

    def resolve_tier_name(
        self,
        *,
        thinking: bool,
        override: str | Tier | None = None,
    ) -> str:
        """thinking 优先于显式档位，其次使用 override，最后使用默认档位。"""
        if thinking and self.deep_thinking_tier:
            return self.deep_thinking_tier
        return str(override) if override is not None else self.default_tier

    async def build_tier_targets(
        self,
        *,
        thinking: bool,
        override: str | Tier | None = None,
        preferred_model_id: str | None = None,
    ) -> list[ModelTarget]:
        tier_name = self.resolve_tier_name(thinking=thinking, override=override)
        plan = self.tiers.get(tier_name)
        if plan is None:
            return []

        ordered_ids = self._preferred_then_plan(preferred_model_id, plan.candidates)
        targets: list[ModelTarget] = []
        for model_id in ordered_ids:
            candidate = self.candidates.get(model_id)
            if candidate is None or not candidate.enabled:
                continue
            if thinking and not candidate.supports_thinking:
                continue
            if (
                self.configured_providers is not None
                and candidate.provider != ModelProvider.NOOP
                and candidate.provider not in self.configured_providers
            ):
                continue
            if self.health_store and await self.health_store.is_unavailable(candidate.id):
                continue
            targets.append(ModelTarget(candidate, Tier(tier_name), plan.timeout_ms))
        return targets

    async def select_candidates(
        self,
        candidates: Sequence[ModelCandidate],
        *,
        default_model: str | None = None,
    ) -> list[ModelTarget]:
        """为 embedding/rerank/vlm 生成 defaultModel 优先、priority 升序列表。"""
        by_id = {candidate.id: candidate for candidate in candidates}
        ordered: list[ModelCandidate] = []
        if default_model and default_model in by_id:
            ordered.append(by_id[default_model])
        ordered.extend(
            sorted(
                (candidate for candidate in candidates if candidate.id != default_model),
                key=lambda item: (item.priority, item.id),
            )
        )
        result: list[ModelTarget] = []
        for candidate in ordered:
            if not candidate.enabled:
                continue
            if self.health_store and await self.health_store.is_unavailable(candidate.id):
                continue
            result.append(ModelTarget(candidate))
        return result

    @staticmethod
    def _preferred_then_plan(
        preferred_model_id: str | None,
        plan_ids: Sequence[str],
    ) -> list[str]:
        result: list[str] = []
        for model_id in ([preferred_model_id] if preferred_model_id else []) + list(plan_ids):
            if model_id and model_id not in result:
                result.append(model_id)
        return result


T = TypeVar("T")


class ModelRoutingExecutor:
    """同步调用的候选容错执行器（docs/04 §3.5）。

    按 targets 顺序逐个尝试：client 缺失告警 continue、熔断拒绝 continue、
    调用失败 mark_failure 切下一候选；全部失败抛 RemoteException。
    mark_success/mark_failure 以候选 id（modelId）为粒度，不是 provider 粒度。
    """

    def __init__(self, health_store: ModelHealthStore, clients: Mapping[str, Any]) -> None:
        self._health_store = health_store
        self._clients = clients

    async def execute_with_fallback(
        self,
        targets: Sequence[ModelTarget],
        caller: Callable[[Any, ModelTarget], Awaitable[T]],
        label: str,
    ) -> T:
        if not targets:
            raise RemoteException(f"No {label} model candidates available")
        last: Exception | None = None
        for target in targets:
            client = self._clients.get(str(target.candidate.provider))
            if client is None:
                logger.warning(
                    "model client 缺失，跳过候选",
                    model_id=target.id,
                    provider=str(target.candidate.provider),
                )
                continue
            permit = await self._health_store.allow_call(target.id)
            if permit is None:
                continue
            try:
                result = await caller(client, target)
            except Exception as exc:  # noqa: BLE001 路由层不区分错误类型一律 fallback（docs/04 §6.3）
                last = exc
                await self._health_store.mark_failure(target.id)
                logger.warning(
                    "模型候选调用失败，切换下一候选",
                    model_id=target.id,
                    provider=str(target.candidate.provider),
                    error=str(exc),
                )
                continue
            await self._health_store.mark_success(target.id)
            return result
        raise RemoteException(f"All {label} model candidates failed: {last}")
