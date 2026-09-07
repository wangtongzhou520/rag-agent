"""运行时配置脱敏汇总与模型熔断状态查询。"""

import time
from collections.abc import Iterable

from app.framework.config import Settings
from app.model_runtime.factory import ModelRuntime
from app.model_runtime.routing import CircuitState, ModelProvider


class RuntimeSettingsService:
    def __init__(self, settings: Settings, runtime: ModelRuntime) -> None:
        self._settings = settings
        self._runtime = runtime

    async def snapshot(self) -> dict:
        settings = self._settings
        providers = self._providers()
        configured = {
            name for name, value in providers.items() if value["configured"]
        }
        chat = await self._chat(configured)
        embedding = await self._embedding(configured)
        rerank = await self._rerank(configured)
        return {
            "readOnly": True,
            "sourcePriority": ["environment", "application.yaml", "defaults"],
            "engine": {"type": settings.rag.engine.type},
            "backends": {
                "vector": {"type": settings.rag.vector.type},
                "keyword": {"type": settings.rag.keyword.type},
                "graph": {"type": settings.rag.graph.type},
            },
            "rag": {
                "default": {
                    "dimension": settings.rag.default.dimension,
                    "topK": settings.rag.default.top_k,
                    "sseTimeoutMs": settings.rag.default.sse_timeout_ms,
                },
                "search": {
                    "recallBudget": settings.rag.recall_budget,
                    "rerankCandidateLimit": settings.rag.rerank_candidate_limit,
                    "retrievalTimeoutMs": settings.rag.retrieval.timeout_ms,
                    "queryRewrite": {
                        "enabled": settings.rag.query_rewrite.enabled,
                        "timeoutMs": settings.rag.query_rewrite.timeout_ms,
                    },
                    "scope": {
                        "minIntentScore": settings.rag.intent.min_score,
                        "confidenceThreshold": settings.rag.intent.confidence_threshold,
                        "supplementRatio": settings.rag.scope.supplement_ratio,
                    },
                    "fusion": {
                        "strategy": "weighted-rrf",
                        "rrfK": settings.rag.fusion.rrf_k,
                        "channelWeights": settings.rag.fusion.channel_weights.model_dump(),
                    },
                },
                "memory": {
                    "historyKeepTurns": settings.rag.memory.history_keep_turns,
                    "titleMaxLength": settings.rag.memory.title_max_length,
                },
                "rateLimit": {"enabled": settings.rag.rate_limit.enabled},
            },
            "ai": {
                "providers": providers,
                "chat": chat,
                "embedding": embedding,
                "rerank": rerank,
                "selection": {
                    "failureThreshold": settings.ai.selection.failure_threshold,
                    "openDurationMs": settings.ai.selection.open_duration_ms,
                },
                "stream": {
                    "messageChunkSize": settings.ai.stream.message_chunk_size
                },
            },
            "storage": {"localDir": settings.storage.local_dir},
        }

    def _providers(self) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for name in ("ollama", "bailian", "siliconflow", "aihubmix"):
            provider = getattr(self._settings.ai.providers, name)
            configured = bool(provider.url) and (
                name == str(ModelProvider.OLLAMA) or bool(provider.api_key)
            )
            result[name] = {
                "url": provider.url or None,
                "apiKey": _mask_secret(provider.api_key),
                "configured": configured,
                "endpoints": dict(provider.endpoints),
            }
        result[str(ModelProvider.NOOP)] = {
            "url": None,
            "apiKey": None,
            "configured": True,
            "endpoints": {},
        }
        return result

    async def _chat(self, configured: set[str]) -> dict:
        tier_settings = self._settings.ai.chat
        tier_map = {
            "fast": tier_settings.fast,
            "standard": tier_settings.standard,
            "deep": tier_settings.deep,
        }
        memberships: dict[str, list[str]] = {}
        for tier, plan in tier_map.items():
            for model_id in plan.candidates:
                memberships.setdefault(model_id, []).append(tier)
        candidates = []
        for candidate in tier_settings.candidates:
            candidates.append(
                await self._candidate(
                    candidate.resolved_id,
                    candidate.provider,
                    candidate.model,
                    candidate.enabled,
                    configured,
                    url=candidate.url,
                    priority=candidate.priority,
                    dimension=candidate.dimension,
                    supports_thinking=candidate.supports_thinking,
                    tiers=memberships.get(candidate.resolved_id, []),
                )
            )
        return {
            "defaultTier": "standard",
            "deepThinkingTier": "deep",
            "tiers": {
                name: {
                    "candidates": list(plan.candidates),
                    "timeoutMs": plan.timeout_ms,
                }
                for name, plan in tier_map.items()
            },
            "candidates": candidates,
        }

    async def _embedding(self, configured: set[str]) -> dict:
        settings = self._settings.ai.embedding
        candidates = [
            await self._candidate(
                candidate.resolved_id,
                candidate.provider,
                candidate.model,
                candidate.enabled,
                configured,
                url=candidate.url,
                priority=candidate.priority,
                dimension=candidate.dimension,
                is_default=candidate.resolved_id == settings.default_model,
            )
            for candidate in settings.candidates
        ]
        return {"defaultModel": settings.default_model, "candidates": candidates}

    async def _rerank(self, configured: set[str]) -> dict:
        settings = self._settings.ai.rerank
        candidates = [
            await self._candidate(
                candidate.resolved_id,
                candidate.provider,
                candidate.model,
                candidate.enabled,
                configured,
                url=candidate.url,
                priority=candidate.priority,
                is_default=candidate.resolved_id == settings.default_model,
            )
            for candidate in settings.candidates
        ]
        return {"defaultModel": settings.default_model, "candidates": candidates}

    async def _candidate(
        self,
        model_id: str,
        provider: str,
        model: str,
        enabled: bool,
        configured: Iterable[str],
        *,
        url: str | None = None,
        priority: int | None = None,
        dimension: int | None = None,
        supports_thinking: bool = False,
        tiers: list[str] | None = None,
        is_default: bool = False,
    ) -> dict:
        state, failures, open_until = await self._runtime.health.snapshot(model_id)
        provider_configured = provider in configured
        availability = _availability(enabled, provider_configured, state)
        return {
            "id": model_id,
            "provider": provider,
            "model": model,
            "enabled": enabled,
            "providerConfigured": provider_configured,
            "availability": availability,
            "health": {
                "state": str(state),
                "consecutiveFailures": failures,
                "retryAfterMs": max(
                    0, int((open_until - time.monotonic()) * 1000)
                )
                if state is CircuitState.OPEN
                else 0,
            },
            "url": url,
            "priority": priority,
            "dimension": dimension,
            "supportsThinking": supports_thinking,
            "tiers": tiers or [],
            "isDefault": is_default,
        }


def _availability(
    enabled: bool, provider_configured: bool, state: CircuitState
) -> str:
    if not enabled:
        return "disabled"
    if not provider_configured:
        return "unconfigured"
    if state is CircuitState.OPEN:
        return "circuit_open"
    if state is CircuitState.HALF_OPEN:
        return "probing"
    return "ready"


def _mask_secret(value: str) -> str | None:
    if not value:
        return None
    if len(value) <= 10:
        return "******"
    return f"{value[:6]}***{value[-4:]}"
