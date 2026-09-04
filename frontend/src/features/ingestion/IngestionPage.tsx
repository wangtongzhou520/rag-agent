import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Braces,
  Edit3,
  FileInput,
  GitCommitHorizontal,
  Play,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import "@/features/ingestion/IngestionPage.css";
import {
  createPipeline,
  deletePipeline,
  getTaskNodes,
  listAsyncTasks,
  listPipelines,
  listPipelineTasks,
  runUploadTask,
  runUrlTask,
  updatePipeline,
} from "@/features/ingestion/api";
import { PipelineDialog } from "@/features/ingestion/PipelineDialog";
import { RunTaskDialog, type RunTaskValue } from "@/features/ingestion/RunTaskDialog";
import type { Pipeline, PipelineTask, PipelineWrite } from "@/features/ingestion/types";
import { formatTraceTime } from "@/features/trace/format";
import { Button } from "@/shared/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/Dialog";
import { Input } from "@/shared/ui/Input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/shared/ui/Table";

const PAGE_SIZE = 20;
type View = "pipelines" | "runs" | "queue";

const nodeNames: Record<string, string> = {
  fetcher: "获取",
  parser: "解析",
  enhancer: "文档增强",
  chunker: "分块",
  enricher: "块富集",
  indexer: "索引",
};
const statusNames: Record<string, string> = {
  pending: "等待中",
  running: "运行中",
  completed: "已完成",
  success: "已完成",
  failed: "失败",
  skipped: "已跳过",
};

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`pipeline-status pipeline-status--${status}`}>
      {statusNames[status] || status}
    </span>
  );
}

