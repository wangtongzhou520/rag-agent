import { useQuery } from "@tanstack/react-query";
import {
  Database,
  KeyRound,
  Layers3,
  RefreshCw,
  Route,
  ServerCog,
  Settings2,
  ShieldCheck,
} from "lucide-react";
import { useMemo, useState } from "react";

import { getRuntimeSettings } from "@/features/runtime/api";
import type { ModelAvailability, ModelCandidate } from "@/features/runtime/types";
import { Button } from "@/shared/ui/Button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/shared/ui/Table";

import "@/features/runtime/RuntimeSettingsPage.css";

type Capability = "chat" | "embedding" | "rerank";

const availabilityNames: Record<ModelAvailability, string> = {
  ready: "可调用",
  disabled: "已停用",
  unconfigured: "Provider 未配置",
  circuit_open: "熔断中",
  probing: "探测中",
};

const tierNames: Record<string, string> = {
  fast: "快速档",
  standard: "标准档",
  deep: "深度档",
};

export function RuntimeSettingsPage() {
  const [capability, setCapability] = useState<Capability>("chat");
  const query = useQuery({ queryKey: ["runtime-settings"], queryFn: getRuntimeSettings });
  const settings = query.data;
  const candidates = useMemo(() => {
    if (!settings) return [];
    return settings.ai[capability].candidates;
  }, [capability, settings]);
  const allCandidates = settings
    ? [
        ...settings.ai.chat.candidates,
        ...settings.ai.embedding.candidates,
        ...settings.ai.rerank.candidates,
      ]
    : [];
  const readyCount = allCandidates.filter((item) => item.availability === "ready").length;
  const externalProviders = settings
    ? Object.entries(settings.ai.providers).filter(([name]) => name !== "noop")
    : [];
  const configuredProviders = externalProviders.filter(([, item]) => item.configured).length;
  const circuitCount = allCandidates.filter((item) => item.availability === "circuit_open").length;

  return (
    <main className="console-content runtime-page">
      <header className="console-page-header runtime-page-header">
        <div className="console-page-heading">
          <p>运行登记册</p>
          <h1>运行时与模型设置</h1>
          <span>核对当前进程实际加载的模型路由、熔断状态和检索参数，敏感配置仅脱敏展示。</span>
        </div>
        <Button variant="secondary" onClick={() => void query.refetch()}>
          <RefreshCw aria-hidden="true" /> 刷新快照
        </Button>
      </header>

      {query.isLoading ? (
        <RuntimeState text="正在读取运行时快照…" />
      ) : query.isError || !settings ? (
        <RuntimeState
          error
          text={query.error instanceof Error ? query.error.message : "运行时设置加载失败"}
        />
      ) : (
        <>
          <section className="runtime-summary-strip">
            <SummaryItem icon={Route} label="执行架构" value={settings.engine.type} />
            <SummaryItem
              icon={Database}
              label="向量后端"
              value={settings.backends.vector.type}
            />
            <SummaryItem
              icon={ServerCog}
              label="Provider"
              value={`${configuredProviders} / ${externalProviders.length}`}
            />
            <SummaryItem icon={ShieldCheck} label="可调用模型" value={String(readyCount)} />
            <p className={circuitCount ? "warning" : ""}>
              {circuitCount
                ? `${circuitCount} 个模型处于熔断窗口，请查看模型登记册。`
                : "当前没有模型处于熔断窗口。配置来自环境变量、application.yaml 与默认值。"}
            </p>
          </section>

          <section className="runtime-tier-panel">
            <header>
              <div>
                <Route aria-hidden="true" />
                <h2>Chat 路由档位</h2>
              </div>
              <span>候选顺序即失败切换顺序</span>
            </header>
            <div className="runtime-tier-list">
              {Object.entries(settings.ai.chat.tiers).map(([name, tier]) => (
                <article key={name}>
                  <div className="runtime-tier-name">
                    <strong>{tierNames[name] || name}</strong>
                    <span>{formatDuration(tier.timeoutMs)} 超时预算</span>
                  </div>
                  <div className="runtime-candidate-chain">
                    {tier.candidates.map((id, index) => {
                      const candidate = settings.ai.chat.candidates.find(
                        (item) => item.id === id,
                      );
                      return (
                        <div
                          className={candidate?.availability === "ready" ? "ready" : "unavailable"}
                          key={id}
                        >
                          <i>{index + 1}</i>
                          <span>{id}</span>
                          <small>{candidate ? availabilityNames[candidate.availability] : "未注册"}</small>
                        </div>
                      );
                    })}
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="runtime-model-panel">
            <header>
              <div>
                <Layers3 aria-hidden="true" />
                <h2>模型登记册</h2>
              </div>
              <nav aria-label="模型能力">
                {(["chat", "embedding", "rerank"] as Capability[]).map((item) => (
                  <button
                    className={capability === item ? "active" : ""}
                    key={item}
                    onClick={() => setCapability(item)}
                  >
                    {capabilityName(item)}
                  </button>
                ))}
              </nav>
            </header>
            <div className="runtime-model-table">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>模型</TableHead>
                    <TableHead>Provider</TableHead>
                    <TableHead>路由位置</TableHead>
                    <TableHead>能力约束</TableHead>
                    <TableHead>运行状态</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {candidates.map((candidate) => (
                    <TableRow key={candidate.id}>
                      <TableCell>
                        <div className="runtime-model-name">
                          <strong>{candidate.id}</strong>
                          <code>{candidate.model}</code>
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className="runtime-provider-code">{candidate.provider}</span>
                      </TableCell>
                      <TableCell>{routePosition(candidate, capability)}</TableCell>
                      <TableCell>{capabilityConstraint(candidate, capability)}</TableCell>
                      <TableCell>
                        <div className={`runtime-health state-${candidate.availability}`}>
                          <span />
                          <div>
                            <strong>{availabilityNames[candidate.availability]}</strong>
                            <small>{healthDetail(candidate)}</small>
                          </div>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </section>

          <div className="runtime-lower-grid">
            <section className="runtime-provider-panel">
              <header>
                <div>
                  <KeyRound aria-hidden="true" />
                  <h2>Provider 连接</h2>
                </div>
                <span>凭据仅显示脱敏片段</span>
              </header>
              <div>
                {Object.entries(settings.ai.providers).map(([name, provider]) => (
                  <article key={name}>
                    <span className={provider.configured ? "configured" : ""} />
                    <div>
                      <strong>{name}</strong>
                      <code>{provider.url || "本地内置执行器"}</code>
                    </div>
                    <div>
                      <small>{Object.keys(provider.endpoints).join(" · ") || "无需端点"}</small>
                      <em>{provider.apiKey || (name === "ollama" || name === "noop" ? "无需密钥" : "未配置")}</em>
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section className="runtime-parameter-panel">
              <header>
                <div>
                  <Settings2 aria-hidden="true" />
                  <h2>检索与韧性参数</h2>
                </div>
                <span>当前进程有效值</span>
              </header>
              <dl>
                <Parameter label="向量维度" value={settings.rag.default.dimension} />
                <Parameter label="最终 TopK" value={settings.rag.default.topK} />
                <Parameter label="召回预算" value={settings.rag.search.recallBudget} />
                <Parameter label="Rerank 候选" value={settings.rag.search.rerankCandidateLimit} />
                <Parameter label="Rerank 最低分" value={settings.rag.search.rerankMinScore.toFixed(2)} />
                <Parameter label="检索超时" value={formatDuration(settings.rag.search.retrievalTimeoutMs)} />
                <Parameter label="RRF K" value={settings.rag.search.fusion.rrfK} />
                <Parameter label="熔断阈值" value={`${settings.ai.selection.failureThreshold} 次`} />
                <Parameter label="熔断窗口" value={formatDuration(settings.ai.selection.openDurationMs)} />
                <Parameter label="记忆轮数" value={settings.rag.memory.historyKeepTurns} />
                <Parameter label="流式分片" value={`${settings.ai.stream.messageChunkSize} 字`} />
              </dl>
              <footer>
                此页面只读。修改环境变量或 YAML 后需重启 API，页面才会反映新的运行值。
              </footer>
            </section>
          </div>
        </>
      )}
    </main>
  );
}

function SummaryItem({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Route;
  label: string;
  value: string;
}) {
  return (
    <div>
      <Icon aria-hidden="true" />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Parameter({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function RuntimeState({ text, error = false }: { text: string; error?: boolean }) {
  return <div className={`runtime-state${error ? " error" : ""}`}>{text}</div>;
}

function capabilityName(capability: Capability) {
  return { chat: "Chat", embedding: "Embedding", rerank: "Rerank" }[capability];
}

function routePosition(candidate: ModelCandidate, capability: Capability) {
  if (capability === "chat") {
    return candidate.tiers?.map((tier) => tierNames[tier] || tier).join("、") || "未进入档位";
  }
  return candidate.isDefault ? "默认模型" : `优先级 ${candidate.priority ?? "—"}`;
}

function capabilityConstraint(candidate: ModelCandidate, capability: Capability) {
  if (capability === "embedding") return candidate.dimension ? `${candidate.dimension} 维` : "维度未声明";
  if (capability === "chat") return candidate.supportsThinking ? "支持深度思考" : "普通生成";
  return candidate.provider === "noop" ? "不改变候选顺序" : "相关性重排";
}

function healthDetail(candidate: ModelCandidate) {
  if (candidate.availability === "circuit_open") {
    return `${Math.ceil(candidate.health.retryAfterMs / 1000)} 秒后允许探测`;
  }
  if (candidate.availability === "unconfigured") return "连接配置不完整";
  if (candidate.availability === "disabled") return "配置中 enabled=false";
  if (candidate.availability === "probing") return "已有请求占用探测名额";
  return candidate.health.consecutiveFailures
    ? `连续失败 ${candidate.health.consecutiveFailures} 次`
    : "熔断器关闭";
}

function formatDuration(milliseconds: number) {
  if (milliseconds >= 1000 && milliseconds % 1000 === 0) return `${milliseconds / 1000} s`;
  return `${milliseconds} ms`;
}
