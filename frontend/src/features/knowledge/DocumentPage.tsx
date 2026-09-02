import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Boxes,
  Eye,
  FileText,
  Link2,
  Play,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";

import { DocumentPreviewDialog } from "@/features/chat/DocumentPreviewDialog";
import type { SourceRef } from "@/features/chat/types";
import {
  deleteDocument,
  getIngestionSpecSchema,
  getKnowledgeBase,
  listDocuments,
  setDocumentEnabled,
  triggerDocumentChunk,
  uploadDocument,
} from "@/features/knowledge/api";
import { DocumentStatusBadge } from "@/features/knowledge/DocumentStatusBadge";
import { DocumentUploadDialog } from "@/features/knowledge/DocumentUploadDialog";
import type { KnowledgeDocument, UploadDocumentInput } from "@/features/knowledge/types";
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

export function DocumentPage() {
  const { kbId: rawKbId } = useParams();
  const kbId = Number(rawKbId);
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [deleting, setDeleting] = useState<KnowledgeDocument>();
  const [preview, setPreview] = useState<SourceRef>();
  const [processing, setProcessing] = useState<number[]>([]);

  const baseQuery = useQuery({
    queryKey: ["knowledge-base", kbId],
    queryFn: () => getKnowledgeBase(kbId),
    enabled: Number.isInteger(kbId),
  });
  const schemaQuery = useQuery({
    queryKey: ["ingestion-spec-schema"],
    queryFn: getIngestionSpecSchema,
    enabled: uploadOpen,
  });
  const query = useQuery({
    queryKey: ["knowledge-documents", kbId, page, status, keyword],
    queryFn: () => listDocuments(kbId, page, PAGE_SIZE, status, keyword),
    enabled: Number.isInteger(kbId),
    refetchInterval: processing.length ? 2000 : false,
  });

  useEffect(() => {
    if (!query.data || !processing.length) return;
    setProcessing((ids) =>
      ids.filter((id) => {
        const document = query.data.records.find((item) => item.id === id);
        return Boolean(
          document && (document.status === "pending" || document.status === "running"),
        );
      }),
    );
  }, [processing.length, query.data]);

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["knowledge-documents", kbId] });
  const upload = useMutation({
    mutationFn: (input: UploadDocumentInput) => uploadDocument(kbId, input),
    onSuccess: () => {
      toast.success("文档已创建，请确认后启动分块");
      setUploadOpen(false);
      void refresh();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "文档导入失败"),
  });
  const chunk = useMutation({
    mutationFn: (id: number) => triggerDocumentChunk(id),
    onSuccess: (_, id) => {
      toast.success("分块任务已提交");
      setProcessing((ids) => [...new Set([...ids, id])]);
      void refresh();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "任务提交失败"),
  });
  const toggle = useMutation({
    mutationFn: ({ id, value }: { id: number; value: boolean }) => setDocumentEnabled(id, value),
    onSuccess: (_, input) => {
      toast.success(input.value ? "文档已启用" : "文档已停用");
      void refresh();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "状态修改失败"),
  });
  const remove = useMutation({
    mutationFn: (id: number) => deleteDocument(id),
    onSuccess: () => {
      toast.success("文档已删除");
      setDeleting(undefined);
      void refresh();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "文档删除失败"),
  });

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    setPage(1);
    setKeyword(search.trim());
  };

  if (!Number.isInteger(kbId)) {
    return (
      <main className="console-content">
        <div className="console-table-state console-table-state--error">知识库 ID 无效</div>
      </main>
    );
  }

  return (
    <main className="console-content document-page">
      <Link className="console-back-link" to="/admin/knowledge-bases">
        <ArrowLeft aria-hidden="true" /> 返回知识库
      </Link>
      <header className="console-page-header">
        <div className="console-page-heading">
          <p>知识库 / {baseQuery.data?.name || `编号 ${kbId}`}</p>
          <h1>文档管理</h1>
          <span>导入材料、观察处理状态，并控制进入检索链路的内容。</span>
        </div>
        <Button onClick={() => setUploadOpen(true)}>
          <Plus className="h-4 w-4" /> 导入文档
        </Button>
      </header>

      <p className="document-process-hint">
        文档导入后需要手动开始分块；处理状态变为“已完成”后，内容才会进入检索。
      </p>

      <section className="console-toolbar document-toolbar">
        <form onSubmit={submitSearch}>
          <Search aria-hidden="true" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜索文档名称"
          />
        </form>
        <div>
          <select
            aria-label="处理状态"
            value={status}
            onChange={(event) => {
              setPage(1);
              setStatus(event.target.value);
            }}
          >
            <option value="">全部状态</option>
            <option value="pending">待分块</option>
            <option value="running">处理中</option>
            <option value="success">已完成</option>
            <option value="failed">处理失败</option>
          </select>
          <Button variant="secondary" onClick={() => void query.refetch()}>
            <RefreshCw className="h-4 w-4" /> 刷新
          </Button>
        </div>
      </section>

      <section className="knowledge-table-panel">
        {query.isLoading ? (
          <div className="console-table-state">正在读取文档…</div>
        ) : query.isError ? (
          <div className="console-table-state console-table-state--error">
            {query.error instanceof Error ? query.error.message : "文档加载失败"}
          </div>
        ) : query.data?.records.length === 0 ? (
          <div className="console-empty-state">
            <FileText aria-hidden="true" />
            <strong>{keyword || status ? "没有匹配的文档" : "这个知识库还没有文档"}</strong>
            <p>
              {keyword || status
                ? "调整名称或状态筛选。"
                : "导入文件或 URL，建立第一批可检索内容。"}
            </p>
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>文档</TableHead>
                  <TableHead>来源</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>启用</TableHead>
                  <TableHead>Chunk</TableHead>
                  <TableHead>类型 / 大小</TableHead>
                  <TableHead className="w-[180px] text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.data?.records.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>
                      <div className="document-name-cell">
                        <FileText aria-hidden="true" />
                        <div>
                          <strong>{item.docName}</strong>
                          <small>文档编号 {item.id}</small>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="document-source">
                        <Link2 aria-hidden="true" />
                        {item.sourceType === "url" ? "URL" : "文件"}
                      </span>
                    </TableCell>
                    <TableCell>
                      <DocumentStatusBadge status={item.status} />
                    </TableCell>
                    <TableCell>
                      <button
                        type="button"
                        className={`switch-control${item.enabled ? " is-on" : ""}`}
                        aria-label={`${item.enabled ? "停用" : "启用"} ${item.docName}`}
                        aria-pressed={item.enabled}
                        onClick={() => toggle.mutate({ id: item.id, value: !item.enabled })}
                      >
                        <i />
                      </button>
                    </TableCell>
                    <TableCell>
                      <Button asChild variant="ghost" className="chunk-count-link">
                        <Link to={`/admin/documents/${item.id}/chunks`}>
                          <Boxes aria-hidden="true" /> {item.chunkCount}
                        </Link>
                      </Button>
                    </TableCell>
                    <TableCell>
                      <span className="document-file-meta">
                        {item.fileType?.toUpperCase() || "—"}
                        <small>{formatFileSize(item.fileSize)}</small>
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="table-actions document-actions">
                        <button
                          type="button"
                          aria-label={`预览 ${item.docName}`}
                          onClick={() => setPreview(toSource(item))}
                        >
                          <Eye />
                        </button>
                        <button
                          type="button"
                          aria-label={`开始分块 ${item.docName}`}
                          disabled={item.status === "running" || processing.includes(item.id)}
                          onClick={() => chunk.mutate(item.id)}
                        >
                          <Play />
                        </button>
                        <button
                          type="button"
                          aria-label={`删除文档 ${item.docName}`}
                          onClick={() => setDeleting(item)}
                        >
                          <Trash2 />
                        </button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <footer className="console-pagination">
              <span>共 {query.data?.total || 0} 篇文档</span>
              <div>
                <Button variant="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                  上一页
                </Button>
                <span>
                  {page} / {query.data?.pages || 1}
                </span>
                <Button
                  variant="ghost"
                  disabled={page >= (query.data?.pages || 1)}
                  onClick={() => setPage(page + 1)}
                >
                  下一页
                </Button>
              </div>
            </footer>
          </>
        )}
      </section>

      <DocumentUploadDialog
        open={uploadOpen}
        schema={schemaQuery.data}
        schemaError={schemaQuery.isError ? "无法读取服务端分块参数" : undefined}
        busy={upload.isPending}
        onClose={() => setUploadOpen(false)}
        onSubmit={(input) => upload.mutate(input)}
      />
      <DocumentPreviewDialog source={preview} onClose={() => setPreview(undefined)} />
      <Dialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(undefined)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除文档“{deleting?.docName}”？</DialogTitle>
            <DialogDescription>
              文档及其 Chunk 将退出检索，并由后台任务清理关联文件。此操作不可撤销。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleting(undefined)}>
              取消
            </Button>
            <Button
              className="bg-[var(--danger)] hover:bg-red-700"
              disabled={remove.isPending}
              onClick={() => deleting && remove.mutate(deleting.id)}
            >
              确认删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}

function formatFileSize(bytes?: number) {
  if (bytes === undefined || bytes === null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

function toSource(document: KnowledgeDocument): SourceRef {
  return {
    index: 1,
    docId: String(document.id),
    docName: document.docName,
    sourceType: document.sourceType,
    fileType: document.fileType,
    url: document.sourceLocation,
  };
}
