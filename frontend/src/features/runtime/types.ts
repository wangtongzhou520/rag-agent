export type ModelAvailability =
  | "ready"
  | "disabled"
  | "unconfigured"
  | "circuit_open"
  | "probing";

export interface ModelCandidate {
  id: string;
  provider: string;
  model: string;
  enabled: boolean;
  providerConfigured: boolean;
  availability: ModelAvailability;
  health: {
    state: "closed" | "open" | "half_open";
    consecutiveFailures: number;
    retryAfterMs: number;
  };
  url?: string | null;
  priority?: number | null;
  dimension?: number | null;
  supportsThinking?: boolean;
  tiers?: string[];
  isDefault?: boolean;
}

export interface ProviderRuntime {
  url?: string | null;
  apiKey?: string | null;
  configured: boolean;
  endpoints: Record<string, string>;
}

export interface RuntimeSettings {
  readOnly: boolean;
  sourcePriority: string[];
  engine: { type: string };
  backends: {
    vector: { type: string };
    keyword: { type: string };
    graph: { type: string };
  };
  rag: {
    default: { dimension: number; topK: number; sseTimeoutMs: number };
    search: {
      recallBudget: number;
      rerankCandidateLimit: number;
      rerankMinScore: number;
      retrievalTimeoutMs: number;
      queryRewrite: { enabled: boolean; timeoutMs: number };
      scope: {
        minIntentScore: number;
        confidenceThreshold: number;
        supplementRatio: number;
      };
      fusion: {
        strategy: string;
        rrfK: number;
        channelWeights: Record<string, number>;
      };
    };
    memory: { historyKeepTurns: number; titleMaxLength: number };
    rateLimit: { enabled: boolean };
  };
  ai: {
    providers: Record<string, ProviderRuntime>;
    chat: {
      defaultTier: string;
      deepThinkingTier: string;
      tiers: Record<string, { candidates: string[]; timeoutMs: number }>;
      candidates: ModelCandidate[];
    };
    embedding: { defaultModel?: string | null; candidates: ModelCandidate[] };
    rerank: { defaultModel?: string | null; candidates: ModelCandidate[] };
    selection: { failureThreshold: number; openDurationMs: number };
    stream: { messageChunkSize: number };
  };
  storage: { localDir: string };
}
