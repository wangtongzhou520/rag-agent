"""模型运行时装配：由 Settings 构建 provider clients、selector、熔断与服务。

chat 与 embedding 共享同一个 ModelHealthStore（熔断以候选 id 为粒度，
docs/04 §5.2）与同一个 HttpClientFactory（连接池复用，docs/04 §6.2）。
"""

from dataclasses import dataclass

from app.framework.config import Settings
from app.model_runtime.chat.providers import (
    AIHubMixChatClient,
    BaiLianChatClient,
    OllamaChatClient,
    SiliconFlowChatClient,
)
from app.model_runtime.chat.service import RoutingLLMService
from app.model_runtime.embedding.providers import (
    AIHubMixEmbeddingClient,
    BaiLianEmbeddingClient,
    OllamaEmbeddingClient,
    SiliconFlowEmbeddingClient,
)
from app.model_runtime.embedding.service import RoutingEmbeddingService
from app.model_runtime.http import HttpClientFactory
from app.model_runtime.rerank.base import BaiLianRerankClient, NoopRerankClient
from app.model_runtime.rerank.service import RoutingRerankService
from app.model_runtime.routing import (
    ModelCandidate,
    ModelHealthStore,
    ModelProvider,
    ModelSelector,
    Tier,
    TierPlan,
)

_CHAT_CLIENT_CLASSES = {
    ModelProvider.OLLAMA: OllamaChatClient,
    ModelProvider.BAILIAN: BaiLianChatClient,
    ModelProvider.SILICONFLOW: SiliconFlowChatClient,
    ModelProvider.AIHUBMIX: AIHubMixChatClient,
}

_EMBEDDING_CLIENT_CLASSES = {
    ModelProvider.BAILIAN: BaiLianEmbeddingClient,
    ModelProvider.OLLAMA: OllamaEmbeddingClient,
    ModelProvider.SILICONFLOW: SiliconFlowEmbeddingClient,
    ModelProvider.AIHUBMIX: AIHubMixEmbeddingClient,
}


@dataclass(slots=True)
class ModelRuntime:
    """装配产物；http 由调用方在关闭时 aclose。"""

    llm: RoutingLLMService
    embedding: RoutingEmbeddingService
    rerank: RoutingRerankService
    health: ModelHealthStore
    http: HttpClientFactory


def _configured_providers(settings: Settings) -> set[str]:
    """ollama 有 url 即已配置；其余 provider 需 url + api_key。"""
    providers = settings.ai.providers
    configured: set[str] = set()
    for name, provider in (
        (ModelProvider.OLLAMA, providers.ollama),
        (ModelProvider.BAILIAN, providers.bailian),
        (ModelProvider.SILICONFLOW, providers.siliconflow),
        (ModelProvider.AIHUBMIX, providers.aihubmix),
    ):
        if not provider.url:
            continue
        if name == ModelProvider.OLLAMA or provider.api_key:
            configured.add(str(name))
    return configured


def _build_clients(
    settings: Settings,
    http: HttpClientFactory,
    configured: set[str],
    classes: dict,
) -> dict:
    clients = {}
    for name, client_cls in classes.items():
        if str(name) not in configured:
            continue
        provider = getattr(settings.ai.providers, str(name))
        clients[str(name)] = client_cls(
            http, provider.url, provider.api_key, provider.endpoints
        )
    return clients


def build_model_runtime(settings: Settings) -> ModelRuntime:
    http = HttpClientFactory()
    configured = _configured_providers(settings)
    health = ModelHealthStore(
        failure_threshold=settings.ai.selection.failure_threshold,
        open_duration_ms=settings.ai.selection.open_duration_ms,
    )

    chat = settings.ai.chat
    chat_candidates = {
        candidate.resolved_id: ModelCandidate(
            id=candidate.resolved_id,
            provider=candidate.provider,
            model=candidate.model,
            url=candidate.url,
            dimension=candidate.dimension,
            priority=candidate.priority,
            enabled=candidate.enabled,
            supports_thinking=candidate.supports_thinking,
        )
        for candidate in chat.candidates
    }
    tiers = {
        str(Tier.FAST): TierPlan(tuple(chat.fast.candidates), chat.fast.timeout_ms),
        str(Tier.STANDARD): TierPlan(
            tuple(chat.standard.candidates), chat.standard.timeout_ms
        ),
        str(Tier.DEEP): TierPlan(tuple(chat.deep.candidates), chat.deep.timeout_ms),
    }
    chat_selector = ModelSelector(
        chat_candidates,
        tiers,
        health_store=health,
        configured_providers=configured,
    )
    llm = RoutingLLMService(
        chat_selector, health, _build_clients(settings, http, configured, _CHAT_CLIENT_CLASSES)
    )

    embedding_candidates = [
        ModelCandidate(
            id=candidate.resolved_id,
            provider=candidate.provider,
            model=candidate.model,
            url=candidate.url,
            dimension=candidate.dimension,
            priority=candidate.priority,
            enabled=candidate.enabled,
        )
        for candidate in settings.ai.embedding.candidates
        if candidate.provider in configured
    ]
    embedding_selector = ModelSelector({}, {}, health_store=health)
    embedding = RoutingEmbeddingService(
        embedding_selector,
        health,
        _build_clients(settings, http, configured, _EMBEDDING_CLIENT_CLASSES),
        embedding_candidates,
        settings.ai.embedding.default_model,
    )
    rerank_candidates = [
        ModelCandidate(
            id=candidate.resolved_id,
            provider=candidate.provider,
            model=candidate.model,
            url=candidate.url,
            priority=candidate.priority,
            enabled=candidate.enabled,
        )
        for candidate in settings.ai.rerank.candidates
        if candidate.provider == ModelProvider.NOOP
        or candidate.provider in configured
    ]
    rerank_clients = {str(ModelProvider.NOOP): NoopRerankClient()}
    if str(ModelProvider.BAILIAN) in configured:
        provider = settings.ai.providers.bailian
        rerank_clients[str(ModelProvider.BAILIAN)] = BaiLianRerankClient(
            http, provider.url, provider.api_key, provider.endpoints
        )
    rerank = RoutingRerankService(
        ModelSelector({}, {}, health_store=health),
        health,
        rerank_clients,
        rerank_candidates,
        settings.ai.rerank.default_model,
    )
    return ModelRuntime(
        llm=llm,
        embedding=embedding,
        rerank=rerank,
        health=health,
        http=http,
    )
