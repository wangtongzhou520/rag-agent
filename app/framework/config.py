"""应用配置：pydantic-settings 加载 config/application.yaml，支持 RAGENT_ 前缀环境变量覆盖。"""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    InitSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

# 项目根目录（app/framework/config.py -> 上三级）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
YAML_FILE = PROJECT_ROOT / "config" / "application.yaml"


class ServerSettings(BaseModel):
    port: int = 9090
    root_path: str = "/api/ragent"


class DatasourceSettings(BaseModel):
    host: str = "localhost"
    port: int = 5432
    database: str = "ragent"
    username: str = "postgres"
    password: str = ""
    # 新项目起步：启动时自动 CREATE EXTENSION + create_all；测试环境置 false
    auto_ddl: bool = True

    @property
    def url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.username}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


class RedisSettings(BaseModel):
    host: str = "localhost"
    port: int = 6379
    database: int = 0
    password: str = ""
    key_prefix: str = "ragent:"


class AuthSettings(BaseModel):
    """JWT + Redis 会话认证；未配置数据库阶段可保持 disabled。"""

    enabled: bool = False
    jwt_secret: str = ""
    token_ttl_seconds: int = 2_592_000
    header_name: str = "Authorization"
    default_avatar: str = ""
    development_user_id: int = 0


class StorageSettings(BaseModel):
    local_dir: str = "resources/uploads"


class ProviderSettings(BaseModel):
    """单个模型 provider 的连接配置；api_key 留空，用 RAGENT_ 前缀环境变量覆盖。"""

    url: str = ""
    api_key: str = ""
    endpoints: dict[str, str] = {}  # capability（小写）-> 路径


class OllamaProviderSettings(ProviderSettings):
    url: str = "http://localhost:11434"


class AiProvidersSettings(BaseModel):
    """四个 provider 均为可选配置块，缺省即未配置（候选构建时跳过）。"""

    ollama: OllamaProviderSettings = OllamaProviderSettings()
    bailian: ProviderSettings = ProviderSettings()
    siliconflow: ProviderSettings = ProviderSettings()
    aihubmix: ProviderSettings = ProviderSettings()


class ChatCandidateSettings(BaseModel):
    """chat 物理模型注册表项；id 缺省回退 provider::model。"""

    provider: str
    model: str
    id: str | None = None
    url: str | None = None  # 覆盖 provider 拼接
    supports_thinking: bool = False
    enabled: bool = True
    priority: int = 100
    dimension: int | None = None

    @property
    def resolved_id(self) -> str:
        return self.id or f"{self.provider}::{self.model}"


class ChatTierSettings(BaseModel):
    candidates: list[str] = []
    timeout_ms: int = 30000


class ChatSettings(BaseModel):
    candidates: list[ChatCandidateSettings] = []  # 物理模型注册表，不决定顺序
    fast: ChatTierSettings = ChatTierSettings(timeout_ms=5000)
    standard: ChatTierSettings = ChatTierSettings(timeout_ms=30000)
    deep: ChatTierSettings = ChatTierSettings(timeout_ms=120000)


class EmbeddingCandidateSettings(BaseModel):
    """embedding 物理模型注册表项；dimension 须等于 rag.default.dimension（启动校验）。"""

    provider: str
    model: str
    id: str | None = None
    url: str | None = None
    dimension: int | None = None
    priority: int = 100
    enabled: bool = True

    @property
    def resolved_id(self) -> str:
        return self.id or f"{self.provider}::{self.model}"


class EmbeddingSettings(BaseModel):
    default_model: str | None = None  # 置顶候选 id
    candidates: list[EmbeddingCandidateSettings] = []


class CandidateSettings(BaseModel):
    candidates: list[str] = []


class SelectionSettings(BaseModel):
    failure_threshold: int = 2
    open_duration_ms: int = 30000


class AiStreamSettings(BaseModel):
    message_chunk_size: int = 5


class AiSettings(BaseModel):
    providers: AiProvidersSettings = AiProvidersSettings()
    chat: ChatSettings = ChatSettings()
    embedding: EmbeddingSettings = EmbeddingSettings()
    rerank: CandidateSettings = CandidateSettings()
    selection: SelectionSettings = SelectionSettings()
    stream: AiStreamSettings = AiStreamSettings()


class RagDefaultSettings(BaseModel):
    dimension: int = 1536
    top_k: int = 10
    sse_timeout_ms: int = 300000


class ChannelWeights(BaseModel):
    vector: float = 1.0
    keyword: float = 1.0
    graph: float = 0.8
    web: float = 0.5


class FusionSettings(BaseModel):
    rrf_k: int = 20
    channel_weights: ChannelWeights = ChannelWeights()


class ScopeSettings(BaseModel):
    supplement_ratio: float = 0.25


class IntentSettings(BaseModel):
    confidence_threshold: float = 0.6


class BackendTypeSettings(BaseModel):
    type: str = "none"


class EngineSettings(BaseModel):
    type: str = "workflow"


class MemorySettings(BaseModel):
    history_keep_turns: int = 8


class RateLimitSettings(BaseModel):
    enabled: bool = True


class RagSettings(BaseModel):
    default: RagDefaultSettings = RagDefaultSettings()
    recall_budget: int = 20
    fusion: FusionSettings = FusionSettings()
    rerank_candidate_limit: int = 40
    scope: ScopeSettings = ScopeSettings()
    intent: IntentSettings = IntentSettings()
    vector: BackendTypeSettings = BackendTypeSettings(type="pg")
    keyword: BackendTypeSettings = BackendTypeSettings()
    graph: BackendTypeSettings = BackendTypeSettings()
    engine: EngineSettings = EngineSettings()
    memory: MemorySettings = MemorySettings()
    rate_limit: RateLimitSettings = RateLimitSettings()


class LoggingSettings(BaseModel):
    level: str = "INFO"


class Settings(BaseSettings):
    """全局配置根模型。优先级：环境变量(RAGENT_*) > application.yaml > 字段默认值。"""

    model_config = SettingsConfigDict(
        env_prefix="RAGENT_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    server: ServerSettings = ServerSettings()
    datasource: DatasourceSettings = DatasourceSettings()
    redis: RedisSettings = RedisSettings()
    auth: AuthSettings = AuthSettings()
    storage: StorageSettings = StorageSettings()
    ai: AiSettings = AiSettings()
    rag: RagSettings = RagSettings()
    logging: LoggingSettings = LoggingSettings()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Windows 默认 GBK，pydantic-settings 的 YamlConfigSettingsSource 按 locale 读文件会炸，
        # 这里显式用 UTF-8 读 YAML 后包成 InitSettingsSource，优先级：env > yaml > 默认值
        yaml_data: dict = {}
        if YAML_FILE.exists():
            yaml_data = yaml.safe_load(YAML_FILE.read_text(encoding="utf-8")) or {}
        return (
            env_settings,
            InitSettingsSource(settings_cls, yaml_data),
            init_settings,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
