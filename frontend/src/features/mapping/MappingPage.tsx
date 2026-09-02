import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Edit3, Plus, RefreshCw, Replace, Search, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { createMapping, deleteMapping, listMappings, updateMapping } from "@/features/mapping/api";
import { MappingDialog } from "@/features/mapping/MappingDialog";
import {
  MATCH_TYPE_LABELS,
  type QueryTermMapping,
  type QueryTermMappingWrite,
} from "@/features/mapping/types";
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

function readPage(value: string | null) {
  const page = Number(value);
  return Number.isInteger(page) && page > 0 ? page : 1;
}

export function MappingPage() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const page = readPage(searchParams.get("page"));
  const keyword = searchParams.get("keyword")?.trim() || "";
  const [search, setSearch] = useState(keyword);
  const [editing, setEditing] = useState<QueryTermMapping>();
  const [formOpen, setFormOpen] = useState(false);
  const [deleting, setDeleting] = useState<QueryTermMapping>();

  useEffect(() => setSearch(keyword), [keyword]);

  const query = useQuery({
    queryKey: ["mappings", page, keyword],
    queryFn: () => listMappings(page, PAGE_SIZE, keyword),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["mappings"] });
  const save = useMutation({
    mutationFn: (value: QueryTermMappingWrite) =>
      editing ? updateMapping(editing.id, value) : createMapping(value),
    onSuccess: () => {
      toast.success(editing ? "查询词映射已更新" : "查询词映射已创建");
      setFormOpen(false);
      setEditing(undefined);
      void refresh();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "映射保存失败"),
  });
  const toggle = useMutation({
    mutationFn: (item: QueryTermMapping) =>
      updateMapping(item.id, {
        sourceTerm: item.sourceTerm,
        targetTerm: item.targetTerm,
        matchType: item.matchType,
        priority: item.priority,
        enabled: !item.enabled,
        domain: item.domain,
        remark: item.remark,
      }),
    onSuccess: (_, item) => {
      toast.success(`已${item.enabled ? "停用" : "启用"}“${item.sourceTerm}”`);
      void refresh();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "状态更新失败"),
  });
  const remove = useMutation({
    mutationFn: (id: number) => deleteMapping(id),
    onSuccess: () => {
      toast.success("查询词映射已删除");
      setDeleting(undefined);
      void refresh();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "映射删除失败"),
  });

  const updateLocation = (nextPage: number, nextKeyword = keyword) => {
    const next = new URLSearchParams();
    if (nextKeyword) next.set("keyword", nextKeyword);
    if (nextPage > 1) next.set("page", String(nextPage));
    setSearchParams(next);
  };
  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    updateLocation(1, search.trim());
  };

  return (
    <main className="console-content mapping-page">
      <header className="console-page-header">
        <div className="console-page-heading">
          <p>问题理解</p>
          <h1>查询词映射</h1>
          <span>统一别名、缩写和业务口语，让检索问题使用稳定的标准术语。</span>
        </div>
        <Button
          onClick={() => {
            setEditing(undefined);
            setFormOpen(true);
          }}
        >
          <Plus aria-hidden="true" /> 新建映射
        </Button>
      </header>

      <section className="console-toolbar mapping-toolbar">
        <form onSubmit={submitSearch}>
          <Search aria-hidden="true" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="搜索原始词或标准词"
            aria-label="搜索查询词映射"
          />
        </form>
        <div>
          {keyword && (
            <Button variant="ghost" onClick={() => updateLocation(1, "")}>
              清除筛选
            </Button>
          )}
          <Button variant="secondary" onClick={() => void query.refetch()}>
            <RefreshCw aria-hidden="true" /> 刷新
          </Button>
        </div>
      </section>

      <section className="knowledge-table-panel mapping-table-panel">
        {query.isLoading ? (
          <div className="console-table-state">正在读取查询词映射…</div>
        ) : query.isError ? (
          <div className="console-table-state console-table-state--error">
            {query.error instanceof Error ? query.error.message : "查询词映射加载失败"}
          </div>
        ) : query.data?.records.length === 0 ? (
          <div className="console-empty-state">
            <Replace aria-hidden="true" />
            <strong>{keyword ? "没有匹配的查询词映射" : "还没有查询词映射"}</strong>
            <p>{keyword ? "尝试调整搜索关键词。" : "添加别名或缩写，统一进入检索的问题表达。"}</p>
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>原始词</TableHead>
                  <TableHead>标准词</TableHead>
                  <TableHead>匹配方式</TableHead>
                  <TableHead>领域</TableHead>
                  <TableHead>优先级</TableHead>
                  <TableHead>启用</TableHead>
                  <TableHead>备注</TableHead>
                  <TableHead className="w-[110px] text-right">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.data?.records.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>
                      <div className="mapping-term-cell">
                        <strong>{item.sourceTerm}</strong>
                        <small>编号 {item.id}</small>
                      </div>
                    </TableCell>
                    <TableCell>
                      <span className="mapping-target-term">{item.targetTerm}</span>
                    </TableCell>
                    <TableCell>
                      <span className={`mapping-match-type mapping-match-type--${item.matchType}`}>
                        {MATCH_TYPE_LABELS[item.matchType] || `类型 ${item.matchType}`}
                      </span>
                    </TableCell>
                    <TableCell>
                      {item.domain || <span className="mapping-empty-value">—</span>}
                    </TableCell>
                    <TableCell>
                      {item.priority ?? <span className="mapping-empty-value">—</span>}
                    </TableCell>
                    <TableCell>
                      <button
                        type="button"
                        className={`switch-control${item.enabled ? " is-on" : ""}`}
                        aria-label={`${item.enabled ? "停用" : "启用"} ${item.sourceTerm}`}
                        aria-pressed={item.enabled}
                        disabled={toggle.isPending}
                        onClick={() => toggle.mutate(item)}
                      >
                        <i />
                      </button>
                    </TableCell>
                    <TableCell>
                      <span className="mapping-remark" title={item.remark || undefined}>
                        {item.remark || "—"}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="table-actions">
                        <button
                          type="button"
                          aria-label={`编辑 ${item.sourceTerm}`}
                          onClick={() => {
                            setEditing(item);
                            setFormOpen(true);
                          }}
                        >
                          <Edit3 aria-hidden="true" />
                        </button>
                        <button
                          type="button"
                          aria-label={`删除 ${item.sourceTerm}`}
                          onClick={() => setDeleting(item)}
                        >
                          <Trash2 aria-hidden="true" />
                        </button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <footer className="console-pagination">
              <span>共 {query.data?.total || 0} 条映射</span>
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

      <MappingDialog
        key={formOpen ? `mapping-${editing?.id ?? "new"}` : "mapping-closed"}
        open={formOpen}
        current={editing}
        busy={save.isPending}
        onClose={() => {
          setFormOpen(false);
          setEditing(undefined);
        }}
        onSubmit={(value) => save.mutate(value)}
      />

      <Dialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(undefined)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除“{deleting?.sourceTerm}”的映射？</DialogTitle>
            <DialogDescription>
              删除后，新问题将不再把该词替换为“{deleting?.targetTerm}”。
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
