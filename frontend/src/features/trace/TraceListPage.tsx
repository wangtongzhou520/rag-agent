import { useQuery } from "@tanstack/react-query";
import { Activity, Clipboard, Eye, RefreshCw, Search } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { listTraceRuns } from "@/features/trace/api";
import { formatDuration, formatTraceTime, shortTraceId } from "@/features/trace/format";
import { TraceStatusBadge } from "@/features/trace/TraceStatusBadge";
import type { TraceFilters } from "@/features/trace/types";
import { Button } from "@/shared/ui/Button";
import { Input } from "@/shared/ui/Input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/shared/ui/Table";

const PAGE_SIZE = 20;
const emptyFilters: TraceFilters = { traceId: "", conversationId: "", taskId: "", status: "" };

function readPage(value: string | null) {
  const page = Number(value);
  return Number.isInteger(page) && page > 0 ? page : 1;
}

function readFilters(params: URLSearchParams): TraceFilters {
  return {
    traceId: params.get("traceId") || "",
    conversationId: params.get("conversationId") || "",
    taskId: params.get("taskId") || "",
    status: params.get("status") || "",
  };
}

export function TraceListPage() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const page = readPage(searchParams.get("page"));
  const filters = readFilters(searchParams);
  const [draft, setDraft] = useState(filters);

  useEffect(() => {
    setDraft(filters);
    // Individual URL fields are stable dependencies; the derived object is intentionally omitted.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.traceId, filters.conversationId, filters.taskId, filters.status]);

  const query = useQuery({
    queryKey: [
      "trace-runs",
      page,
      filters.traceId,
      filters.conversationId,
      filters.taskId,
      filters.status,
    ],
    queryFn: () => listTraceRuns(page, PAGE_SIZE, filters),
  });
  const pageStats = useMemo(() => {
    const records = query.data?.records || [];
    const completed = records.filter((item) => item.durationMs != null);
    const average = completed.length
      ? Math.round(
          completed.reduce((sum, item) => sum + (item.durationMs || 0), 0) / completed.length,
        )
      : null;
    return {
      visible: records.length,
      success: records.filter((item) => item.status === "SUCCESS").length,
      errors: records.filter((item) => item.status === "ERROR").length,
      average,
    };
  }, [query.data?.records]);

  const updateLocation = (nextPage: number, nextFilters = filters) => {
    const next = new URLSearchParams();
    Object.entries(nextFilters).forEach(([key, value]) => {
      const normalized = value.trim();
      if (normalized) next.set(key, normalized);
    });
    if (nextPage > 1) next.set("page", String(nextPage));
    setSearchParams(next);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    updateLocation(1, draft);
  };
  const clear = () => {
    setDraft(emptyFilters);
    updateLocation(1, emptyFilters);
  };
  const copyId = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      toast.success("Trace ID 已复制");
    } catch {
      toast.error("复制失败，请手动选择");
    }
  };

  return (
    <main className="console-content trace-page">
      <header className="console-page-header">
        <div className="console-page-heading">
          <p>运行观测</p>
          <h1>RAG Trace</h1>
          <span>定位一次问答的执行状态、总耗时和检索节点输出。</span>
        </div>
        <Button variant="secondary" onClick={() => void query.refetch()}>
          <RefreshCw aria-hidden="true" /> 刷新
        </Button>
      </header>

      <form className="trace-filter-panel" onSubmit={submit}>
        <label>
          <span>Trace ID</span>
          <Input
            aria-label="Trace ID"
            value={draft.traceId}
            onChange={(event) => setDraft({ ...draft, traceId: event.target.value })}
            placeholder="输入完整 UUID"
          />
        </label>
        <label>
          <span>会话 ID</span>
          <Input
            aria-label="会话 ID"
            value={draft.conversationId}
            onChange={(event) => setDraft({ ...draft, conversationId: event.target.value })}
            placeholder="输入完整 UUID"
          />
        </label>
        <label>
          <span>任务 ID</span>
          <Input
            aria-label="任务 ID"
            value={draft.taskId}
            onChange={(event) => setDraft({ ...draft, taskId: event.target.value })}
            placeholder="输入完整 UUID"
          />
        </label>
        <label>
          <span>运行状态</span>
          <select
            aria-label="运行状态"
            value={draft.status}
            onChange={(event) => setDraft({ ...draft, status: event.target.value })}
          >
            <option value="">全部状态</option>
            <option value="SUCCESS">成功</option>
            <option value="RUNNING">运行中</option>
            <option value="ERROR">异常</option>
          </select>
        </label>
        <div className="trace-filter-actions">
          <Button type="submit">
            <Search aria-hidden="true" /> 查询
          </Button>
          <Button type="button" variant="ghost" onClick={clear}>
            重置
          </Button>
        </div>
      </form>

      <section className="trace-page-summary" aria-label="当前页概况">
        <span>当前页 {pageStats.visible} 条</span>
        <span>成功 {pageStats.success}</span>
        <span>异常 {pageStats.errors}</span>
        <span>平均耗时 {formatDuration(pageStats.average)}</span>
        <small>统计口径仅为当前页</small>
      </section>

      <section className="knowledge-table-panel trace-table-panel">
        {query.isLoading ? (
          <div className="console-table-state">正在读取 Trace 记录…</div>
        ) : query.isError ? (
          <div className="console-table-state console-table-state--error">
            {query.error instanceof Error ? query.error.message : "Trace 记录加载失败"}
          </div>
        ) : query.data?.records.length === 0 ? (
          <div className="console-empty-state">
            <Activity aria-hidden="true" />
            <strong>没有匹配的 Trace 记录</strong>
            <p>完成一次问答后，运行记录会显示在这里。</p>
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>问题</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>总耗时</TableHead>
                  <TableHead>用户 ID</TableHead>
                  <TableHead>开始时间</TableHead>
                  <TableHead>Trace ID</TableHead>
                  <TableHead className="w-[78px] text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.data?.records.map((item) => (
                  <TableRow key={item.traceId}>
                    <TableCell>
                      <div className="trace-question-cell">
                        <strong title={item.question || undefined}>
                          {item.question || "未记录问题"}
                        </strong>
                        <small>{item.traceName}</small>
                      </div>
                    </TableCell>
                    <TableCell>
                      <TraceStatusBadge status={item.status} />
                    </TableCell>
                    <TableCell>
                      <span className="trace-duration">{formatDuration(item.durationMs)}</span>
                    </TableCell>
                    <TableCell>{item.userId}</TableCell>
                    <TableCell>
                      <time>{formatTraceTime(item.startTime)}</time>
                    </TableCell>
                    <TableCell>
                      <div className="trace-id-cell">
                        <code title={item.traceId}>{shortTraceId(item.traceId)}</code>
                        <button
                          type="button"
                          aria-label={`复制 Trace ID ${item.traceId}`}
                          onClick={() => void copyId(item.traceId)}
                        >
                          <Clipboard aria-hidden="true" />
                        </button>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="table-actions">
                        <Button
                          asChild
                          variant="ghost"
                          className="table-icon-link"
                          aria-label={`查看 Trace ${item.traceId}`}
                        >
                          <Link
                            to={`/admin/traces/${item.traceId}`}
                            state={{ from: location.search }}
                          >
                            <Eye aria-hidden="true" />
                          </Link>
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <footer className="console-pagination">
              <span>共 {query.data?.total || 0} 条 Trace</span>
              <div>
                <Button
                  variant="ghost"
                  disabled={page <= 1}
                  onClick={() => updateLocation(page - 1)}
                >
                  上一页
                </Button>
                <span>
                  {page} / {query.data?.pages || 1}
                </span>
                <Button
                  variant="ghost"
                  disabled={page >= (query.data?.pages || 1)}
                  onClick={() => updateLocation(page + 1)}
                >
                  下一页
                </Button>
              </div>
            </footer>
          </>
        )}
      </section>
    </main>
  );
}
