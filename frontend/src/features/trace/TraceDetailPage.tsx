import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Clipboard, Clock3, DatabaseZap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { toast } from "sonner";

import { getTraceDetail } from "@/features/trace/api";
import { formatDuration, formatTraceTime, shortTraceId } from "@/features/trace/format";
import { JsonTree } from "@/features/trace/JsonTree";
import { TraceStatusBadge } from "@/features/trace/TraceStatusBadge";
import { Button } from "@/shared/ui/Button";

export function TraceDetailPage() {
  const { traceId = "" } = useParams();
  const location = useLocation();
  const returnSearch = (location.state as { from?: string } | null)?.from || "";
  const query = useQuery({
    queryKey: ["trace-detail", traceId],
    queryFn: () => getTraceDetail(traceId),
    enabled: Boolean(traceId),
  });
  const [activeNodeId, setActiveNodeId] = useState<string>();
  const nodes = useMemo(() => query.data?.nodes || [], [query.data?.nodes]);
  const activeNode = nodes.find((node) => node.nodeId === activeNodeId) || nodes[0];
  const longestNodeId = nodes.reduce(
    (current, node) => (!current || node.durationMs > current.durationMs ? node : current),
    undefined as (typeof nodes)[number] | undefined,
  )?.nodeId;

  useEffect(() => {
    setActiveNodeId((id) =>
      id && nodes.some((node) => node.nodeId === id) ? id : nodes[0]?.nodeId,
    );
  }, [nodes]);

  const copy = async (label: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(`${label}已复制`);
    } catch {
      toast.error("复制失败，请手动选择");
    }
  };

  if (query.isLoading) {
    return (
      <div className="session-loading console-route-loading">
        <span />
        <p>正在读取 Trace 详情…</p>
      </div>
    );
  }
  if (query.isError) {
    return (
      <main className="console-content">
        <div className="console-table-state console-table-state--error">
          {query.error instanceof Error ? query.error.message : "Trace 详情加载失败"}
        </div>
      </main>
    );
  }
  if (!query.data) {
    return (
      <main className="console-content">
        <Link className="console-back-link" to={`/admin/traces${returnSearch}`}>
          <ArrowLeft /> 返回 Trace 列表
        </Link>
        <div className="console-empty-state">
          <Clock3 />
          <strong>Trace 不存在</strong>
          <p>记录可能已被清理，或 Trace ID 不正确。</p>
        </div>
      </main>
    );
  }

  const { run } = query.data;
  return (
    <main className="console-content trace-detail-page">
      <Link className="console-back-link" to={`/admin/traces${returnSearch}`}>
        <ArrowLeft aria-hidden="true" /> 返回 Trace 列表
      </Link>

      <header className="trace-detail-overview">
        <div>
          <TraceStatusBadge status={run.status} />
          <h1>{run.question || "未记录问题"}</h1>
          <p>{run.entryPoint}</p>
        </div>
        <div className="trace-total-duration">
          <span>总耗时</span>
          <strong>{formatDuration(run.durationMs)}</strong>
        </div>
      </header>

      {run.errorMessage && (
        <div className="trace-run-error">
          <strong>运行异常</strong>
          <span>{run.errorMessage}</span>
        </div>
      )}

      <dl className="trace-run-metadata">
        <div>
          <dt>Trace ID</dt>
          <dd>
            <code>{shortTraceId(run.traceId)}</code>
            <button
              type="button"
              aria-label="复制当前 Trace ID"
              onClick={() => void copy("Trace ID", run.traceId)}
            >
              <Clipboard />
            </button>
          </dd>
        </div>
        <div>
          <dt>会话 ID</dt>
          <dd>
            <code title={run.conversationId}>{shortTraceId(run.conversationId)}</code>
          </dd>
        </div>
        <div>
          <dt>任务 ID</dt>
          <dd>
            <code title={run.taskId}>{shortTraceId(run.taskId)}</code>
          </dd>
        </div>
        <div>
          <dt>用户 ID</dt>
          <dd>{run.userId}</dd>
        </div>
        <div>
          <dt>开始时间</dt>
          <dd>{formatTraceTime(run.startTime)}</dd>
        </div>
        <div>
          <dt>结束时间</dt>
          <dd>{formatTraceTime(run.endTime)}</dd>
        </div>
      </dl>

      <section className="trace-detail-workbench">
        <div className="trace-node-panel">
          <header>
            <div>
              <strong>运行节点</strong>
              <span>按后端记录顺序排列</span>
            </div>
            <small>{nodes.length} 个节点</small>
          </header>
          {nodes.length ? (
            <ol className="trace-node-list">
              {nodes.map((node, index) => (
                <li
                  key={node.nodeId}
                  className={node.nodeId === activeNode?.nodeId ? "is-active" : ""}
                >
                  <button type="button" onClick={() => setActiveNodeId(node.nodeId)}>
                    <span
                      className={`trace-node-marker trace-node-marker--${node.status.toLowerCase()}`}
                    >
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span className="trace-node-copy">
                      <strong>{node.nodeName}</strong>
                      <small>{node.nodeType}</small>
                    </span>
                    <span className="trace-node-time">
                      {node.nodeId === longestNodeId && nodes.length > 1 && <i>最慢</i>}
                      <strong>{formatDuration(node.durationMs)}</strong>
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          ) : (
            <div className="trace-node-empty">
              <DatabaseZap aria-hidden="true" />
              <strong>没有节点记录</strong>
              <span>本次运行没有写入可检查的管线节点。</span>
            </div>
          )}
        </div>

        <aside className="trace-node-inspector">
          {activeNode ? (
            <>
              <header>
                <div>
                  <TraceStatusBadge status={activeNode.status} />
                  <h2>{activeNode.nodeName}</h2>
                  <code>{activeNode.nodeType}</code>
                </div>
                <strong>{formatDuration(activeNode.durationMs)}</strong>
              </header>
              <div className="trace-inspector-toolbar">
                <span>节点输出</span>
                <Button
                  variant="ghost"
                  onClick={() =>
                    void copy("节点数据", JSON.stringify(activeNode.extraData || {}, null, 2))
                  }
                >
                  <Clipboard /> 复制 JSON
                </Button>
              </div>
              <JsonTree value={activeNode.extraData} />
            </>
          ) : (
            <div className="trace-node-empty">
              <span>选择节点后查看输出数据。</span>
            </div>
          )}
        </aside>
      </section>
    </main>
  );
}
