import { useMutation } from "@tanstack/react-query";
import {
  ArrowRight,
  BookOpenCheck,
  Braces,
  Clock3,
  FileSearch,
  FlaskConical,
  Route,
  TerminalSquare,
} from "lucide-react";
import { useState, type FormEvent } from "react";

import { evaluateQuestion } from "@/features/eval/api";
import { formatEvalLatency, routeLabel } from "@/features/eval/format";
import { Button } from "@/shared/ui/Button";

import "@/features/eval/EvalPage.css";

const EXAMPLES = [
  "员工每年有多少天带薪年假？",
  "非一线城市出差住宿每晚上限是多少？",
  "P0 故障发生后多久要建立应急沟通群？",
];

export function EvalPage() {
  const [question, setQuestion] = useState(EXAMPLES[0]);
  const mutation = useMutation({ mutationFn: evaluateQuestion });
  const result = mutation.data;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const normalized = question.trim();
    if (normalized) mutation.mutate(normalized);
  };

  return (
    <main className="console-content eval-page">
      <header className="console-page-header eval-page-header">
        <div className="console-page-heading">
          <p>QUALITY WORKBENCH / M5</p>
          <h1>检索质量实验台</h1>
          <span>隔离回答生成，只观察问题改写、意图路由与最终证据。</span>
        </div>
        <div className="eval-version-stamp">
          <FlaskConical aria-hidden="true" />
          <span>DATASET</span>
          <strong>rag_quality.v2</strong>
        </div>
      </header>

      <section className="eval-workbench">
        <form className="eval-query-panel" onSubmit={submit}>
          <div className="eval-panel-index">01 / PROBE</div>
          <label htmlFor="eval-question">验证一个真实问题</label>
          <textarea
            id="eval-question"
            maxLength={1000}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="输入需要检查召回质量的问题…"
          />
          <div className="eval-query-meta">
            <span>{question.length} / 1000</span>
            <span>不生成最终答案</span>
          </div>
          <div className="eval-examples" aria-label="基准问题示例">
            {EXAMPLES.map((example, index) => (
              <button key={example} type="button" onClick={() => setQuestion(example)}>
                <i>0{index + 1}</i>
                {example}
              </button>
            ))}
          </div>
          <Button type="submit" disabled={!question.trim() || mutation.isPending}>
            {mutation.isPending ? "正在穿过检索链路…" : "运行单题评测"}
            {!mutation.isPending && <ArrowRight aria-hidden="true" />}
          </Button>
          {mutation.isError && (
            <div className="eval-inline-error" role="alert">
              <strong>评测接口不可用</strong>
              <span>
                {mutation.error instanceof Error
                  ? mutation.error.message
                  : "请确认后端已启动且 eval.enabled=true。"}
              </span>
            </div>
          )}
        </form>

        <aside className="eval-method-panel">
          <div className="eval-panel-index">02 / METHOD</div>
          <h2>固定评测口径</h2>
          <ol>
            <li>
              <span>R</span>
              <div>
                <strong>Rewrite</strong>
                <small>空会话历史改写与拆分</small>
              </div>
            </li>
            <li>
              <span>I</span>
              <div>
                <strong>Intent</strong>
                <small>记录每个子问题 Top-1 叶子</small>
              </div>
            </li>
            <li>
              <span>K</span>
              <div>
                <strong>Retrieve</strong>
                <small>最终 Chunk、文档和上下文</small>
              </div>
            </li>
          </ol>
          <div className="eval-cli-note">
            <TerminalSquare aria-hidden="true" />
            <div>
              <span>批量回归</span>
              <code>uv run python -m scripts.evaluate_rag</code>
            </div>
          </div>
        </aside>
      </section>

      {!result && !mutation.isPending ? (
        <section className="eval-empty-board">
          <div>
            <FileSearch aria-hidden="true" />
          </div>
          <strong>等待一次检索探测</strong>
          <p>运行后，这里会展开路由、文档命中、Chunk 证据和耗时。</p>
          <span>NO RESULT / READY</span>
        </section>
      ) : mutation.isPending ? (
        <section className="eval-loading-board" aria-live="polite">
          <span />
          <p>正在执行 Rewrite → Intent → Retrieve</p>
        </section>
      ) : result ? (
        <section className="eval-result-board">
          <div className="eval-metric-strip">
            <Metric icon={Clock3} label="端到端耗时" value={formatEvalLatency(result.latencyMs)} />
            <Metric
              icon={BookOpenCheck}
              label="命中文档"
              value={String(result.retrievedDocIds.length)}
            />
            <Metric
              icon={Braces}
              label="最终 Chunk"
              value={String(result.retrievedChunkIds.length)}
            />
            <Metric icon={Route} label="证据路由" value={routeLabel(result)} wide />
          </div>

          <div className="eval-result-grid">
            <article className="eval-evidence-panel">
              <header>
                <div>
                  <span>03</span>
                  <h2>证据切片</h2>
                </div>
                <small>{result.retrievedContexts.length} 个上下文</small>
              </header>
              {result.retrievedContexts.length ? (
                <div className="eval-context-list">
                  {result.retrievedContexts.map((context, index) => (
                    <section key={result.retrievedChunkIds[index] || index}>
                      <header>
                        <span>CHUNK {String(index + 1).padStart(2, "0")}</span>
                        <div>
                          <b>{result.retrievedScores[index]?.toFixed(4) ?? "—"}</b>
                          <code>{result.retrievedContextDocIds[index] || "未映射文档"}</code>
                        </div>
                      </header>
                      <p>{context}</p>
                      <small>{result.retrievedChunkIds[index]}</small>
                    </section>
                  ))}
                </div>
              ) : (
                <div className="eval-panel-empty">本次没有返回知识库 Chunk。</div>
              )}
            </article>

            <aside className="eval-route-panel">
              <header>
                <span>04</span>
                <h2>链路判读</h2>
              </header>
              <dl>
                <div>
                  <dt>改写拆分</dt>
                  <dd>{result.subIntents.length}</dd>
                </div>
                <div>
                  <dt>KB 证据</dt>
                  <dd>{result.hasKb ? "YES" : "NO"}</dd>
                </div>
                <div>
                  <dt>MCP 成功</dt>
                  <dd>{result.hasMcpSuccess ? "YES" : "NO"}</dd>
                </div>
                <div>
                  <dt>需要补参</dt>
                  <dd>{result.needsClarification ? "YES" : "NO"}</dd>
                </div>
                <div>
                  <dt>MCP 失败</dt>
                  <dd>{result.hasMcpFailure ? "YES" : "NO"}</dd>
                </div>
              </dl>
              {result.retrievedDocIds.length > 0 && (
                <div className="eval-doc-list">
                  <span>RETRIEVED DOCS</span>
                  <div>
                    {result.retrievedDocIds.map((docId) => (
                      <code key={docId}>{docId}</code>
                    ))}
                  </div>
                </div>
              )}
              <div className="eval-intent-list">
                <span>SUB-INTENTS / TOP-1</span>
                {result.subIntents.map((intent, index) => (
                  <div key={`${intent}-${index}`}>
                    <i>{index + 1}</i>
                    <p>{intent}</p>
                    <code>{result.intentLeafIds[index] || "NO MATCH"}</code>
                  </div>
                ))}
              </div>
              {result.mcpContext && (
                <div className="eval-mcp-output">
                  <span>MCP CONTEXT</span>
                  <pre>{result.mcpContext}</pre>
                </div>
              )}
            </aside>
          </div>
        </section>
      ) : null}
    </main>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
  wide = false,
}: {
  icon: typeof Clock3;
  label: string;
  value: string;
  wide?: boolean;
}) {
  return (
    <div className={wide ? "wide" : undefined}>
      <Icon aria-hidden="true" />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
