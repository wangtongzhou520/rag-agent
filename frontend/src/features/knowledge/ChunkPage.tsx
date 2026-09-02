import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Boxes, Edit3, Power, PowerOff, RefreshCw, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { toast } from "sonner";

import {
  batchSetChunksEnabled,
  deleteChunk,
  getDocument,
  listChunks,
  setChunkEnabled,
  updateChunk,
} from "@/features/knowledge/api";
import type { KnowledgeChunk } from "@/features/knowledge/types";
import { Button } from "@/shared/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/Dialog";

const PAGE_SIZE = 20;
const BATCH_LIMIT = 500;

export function ChunkPage() {
  const { docId: rawDocId } = useParams();
  const docId = Number(rawDocId);
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [enabled, setEnabled] = useState<"" | "true" | "false">("");
  const [selected, setSelected] = useState<string[]>([]);
  const [editing, setEditing] = useState<KnowledgeChunk>();
  const [deleting, setDeleting] = useState<KnowledgeChunk>();

  const documentQuery = useQuery({
    queryKey: ["knowledge-document", docId],
    queryFn: () => getDocument(docId),
    enabled: Number.isInteger(docId),
  });
  const query = useQuery({
    queryKey: ["knowledge-chunks", docId, page, enabled],
    queryFn: () =>
      listChunks(docId, page, PAGE_SIZE, enabled === "" ? undefined : enabled === "true"),
    enabled: Number.isInteger(docId),
  });

  useEffect(() => setSelected([]), [page, enabled]);

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["knowledge-chunks", docId] });
  const toggle = useMutation({
    mutationFn: ({ chunkId, value }: { chunkId: string; value: boolean }) =>
      setChunkEnabled(docId, chunkId, value),
    onSuccess: (_, input) => {
      toast.success(input.value ? "Chunk 已启用" : "Chunk 已停用");
      void refresh();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "状态修改失败"),
  });
  const batchToggle = useMutation({
    mutationFn: (value: boolean) => batchSetChunksEnabled(docId, selected, value),
    onSuccess: (_, value) => {
      toast.success(`已${value ? "启用" : "停用"} ${selected.length} 个 Chunk`);
      setSelected([]);
      void refresh();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "批量操作失败"),
  });
  const save = useMutation({
    mutationFn: ({ id, content }: { id: string; content: string }) =>
      updateChunk(docId, id, content),
    onSuccess: () => {
      toast.success("Chunk 已更新并重新向量化");
      setEditing(undefined);
      void refresh();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Chunk 保存失败"),
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteChunk(docId, id),
    onSuccess: () => {
      toast.success("Chunk 已删除");
      setDeleting(undefined);
      setSelected((ids) => ids.filter((id) => id !== deleting?.id));
      void refresh();
      void queryClient.invalidateQueries({ queryKey: ["knowledge-document", docId] });
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Chunk 删除失败"),
  });

  if (!Number.isInteger(docId)) {
    return (
      <main className="console-content">
        <div className="console-table-state console-table-state--error">文档 ID 无效</div>
      </main>
    );
  }

  const rows = query.data?.records || [];
  const pageSelected = rows.length > 0 && rows.every((item) => selected.includes(item.id));
  const togglePage = () => {
    if (pageSelected) {
      setSelected((ids) => ids.filter((id) => !rows.some((item) => item.id === id)));
    } else {
      const next = [...new Set([...selected, ...rows.map((item) => item.id)])];
      if (next.length > BATCH_LIMIT) return toast.error("一次最多选择 500 个 Chunk");
      setSelected(next);
    }
  };

  return (
    <main className="console-content chunk-page">
      <Link
        className="console-back-link"
        to={
          documentQuery.data
            ? `/admin/knowledge-bases/${documentQuery.data.kbId}/documents`
            : "/admin/knowledge-bases"
        }
      >
        <ArrowLeft aria-hidden="true" /> 返回文档
      </Link>
      <header className="console-page-header chunk-page-header">
        <div className="console-page-heading">
          <p>文档 / {documentQuery.data ? `编号 ${documentQuery.data.id}` : rawDocId}</p>
          <h1>{documentQuery.data?.docName || "Chunk 管理"}</h1>
          <span>校正分块内容和检索可见性。编辑保存时会调用 Embedding 模型重新向量化。</span>
        </div>
        <div className="chunk-total">
          <Boxes aria-hidden="true" />
          <span>
            <strong>{query.data?.total || 0}</strong> 个分块
          </span>
        </div>
      </header>

      <section className="chunk-toolbar">
        <div className="chunk-selection">
          <label>
            <input type="checkbox" checked={pageSelected} onChange={togglePage} /> 选择当前页
          </label>
          <span>
            {selected.length ? `已选 ${selected.length} / ${BATCH_LIMIT}` : "选择内容后可批量启停"}
          </span>
        </div>
        <div>
          <select
            aria-label="启用状态"
            value={enabled}
            onChange={(event) => {
              setPage(1);
              setEnabled(event.target.value as typeof enabled);
            }}
          >
            <option value="">全部 Chunk</option>
            <option value="true">仅启用</option>
            <option value="false">仅停用</option>
          </select>
          {selected.length > 0 && (
            <>
              <Button
                variant="secondary"
                disabled={batchToggle.isPending}
                onClick={() => batchToggle.mutate(true)}
              >
                <Power aria-hidden="true" /> 批量启用
              </Button>
              <Button
                variant="secondary"
                disabled={batchToggle.isPending}
                onClick={() => batchToggle.mutate(false)}
              >
                <PowerOff aria-hidden="true" /> 批量停用
              </Button>
            </>
          )}
          <Button variant="secondary" onClick={() => void query.refetch()}>
            <RefreshCw aria-hidden="true" /> 刷新
          </Button>
        </div>
      </section>

      <section className="chunk-list" aria-label="文档分块">
        {query.isLoading ? (
          <div className="console-table-state">正在读取 Chunk…</div>
        ) : query.isError ? (
          <div className="console-table-state console-table-state--error">
            {query.error instanceof Error ? query.error.message : "Chunk 加载失败"}
          </div>
        ) : rows.length === 0 ? (
          <div className="console-empty-state">
            <Boxes aria-hidden="true" />
            <strong>没有可显示的 Chunk</strong>
            <p>文档完成分块后，内容会出现在这里。</p>
          </div>
        ) : (
          rows.map((item) => (
            <article
              className={`chunk-card${selected.includes(item.id) ? " chunk-card--selected" : ""}`}
              key={item.id}
            >
              <label className="chunk-card__select">
                <input
                  type="checkbox"
                  aria-label={`选择 Chunk ${item.chunkIndex}`}
                  checked={selected.includes(item.id)}
                  onChange={(event) =>
                    setSelected((ids) =>
                      event.target.checked ? [...ids, item.id] : ids.filter((id) => id !== item.id),
                    )
                  }
                />
              </label>
              <div className="chunk-card__index">
                <span>分块</span>
                <strong>{String(item.chunkIndex).padStart(3, "0")}</strong>
              </div>
              <div className="chunk-card__content">
                <p>{item.content}</p>
                <small>
                  {item.content.length} 字符 · {shortId(item.id)}
                </small>
              </div>
              <div className="chunk-card__controls">
                <button
                  type="button"
                  className={`switch-control${item.enabled ? " is-on" : ""}`}
                  aria-label={`${item.enabled ? "停用" : "启用"} Chunk ${item.chunkIndex}`}
                  aria-pressed={item.enabled}
                  onClick={() => toggle.mutate({ chunkId: item.id, value: !item.enabled })}
                >
                  <i />
                </button>
                <button
                  type="button"
                  aria-label={`编辑 Chunk ${item.chunkIndex}`}
                  onClick={() => setEditing(item)}
                >
                  <Edit3 />
                </button>
                <button
                  type="button"
                  aria-label={`删除 Chunk ${item.chunkIndex}`}
                  onClick={() => setDeleting(item)}
                >
                  <Trash2 />
                </button>
              </div>
            </article>
          ))
        )}
      </section>

      {query.data && query.data.total > 0 && (
        <footer className="console-pagination">
          <span>
            第 {page} 页，每页 {PAGE_SIZE} 条
          </span>
          <div>
            <Button variant="ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>
              上一页
            </Button>
            <span>
              {page} / {query.data.pages || 1}
            </span>
            <Button
              variant="ghost"
              disabled={page >= query.data.pages}
              onClick={() => setPage(page + 1)}
            >
              下一页
            </Button>
          </div>
        </footer>
      )}

      <ChunkEditDialog
        chunk={editing}
        busy={save.isPending}
        onClose={() => setEditing(undefined)}
        onSave={(content) => editing && save.mutate({ id: editing.id, content })}
      />
      <Dialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(undefined)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除 Chunk {deleting?.chunkIndex}？</DialogTitle>
            <DialogDescription>
              对应向量会同时删除，检索结果将不再包含这段内容。此操作不可撤销。
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

function ChunkEditDialog({
  chunk,
  busy,
  onClose,
  onSave,
}: {
  chunk?: KnowledgeChunk;
  busy: boolean;
  onClose: () => void;
  onSave: (content: string) => void;
}) {
  const [content, setContent] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    setContent(chunk?.content || "");
    setError("");
  }, [chunk]);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!content.trim()) return setError("Chunk 内容不能为空");
    onSave(content.trim());
  };
  return (
    <Dialog open={Boolean(chunk)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="chunk-edit-dialog">
        <form onSubmit={submit}>
          <DialogHeader>
            <span className="dialog-kicker">
              <Edit3 aria-hidden="true" /> 内容编辑
            </span>
            <DialogTitle>编辑 Chunk {chunk?.chunkIndex}</DialogTitle>
            <DialogDescription>
              保存会重新调用当前知识库的 Embedding 模型，旧向量将被替换。
            </DialogDescription>
          </DialogHeader>
          <label className="chunk-editor-field">
            <span>分块内容</span>
            <textarea
              aria-label="分块内容"
              value={content}
              onChange={(event) => setContent(event.target.value)}
            />
            <small>{content.length} 字符</small>
          </label>
          {error && (
            <p className="console-form-error" role="alert">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              取消
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "正在重新向量化…" : "保存并重新向量化"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function shortId(id: string) {
  return id.length > 14 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id;
}
