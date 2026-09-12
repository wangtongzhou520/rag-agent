import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  BookOpenCheck,
  Braces,
  CheckCircle2,
  Clock3,
  FileSearch,
  FlaskConical,
  History,
  MessageSquareText,
  RefreshCw,
  Route,
  TerminalSquare,
  XCircle,
} from "lucide-react";
import { useState, type FormEvent } from "react";

import { evaluateQuestion, getEvalReport, listEvalReports } from "@/features/eval/api";
import { formatEvalLatency, routeLabel } from "@/features/eval/format";
import type { EvalReportSummary } from "@/features/eval/types";
import { formatTraceTime } from "@/features/trace/format";
import { Button } from "@/shared/ui/Button";

import "@/features/eval/EvalPage.css";

const EXAMPLES = [
  "员工每年有多少天带薪年假？",
  "非一线城市出差住宿每晚上限是多少？",
  "P0 故障发生后多久要建立应急沟通群？",
];

export function EvalPage() {
  const [question, setQuestion] = useState(EXAMPLES[0]);
  const [includeAnswer, setIncludeAnswer] = useState(false);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const mutation = useMutation({ mutationFn: evaluateQuestion });
  const reportsQuery = useQuery({
    queryKey: ["eval-reports"],
    queryFn: () => listEvalReports(),
    retry: false,
  });
  const reportQuery = useQuery({
    queryKey: ["eval-report", selectedReportId],
    queryFn: () => getEvalReport(selectedReportId!),
    enabled: Boolean(selectedReportId),
    retry: false,
  });
  const result = mutation.data;
  const reports = reportsQuery.data?.records ?? [];

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const normalized = question.trim();
    if (normalized) mutation.mutate({ question: normalized, includeAnswer });
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
          <strong>rag_quality.v3</strong>
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
          <label className="eval-answer-option">
            <input
              type="checkbox"
              checked={includeAnswer}
              onChange={(event) => setIncludeAnswer(event.target.checked)}
            />
            <div>
              <strong>同时生成答案</strong>
              <small>额外调用 Chat 模型，不写入会话记录</small>
            </div>
          </label>
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

      <section className="eval-history-board" aria-labelledby="eval-history-title">
        <header>
          <div>
            <History aria-hidden="true" />
            <div>
              <span>BATCH ARCHIVE</span>
              <h2 id="eval-history-title">批次评测记录</h2>
            </div>
          </div>
          <Button
            variant="secondary"
            onClick={() => reportsQuery.refetch()}
            disabled={reportsQuery.isFetching}
          >
            <RefreshCw aria-hidden="true" />
            刷新
          </Button>
        </header>

        {reports.length ? (
          <div className="eval-history-layout">
            <div className="eval-report-list">
              {reports.map((report, index) => (
                <button
                  key={report.reportId}
                  type="button"
                  className={selectedReportId === report.reportId ? "is-selected" : undefined}
                  onClick={() => setSelectedReportId(report.reportId)}
                >
                  <span className="eval-report-sequence">
                    {String(reports.length - index).padStart(2, "0")}
                  </span>
                  <div className="eval-report-identity">
                    <strong>{report.label || datasetName(report.dataset)}</strong>
                    <small>{formatTraceTime(report.createTime)}</small>
                  </div>
                  <ReportMetric
                    label={
                      report.summary.unanswerableAbstentionRate != null ? "拒答率" : "命中率"
                    }
                    value={percentage(
                      report.summary.unanswerableAbstentionRate ?? report.summary.docHitRate,
                    )}
                  />
                  <ReportMetric
                    label="上下文精度"
                    value={percentage(report.summary.contextPrecision)}
                    delta={metricDelta(report, reports[index + 1], "contextPrecision")}
                  />
                  <ReportMetric
                    label="P95"
                    value={formatEvalLatency(report.summary.latencyP95Ms ?? 0)}
                  />
                  <span
                    className={
                      report.summary.thresholdsPassed
                        ? "eval-report-state is-pass"
                        : "eval-report-state is-fail"
                    }
                  >
                    {report.summary.thresholdsPassed ? (
                      <CheckCircle2 aria-hidden="true" />
                    ) : (
                      <XCircle aria-hidden="true" />
                    )}
                    {report.summary.thresholdsPassed ? "通过" : "未通过"}
                  </span>
                </button>
              ))}
            </div>

            <aside className="eval-report-detail" aria-live="polite">
              {!selectedReportId ? (
                <div className="eval-report-detail-empty">
                  <span>SELECT A RUN</span>
                  <p>选择左侧批次查看逐题异常和答案指标。</p>
                </div>
              ) : reportQuery.isLoading ? (
                <div className="eval-report-detail-empty">
                  <span>LOADING</span>
                  <p>正在读取批次报告…</p>
                </div>
              ) : reportQuery.data ? (
                <>
                  <header>
                    <div>
                      <span>RUN DETAIL</span>
                      <strong>
                        {reportQuery.data.label || datasetName(reportQuery.data.dataset)}
                      </strong>
                    </div>
                    <code>{reportQuery.data.reportId.slice(0, 8)}</code>
                  </header>
                  <div className="eval-report-answer-metrics">
                    {reportQuery.data.summary.unanswerableAbstentionRate != null ? (
                      <>
                        <ReportMetric
                          label="无证据率"
                          value={percentage(reportQuery.data.summary.unanswerableNoEvidenceRate)}
                        />
                        <ReportMetric
                          label="正确拒答率"
                          value={percentage(reportQuery.data.summary.unanswerableAbstentionRate)}
                        />
                        <ReportMetric
                          label="语义正确性"
                          value={percentage(reportQuery.data.summary.semanticScore)}
                        />
                        <ReportMetric
                          label="回答 P95"
                          value={formatEvalLatency(
                            reportQuery.data.summary.answerLatencyP95Ms ?? 0,
                          )}
                        />
                      </>
                    ) : (
                      <>
                        <ReportMetric label="MRR" value={decimal(reportQuery.data.summary.mrr)} />
                        <ReportMetric
                          label="答案事实覆盖"
                          value={percentage(reportQuery.data.summary.answerKeywordRecall)}
                        />
                        <ReportMetric
                          label="完整答案率"
                          value={percentage(reportQuery.data.summary.answerCompleteRate)}
                        />
                        <ReportMetric
                          label="语义正确性"
                          value={percentage(reportQuery.data.summary.semanticScore)}
                        />
                      </>
                    )}
                  </div>
                  <div className="eval-report-cases">
                    <span>FLAGGED CASES</span>
                    {reportQuery.data.cases.filter(isFlaggedCase).length ? (
                      reportQuery.data.cases
                        .filter(isFlaggedCase)
                        .slice(0, 5)
                        .map((item) => (
                          <div key={item.id}>
                            <code>{item.id}</code>
                            <p>{item.question || "未记录问题"}</p>
                            <small>
                              {item.error || item.semantic_reason || "指标未达到当前门槛"}
                            </small>
                          </div>
                        ))
                    ) : (
                      <p className="eval-report-all-pass">本批次没有失败或语义风险用例。</p>
                    )}
                  </div>
                </>
              ) : (
                <div className="eval-report-detail-empty">
                  <span>UNAVAILABLE</span>
                  <p>报告详情暂时无法读取。</p>
                </div>
              )}
            </aside>
          </div>
        ) : (
          <div className="eval-history-empty">
            <span>{reportsQuery.isLoading ? "正在读取批次记录…" : "尚未发布批量评测报告"}</span>
            <code>scripts.evaluate_rag --publish-report</code>
          </div>
        )}
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

          {result.answer !== null && result.answer !== undefined && (
            <article className="eval-answer-panel">
              <header>
                <div>
                  <MessageSquareText aria-hidden="true" />
                  <span>GROUNDED ANSWER</span>
                </div>
                <small>
                  {result.answerLatencyMs === null || result.answerLatencyMs === undefined
                    ? "生成完成"
                    : formatEvalLatency(result.answerLatencyMs)}
                </small>
              </header>
              <p>{result.answer || "未生成可评测的答案。"}</p>
            </article>
          )}

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

function ReportMetric({
  label,
  value,
  delta,
}: {
  label: string;
  value: string;
  delta?: number | null;
}) {
  return (
    <span className="eval-report-metric">
      <small>{label}</small>
      <strong>{value}</strong>
      {delta != null && delta !== 0 && (
        <i className={delta > 0 ? "is-up" : "is-down"}>
          {delta > 0 ? "+" : ""}
          {(delta * 100).toFixed(1)}pp
        </i>
      )}
    </span>
  );
}

function datasetName(value: string) {
  return (
    value
      .split("/")
      .pop()
      ?.replace(/\.jsonl$/i, "") || value
  );
}

function percentage(value?: number | null) {
  return value == null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function decimal(value?: number | null) {
  return value == null ? "—" : value.toFixed(3);
}

function metricDelta(
  current: EvalReportSummary,
  previous: EvalReportSummary | undefined,
  key: "contextPrecision",
) {
  const currentValue = current.summary[key];
  const previousValue = previous?.summary[key];
  return currentValue == null || previousValue == null ? null : currentValue - previousValue;
}

function isFlaggedCase(item: {
  passed?: boolean;
  semantic_verdict?: "PASS" | "PARTIAL" | "FAIL" | null;
}) {
  return !item.passed || item.semantic_verdict === "PARTIAL" || item.semantic_verdict === "FAIL";
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