export function IngestionPage() {
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const view = (params.get("view") || "pipelines") as View;
  const page = Math.max(1, Number(params.get("page")) || 1);
  const keyword = params.get("keyword")?.trim() || "";
  const status = params.get("status") || "";
  const [search, setSearch] = useState(keyword);
  const [editorOpen, setEditorOpen] = useState(false);
  const [runOpen, setRunOpen] = useState(false);
  const [editing, setEditing] = useState<Pipeline>();
  const [runPipeline, setRunPipeline] = useState<number>();
  const [deleting, setDeleting] = useState<Pipeline>();
  const [selectedTask, setSelectedTask] = useState<PipelineTask>();
  useEffect(() => setSearch(keyword), [keyword]);

  const pipelines = useQuery({
    queryKey: ["ingestion-pipelines", page, keyword],
    queryFn: () => listPipelines(page, PAGE_SIZE, keyword),
    enabled: view === "pipelines",
  });
  const pipelineOptions = useQuery({
    queryKey: ["ingestion-pipeline-options"],
    queryFn: () => listPipelines(1, 100),
  });
  const runs = useQuery({
    queryKey: ["ingestion-runs", page, status],
    queryFn: () => listPipelineTasks(page, PAGE_SIZE, status),
    enabled: view === "runs",
    refetchInterval: view === "runs" ? 5000 : false,
  });
  const queue = useQuery({
    queryKey: ["async-task-queue", page, status],
    queryFn: () => listAsyncTasks(page, PAGE_SIZE, status),
    enabled: view === "queue",
    refetchInterval: view === "queue" ? 5000 : false,
  });
  const nodeLogs = useQuery({
    queryKey: ["ingestion-run-nodes", selectedTask?.id],
    queryFn: () => getTaskNodes(selectedTask!.id),
    enabled: Boolean(selectedTask),
  });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["ingestion-pipelines"] });
    void queryClient.invalidateQueries({ queryKey: ["ingestion-pipeline-options"] });
    void queryClient.invalidateQueries({ queryKey: ["ingestion-runs"] });
    void queryClient.invalidateQueries({ queryKey: ["async-task-queue"] });
  };
  const save = useMutation({
    mutationFn: (value: PipelineWrite) =>
      editing ? updatePipeline(editing.id, value) : createPipeline(value),
    onSuccess: () => {
      toast.success(editing ? "Pipeline 已更新" : "Pipeline 已创建");
      setEditorOpen(false);
      setEditing(undefined);
      refresh();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Pipeline 保存失败"),
  });
  const remove = useMutation({
    mutationFn: deletePipeline,
    onSuccess: () => {
      toast.success("Pipeline 已删除");
      setDeleting(undefined);
      refresh();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Pipeline 删除失败"),
  });
  const run = useMutation({
    mutationFn: (value: RunTaskValue) => {
      if (value.sourceType === "file") {
        if (!value.file) throw new Error("请选择文件");
        return runUploadTask(value.pipelineId, value.file, value.vectorSpaceId);
      }
      if (!value.location) throw new Error("请填写来源地址");
      return runUrlTask({
        pipelineId: value.pipelineId,
        sourceType: value.sourceType,
        location: value.location,
        fileName: value.fileName,
        vectorSpaceId: value.vectorSpaceId,
      });
    },
    onSuccess: (result) => {
      if (result.status === "completed") toast.success(`任务 ${result.taskId} 已完成`);
      else toast.error(result.message || "Pipeline 执行失败");
      setRunOpen(false);
      updateLocation("runs", 1, "", "");
      refresh();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "任务执行失败"),
  });

  const updateLocation = (
    nextView: View,
    nextPage = 1,
    nextKeyword = keyword,
    nextStatus = status,
  ) => {
    const next = new URLSearchParams();
    if (nextView !== "pipelines") next.set("view", nextView);
    if (nextPage > 1) next.set("page", String(nextPage));
    if (nextView === "pipelines" && nextKeyword) next.set("keyword", nextKeyword);
    if (nextView !== "pipelines" && nextStatus) next.set("status", nextStatus);
    setParams(next);
  };
  const searchSubmit = (event: FormEvent) => {
    event.preventDefault();
    updateLocation("pipelines", 1, search.trim(), "");
  };
  const options = pipelineOptions.data?.records || [];

  return (
    <main className="console-content ingestion-page">
      <header className="console-page-header ingestion-page-header">
        <div className="console-page-heading">
          <p>入库编排</p>
          <h1>Pipeline 与任务</h1>
          <span>配置可复用的文档处理链，运行一次真实输入，并从节点日志定位耗时和失败位置。</span>
        </div>
        <div className="ingestion-header-actions">
          <Button variant="secondary" onClick={refresh}>
            <RefreshCw aria-hidden="true" /> 刷新
          </Button>
          <Button
            disabled={!options.length}
            onClick={() => {
              setRunPipeline(undefined);
              setRunOpen(true);
            }}
          >
            <Play aria-hidden="true" /> 运行 Pipeline
          </Button>
        </div>
      </header>

      <nav className="ingestion-view-tabs" aria-label="Pipeline 管理视图">
        <button
          className={view === "pipelines" ? "active" : ""}
          onClick={() => updateLocation("pipelines", 1, "", "")}
        >
          <GitCommitHorizontal /> Pipeline 配置
        </button>
        <button
          className={view === "runs" ? "active" : ""}
          onClick={() => updateLocation("runs", 1, "", "")}
        >
          <Activity /> 调试运行
        </button>
        <button
          className={view === "queue" ? "active" : ""}
          onClick={() => updateLocation("queue", 1, "", "")}
        >
          <FileInput /> 后台任务
        </button>
      </nav>

      {view === "pipelines" && (
        <>
          <section className="console-toolbar ingestion-toolbar">
            <form onSubmit={searchSubmit}>
              <Search aria-hidden="true" />
              <Input
                aria-label="搜索 Pipeline"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="搜索 Pipeline 名称"
              />
            </form>
            <Button
              onClick={() => {
                setEditing(undefined);
                setEditorOpen(true);
              }}
            >
              <Plus aria-hidden="true" /> 新建 Pipeline
            </Button>
          </section>
          <section className="pipeline-list-panel">
            {pipelines.isLoading ? (
              <State text="正在读取 Pipeline…" />
            ) : pipelines.isError ? (
              <State
                text={
                  pipelines.error instanceof Error ? pipelines.error.message : "Pipeline 加载失败"
                }
                error
              />
            ) : !pipelines.data?.records.length ? (
              <Empty
                icon={<GitCommitHorizontal />}
                title={keyword ? "没有匹配的 Pipeline" : "还没有 Pipeline"}
                text={
                  keyword ? "调整关键词后重试。" : "创建一条处理链后，即可使用文件或 URL 进行调试。"
                }
              />
            ) : (
              pipelines.data.records.map((item) => (
                <article className="pipeline-card" key={item.id}>
                  <header>
                    <div>
                      <span>#{item.id}</span>
                      <h2>{item.name}</h2>
                    </div>
                    <div className="pipeline-card-actions">
                      <Button
                        variant="ghost"
                        onClick={() => {
                          setRunPipeline(item.id);
                          setRunOpen(true);
                        }}
                      >
                        <Play /> 运行
                      </Button>
                      <button
                        aria-label={`编辑 ${item.name}`}
                        onClick={() => {
                          setEditing(item);
                          setEditorOpen(true);
                        }}
                      >
                        <Edit3 />
                      </button>
                      <button aria-label={`删除 ${item.name}`} onClick={() => setDeleting(item)}>
                        <Trash2 />
                      </button>
                    </div>
                  </header>
                  <p>{item.description || "未填写说明"}</p>
                  <div className="pipeline-flow" aria-label={`${item.name} 执行顺序`}>
                    {item.nodes.map((node, index) => (
                      <div className="pipeline-flow-node" key={node.nodeId}>
                        <span>{index + 1}</span>
                        <div>
                          <strong>{nodeNames[node.nodeType]}</strong>
                          <small>{node.nodeId}</small>
                        </div>
                        {index < item.nodes.length - 1 && <i />}
                      </div>
                    ))}
                  </div>
                  <footer>
                    <span>{item.nodes.length} 个节点</span>
                    <time>更新于 {formatTraceTime(item.updateTime)}</time>
                  </footer>
                </article>
              ))
            )}
            {pipelines.data && (
              <Pagination
                page={page}
                pages={pipelines.data.pages}
                total={pipelines.data.total}
                unit="条 Pipeline"
                onChange={(next) => updateLocation("pipelines", next)}
              />
            )}
          </section>
        </>
      )}

      {view === "runs" && (
        <TaskTablePanel
          loading={runs.isLoading}
          error={runs.error}
          records={runs.data?.records || []}
          status={status}
          onStatus={(value) => updateLocation("runs", 1, "", value)}
          onSelect={setSelectedTask}
          pagination={
            runs.data
              ? {
                  page,
                  pages: runs.data.pages,
                  total: runs.data.total,
                  onChange: (next: number) => updateLocation("runs", next),
                }
              : undefined
          }
        />
      )}

      {view === "queue" && (
        <section className="knowledge-table-panel pipeline-task-panel">
          <TaskFilter status={status} onChange={(value) => updateLocation("queue", 1, "", value)} />
          {queue.isLoading ? (
            <State text="正在读取后台任务…" />
          ) : queue.isError ? (
            <State
              text={queue.error instanceof Error ? queue.error.message : "后台任务加载失败"}
              error
            />
          ) : !queue.data?.records.length ? (
            <Empty
              icon={<FileInput />}
              title="没有匹配的后台任务"
              text="文档分块、知识库清理和反馈同步任务会显示在这里。"
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>任务</TableHead>
                  <TableHead>业务键</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>重试</TableHead>
                  <TableHead>下次执行 / 租约</TableHead>
                  <TableHead>创建时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {queue.data.records.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>
                      <strong>{item.taskType}</strong>
                      <small className="pipeline-table-sub">
                        #{item.id} · {item.eventId.slice(0, 8)}
                      </small>
                    </TableCell>
                    <TableCell>
                      <code>{item.bizKey || "—"}</code>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={item.status} />
                      {item.errorMessage && (
                        <small className="pipeline-table-error">{item.errorMessage}</small>
                      )}
                    </TableCell>
                    <TableCell>
                      {item.retryCount} / {item.maxRetries}
                    </TableCell>
                    <TableCell>{formatTraceTime(item.nextRetryAt || item.leaseUntil)}</TableCell>
                    <TableCell>{formatTraceTime(item.createTime)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          {queue.data && (
            <Pagination
              page={page}
              pages={queue.data.pages}
              total={queue.data.total}
              unit="个后台任务"
              onChange={(next) => updateLocation("queue", next)}
            />
          )}
        </section>
      )}

      <PipelineDialog
        open={editorOpen}
        current={editing}
        busy={save.isPending}
        onClose={() => {
          setEditorOpen(false);
          setEditing(undefined);
        }}
        onSubmit={(value) => save.mutate(value)}
      />
      <RunTaskDialog
        open={runOpen}
        pipelines={options}
        initialPipeline={runPipeline}
        busy={run.isPending}
        onClose={() => setRunOpen(false)}
        onSubmit={(value) => run.mutate(value)}
      />
      <DeleteDialog
        current={deleting}
        busy={remove.isPending}
        onClose={() => setDeleting(undefined)}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
      />
      <TaskDetail
        current={selectedTask}
        loading={nodeLogs.isLoading}
        nodes={nodeLogs.data || []}
        onClose={() => setSelectedTask(undefined)}
      />
    </main>
  );
}

function TaskFilter({ status, onChange }: { status: string; onChange: (value: string) => void }) {
  return (
    <div className="pipeline-task-filter">
      <label>
        <span>状态</span>
        <select
          aria-label="任务状态"
          value={status}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">全部状态</option>
          <option value="pending">等待中</option>
          <option value="running">运行中</option>
          <option value="completed">已完成</option>
          <option value="success">成功</option>
          <option value="failed">失败</option>
        </select>
      </label>
    </div>
  );
}

function TaskTablePanel({
  loading,
  error,
  records,
  status,
  onStatus,
  onSelect,
  pagination,
}: {
  loading: boolean;
  error: Error | null;
  records: PipelineTask[];
  status: string;
  onStatus: (value: string) => void;
  onSelect: (value: PipelineTask) => void;
  pagination?: { page: number; pages: number; total: number; onChange: (value: number) => void };
}) {
  return (
    <section className="knowledge-table-panel pipeline-task-panel">
      <TaskFilter status={status} onChange={onStatus} />
      {loading ? (
        <State text="正在读取调试运行…" />
      ) : error ? (
        <State text={error.message || "调试任务加载失败"} error />
      ) : !records.length ? (
        <Empty
          icon={<Activity />}
          title="没有匹配的调试运行"
          text="从任意 Pipeline 发起一次文件或 URL 调试。"
        />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>任务</TableHead>
              <TableHead>来源</TableHead>
              <TableHead>状态</TableHead>
              <TableHead>分块</TableHead>
              <TableHead>耗时</TableHead>
              <TableHead>创建时间</TableHead>
              <TableHead className="text-right">详情</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {records.map((item) => (
              <TableRow key={item.id}>
                <TableCell>
                  <strong>运行 #{item.id}</strong>
                  <small className="pipeline-table-sub">Pipeline #{item.pipelineId}</small>
                </TableCell>
                <TableCell>
                  <span>{item.sourceFileName || item.sourceLocation || "—"}</span>
                  <small className="pipeline-table-sub">{item.sourceType}</small>
                </TableCell>
                <TableCell>
                  <StatusBadge status={item.status} />
                  {item.errorMessage && (
                    <small className="pipeline-table-error">{item.errorMessage}</small>
                  )}
                </TableCell>
                <TableCell>{item.chunkCount}</TableCell>
                <TableCell>
                  {item.startedAt && item.completedAt
                    ? `${Math.max(0, item.completedAt - item.startedAt)} ms`
                    : "—"}
                </TableCell>
                <TableCell>{formatTraceTime(item.createTime)}</TableCell>
                <TableCell className="text-right">
                  <button
                    className="pipeline-detail-button"
                    aria-label={`查看任务 ${item.id}`}
                    onClick={() => onSelect(item)}
                  >
                    <Braces />
                  </button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      {pagination && (
        <Pagination
          page={pagination.page}
          pages={pagination.pages}
          total={pagination.total}
          unit="次运行"
          onChange={pagination.onChange}
        />
      )}
    </section>
  );
}

function TaskDetail({
  current,
  nodes,
  loading,
  onClose,
}: {
  current?: PipelineTask;
  nodes: Awaited<ReturnType<typeof getTaskNodes>>;
  loading: boolean;
  onClose: () => void;
}) {
  return (
    <Dialog open={Boolean(current)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="pipeline-task-detail">
        <DialogHeader>
          <DialogTitle>运行 #{current?.id}</DialogTitle>
          <DialogDescription>
            {current
              ? `Pipeline #${current.pipelineId} · ${current.sourceFileName || current.sourceLocation || current.sourceType}`
              : ""}
          </DialogDescription>
        </DialogHeader>
        {current && (
          <>
            <dl className="pipeline-task-summary">
              <div>
                <dt>状态</dt>
                <dd>
                  <StatusBadge status={current.status} />
                </dd>
              </div>
              <div>
                <dt>分块数</dt>
                <dd>{current.chunkCount}</dd>
              </div>
              <div>
                <dt>开始时间</dt>
                <dd>{formatTraceTime(current.startedAt)}</dd>
              </div>
              <div>
                <dt>结束时间</dt>
                <dd>{formatTraceTime(current.completedAt)}</dd>
              </div>
            </dl>
            {current.errorMessage && <p className="pipeline-run-error">{current.errorMessage}</p>}
            <section className="pipeline-log-list">
              <header>
                <strong>节点日志</strong>
                <span>{nodes.length} 条</span>
              </header>
              {loading ? (
                <State text="正在读取节点日志…" />
              ) : (
                nodes.map((node) => (
                  <article key={node.id}>
                    <div className="pipeline-log-rail">
                      <span>{node.nodeOrder}</span>
                      <i />
                    </div>
                    <div className="pipeline-log-body">
                      <header>
                        <div>
                          <strong>{nodeNames[node.nodeType] || node.nodeType}</strong>
                          <small>{node.nodeId}</small>
                        </div>
                        <div>
                          <StatusBadge status={node.status} />
                          <span>{node.durationMs} ms</span>
                        </div>
                      </header>
                      <p>{node.errorMessage || node.message || "—"}</p>
                      <details>
                        <summary>输出摘要</summary>
                        <pre>
                          {node.output == null ? "无" : JSON.stringify(node.output, null, 2)}
                        </pre>
                      </details>
                    </div>
                  </article>
                ))
              )}
            </section>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function DeleteDialog({
  current,
  busy,
  onClose,
  onConfirm,
}: {
  current?: Pipeline;
  busy: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={Boolean(current)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>删除 Pipeline</DialogTitle>
          <DialogDescription>
            将删除“{current?.name}”及其节点配置，历史运行记录仍会保留。
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button disabled={busy} onClick={onConfirm}>
            {busy ? "正在删除…" : "确认删除"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function State({ text, error = false }: { text: string; error?: boolean }) {
  return (
    <div className={`console-table-state${error ? " console-table-state--error" : ""}`}>{text}</div>
  );
}
function Empty({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return (
    <div className="console-empty-state">
      {icon}
      <strong>{title}</strong>
      <p>{text}</p>
    </div>
  );
}
function Pagination({
  page,
  pages,
  total,
  unit,
  onChange,
}: {
  page: number;
  pages: number;
  total: number;
  unit: string;
  onChange: (value: number) => void;
}) {
  return (
    <footer className="console-pagination">
      <span>
        共 {total} {unit}
      </span>
      <div>
        <Button variant="ghost" disabled={page <= 1} onClick={() => onChange(page - 1)}>
          上一页
        </Button>
        <span>
          {page} / {pages}
        </span>
        <Button variant="ghost" disabled={page >= pages} onClick={() => onChange(page + 1)}>
          下一页
        </Button>
      </div>
    </footer>
  );
}
