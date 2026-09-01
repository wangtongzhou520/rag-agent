import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, Edit3, Plus, RefreshCw, Search, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import {
  createKnowledgeBase,
  deleteKnowledgeBase,
  listKnowledgeBases,
  updateKnowledgeBase,
} from "@/features/knowledge/api";
import { KnowledgeBaseDialog } from "@/features/knowledge/KnowledgeBaseDialog";
import type { KnowledgeBase, KnowledgeBaseWrite } from "@/features/knowledge/types";
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

export function KnowledgeBasePage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [keyword, setKeyword] = useState("");
  const [editing, setEditing] = useState<KnowledgeBase>();
  const [formOpen, setFormOpen] = useState(false);
  const [deleting, setDeleting] = useState<KnowledgeBase>();

  const query = useQuery({
    queryKey: ["knowledge-bases", page, keyword],
    queryFn: () => listKnowledgeBases(page, PAGE_SIZE, keyword),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["knowledge-bases"] });
  const save = useMutation({
    mutationFn: (value: KnowledgeBaseWrite) =>
      editing
        ? updateKnowledgeBase(editing.id, {
            name: value.name,
            embeddingModel: value.embeddingModel,
          })
        : createKnowledgeBase(value),
    onSuccess: () => {
      toast.success(editing ? "知识库已更新" : "知识库已创建");
      setFormOpen(false);
      setEditing(undefined);
      void refresh();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "保存失败"),
  });
  const remove = useMutation({
    mutationFn: (id: number) => deleteKnowledgeBase(id),
    onSuccess: () => {
      toast.success("知识库已删除");
      setDeleting(undefined);
      void refresh();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "删除失败"),
  });

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    setPage(1);
    setKeyword(search.trim());
  };

  return (
    <main className="console-content knowledge-page">
      <header className="console-page-header">
        <div className="console-page-heading">
          <p>KNOWLEDGE OPERATIONS / F2</p>
          <h1>知识库</h1>
          <span>管理检索边界、向量集合与 Embedding 模型。</span>
        </div>
        <Button
          onClick={() => {
            setEditing(undefined);
            setFormOpen(true);
          }}
        >
          <Plus className="h-4 w-4" /> 新建知识库
        </Button>
      </header>

      <section className="console-toolbar">
        <form onSubmit={submitSearch}>
          <Search aria-hidden="true" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜索知识库名称"
          />
        </form>
        <Button variant="secondary" onClick={() => void query.refetch()}>
          <RefreshCw className="h-4 w-4" /> 刷新
        </Button>
      </section>

      <section className="knowledge-table-panel">
        {query.isLoading ? (
          <div className="console-table-state">正在读取知识库…</div>
        ) : query.isError ? (
          <div className="console-table-state console-table-state--error">
            {query.error instanceof Error ? query.error.message : "知识库加载失败"}
          </div>
        ) : query.data?.records.length === 0 ? (
          <div className="console-empty-state">
            <Database aria-hidden="true" />
            <strong>{keyword ? "没有匹配的知识库" : "还没有知识库"}</strong>
            <p>{keyword ? "尝试调整搜索关键词。" : "创建第一个向量检索边界。"}</p>
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>名称</TableHead>
                  <TableHead>Collection</TableHead>
                  <TableHead>Embedding 模型</TableHead>
                  <TableHead className="w-[150px] text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.data?.records.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>
                      <div className="knowledge-name-cell">
                        <span>
                          <Database aria-hidden="true" />
                        </span>
                        <div>
                          <strong>{item.name}</strong>
                          <small>ID {item.id}</small>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <code>{item.collectionName}</code>
                    </TableCell>
                    <TableCell>{item.embeddingModel}</TableCell>
                    <TableCell>
                      <div className="table-actions">
                        <button
                          type="button"
                          onClick={() => {
                            setEditing(item);
                            setFormOpen(true);
                          }}
                          aria-label={`编辑 ${item.name}`}
                        >
                          <Edit3 />
                        </button>
                        <button
                          type="button"
                          onClick={() => setDeleting(item)}
                          aria-label={`删除 ${item.name}`}
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
              <span>共 {query.data?.total || 0} 个知识库</span>
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

      <KnowledgeBaseDialog
        open={formOpen}
        current={editing}
        busy={save.isPending}
        onClose={() => setFormOpen(false)}
        onSubmit={(value) => save.mutate(value)}
      />
      <Dialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(undefined)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除知识库“{deleting?.name}”？</DialogTitle>
            <DialogDescription>
              此操作只允许用于没有文档的知识库。存在文档时，后端会拒绝删除并保留全部数据。
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
