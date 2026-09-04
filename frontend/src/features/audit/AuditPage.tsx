import { useQuery } from "@tanstack/react-query";
import { Eye, FileClock, RefreshCw, Search } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";

import { getAuditLog, listAuditLogs } from "@/features/audit/api";
import { AuditDetailDialog } from "@/features/audit/AuditDetailDialog";
import type { AuditFilters, AuditLog } from "@/features/audit/types";
import { formatTraceTime } from "@/features/trace/format";
import { Button } from "@/shared/ui/Button";
import { Input } from "@/shared/ui/Input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/shared/ui/Table";

const PAGE_SIZE = 20;
const emptyFilters: AuditFilters = {
  bizType: "",
  bizId: "",
  operationType: "",
  operatorName: "",
  success: "",
  beginTime: "",
  endTime: "",
};
const operationNames: Record<string, string> = {
  CREATE: "创建",
  UPDATE: "更新",
  DELETE: "删除",
  ENABLE: "启用",
  DISABLE: "停用",
  RUN: "执行",
};

function readFilters(params: URLSearchParams): AuditFilters {
  return Object.fromEntries(
    Object.keys(emptyFilters).map((key) => [key, params.get(key) || ""]),
  ) as unknown as AuditFilters;
}

function toApiTime(value: string) {
  return value ? `${value.replace("T", " ")}:00` : "";
}

export function AuditPage() {
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number(params.get("page")) || 1);
  const filterSearch = params.toString();
  const filters = useMemo(() => readFilters(new URLSearchParams(filterSearch)), [filterSearch]);
  const [draft, setDraft] = useState(filters);
  const [selected, setSelected] = useState<AuditLog>();
  useEffect(() => setDraft(filters), [filters]);
  const query = useQuery({
    queryKey: ["audit-logs", page, ...Object.values(filters)],
    queryFn: () =>
      listAuditLogs(page, PAGE_SIZE, {
        ...filters,
        beginTime: toApiTime(filters.beginTime),
        endTime: toApiTime(filters.endTime),
      }),
  });
  const updateLocation = (nextPage: number, nextFilters = filters) => {
    const next = new URLSearchParams();
    Object.entries(nextFilters).forEach(([key, value]) => value && next.set(key, value));
    if (nextPage > 1) next.set("page", String(nextPage));
    setParams(next);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    updateLocation(1, draft);
  };
  const openDetail = async (item: AuditLog) => {
    setSelected(item);
    try {
      setSelected(await getAuditLog(item.id));
    } catch {
      /* 列表快照仍可查看 */
    }
  };

  return (
    <main className="console-content audit-page">
      <header className="console-page-header">
        <div className="console-page-heading">
          <p>系统管理</p>
          <h1>审计日志</h1>
          <span>按时间还原业务变更，核对操作人、结果及字段级前后差异。</span>
        </div>
        <Button variant="secondary" onClick={() => void query.refetch()}>
          <RefreshCw aria-hidden="true" /> 刷新
        </Button>
      </header>
      <form className="audit-filter-panel" onSubmit={submit}>
        <label>
          <span>业务类型</span>
          <select
            aria-label="业务类型"
            value={draft.bizType}
            onChange={(event) => setDraft({ ...draft, bizType: event.target.value })}
          >
            <option value="">全部业务</option>
            <option value="USER">用户</option>
            <option value="KNOWLEDGE_BASE">知识库</option>
            <option value="KNOWLEDGE_DOCUMENT">文档</option>
            <option value="KNOWLEDGE_CHUNK">Chunk</option>
            <option value="INTENT_TREE">意图树</option>
            <option value="QUERY_TERM_MAPPING">查询词映射</option>
            <option value="INGESTION_PIPELINE">Pipeline</option>
            <option value="INGESTION_TASK">入库任务</option>
          </select>
        </label>
        <label>
          <span>业务 ID</span>
          <Input
            aria-label="业务 ID"
            value={draft.bizId}
            onChange={(event) => setDraft({ ...draft, bizId: event.target.value })}
            placeholder="支持模糊匹配"
          />
        </label>
        <label>
          <span>操作类型</span>
          <select
            aria-label="操作类型"
            value={draft.operationType}
            onChange={(event) => setDraft({ ...draft, operationType: event.target.value })}
          >
            <option value="">全部操作</option>
            {Object.entries(operationNames).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>操作人</span>
          <Input
            aria-label="操作人"
            value={draft.operatorName}
            onChange={(event) => setDraft({ ...draft, operatorName: event.target.value })}
            placeholder="用户名"
          />
        </label>
        <label>
          <span>执行结果</span>
          <select
            aria-label="执行结果"
            value={draft.success}
            onChange={(event) => setDraft({ ...draft, success: event.target.value })}
          >
            <option value="">全部结果</option>
            <option value="true">成功</option>
            <option value="false">失败</option>
          </select>
        </label>
        <label>
          <span>开始时间</span>
          <Input
            aria-label="开始时间"
            type="datetime-local"
            value={draft.beginTime}
            onChange={(event) => setDraft({ ...draft, beginTime: event.target.value })}
          />
        </label>
        <label>
          <span>结束时间</span>
          <Input
            aria-label="结束时间"
            type="datetime-local"
            value={draft.endTime}
            onChange={(event) => setDraft({ ...draft, endTime: event.target.value })}
          />
        </label>
        <div className="audit-filter-actions">
          <Button type="submit">
            <Search aria-hidden="true" /> 查询
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              setDraft(emptyFilters);
              updateLocation(1, emptyFilters);
            }}
          >
            重置
          </Button>
        </div>
      </form>
      <section className="knowledge-table-panel audit-table-panel">
        {query.isLoading ? (
          <div className="console-table-state">正在读取审计日志…</div>
        ) : query.isError ? (
          <div className="console-table-state console-table-state--error">
            {query.error instanceof Error ? query.error.message : "审计日志加载失败"}
          </div>
        ) : query.data?.records.length === 0 ? (
          <div className="console-empty-state">
            <FileClock aria-hidden="true" />
            <strong>没有匹配的审计记录</strong>
            <p>用户等业务发生变更后，记录会显示在这里。</p>
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>时间</TableHead>
                  <TableHead>业务</TableHead>
                  <TableHead>操作</TableHead>
                  <TableHead>说明</TableHead>
                  <TableHead>操作人</TableHead>
                  <TableHead>结果</TableHead>
                  <TableHead className="w-[70px] text-right">详情</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.data?.records.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>
                      <time>{formatTraceTime(item.createTime)}</time>
                    </TableCell>
                    <TableCell>
                      <div className="audit-business">
                        <strong>{item.bizType}</strong>
                        <small>{item.bizId}</small>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span
                        className={`audit-operation audit-operation--${item.operationType.toLowerCase()}`}
                      >
                        {operationNames[item.operationType] || item.operationType}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="audit-description" title={item.actionDesc}>
                        {item.actionDesc}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="audit-operator">
                        <strong>{item.operatorName || "SYSTEM"}</strong>
                        <small>{item.ip || "无 IP"}</small>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className={`audit-result ${item.success ? "is-success" : "is-error"}`}>
                        <i />
                        {item.success ? "成功" : "失败"}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="table-actions">
                        <button
                          type="button"
                          aria-label={`查看审计 ${item.id}`}
                          onClick={() => void openDetail(item)}
                        >
                          <Eye aria-hidden="true" />
                        </button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <footer className="console-pagination">
              <span>共 {query.data?.total || 0} 条记录</span>
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
      <AuditDetailDialog current={selected} onClose={() => setSelected(undefined)} />
    </main>
  );
}
