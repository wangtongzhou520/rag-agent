import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronRight,
  Edit3,
  FolderTree,
  Plus,
  Power,
  PowerOff,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useState, type MouseEvent } from "react";
import { toast } from "sonner";

import { listKnowledgeBases } from "@/features/knowledge/api";
import {
  batchIntentNodes,
  createIntentNode,
  deleteIntentNode,
  listIntentTree,
  updateIntentNode,
} from "@/features/intent/api";
import { IntentNodeDialog } from "@/features/intent/IntentNodeDialog";
import { flattenIntentTree, intentBranchIds, intentTreeStats } from "@/features/intent/tree";
import type { IntentNode, IntentNodeWrite } from "@/features/intent/types";
import { Button } from "@/shared/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/Dialog";

type BatchAction = "enable" | "disable" | "delete";

export function IntentTreePage() {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState<number[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [activeId, setActiveId] = useState<number>();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<IntentNode>();
  const [parent, setParent] = useState<IntentNode>();
  const [deleting, setDeleting] = useState<IntentNode>();
  const [batchAction, setBatchAction] = useState<BatchAction>();

  const query = useQuery({ queryKey: ["intent-tree"], queryFn: listIntentTree });
  const basesQuery = useQuery({
    queryKey: ["knowledge-bases", "intent-options"],
    queryFn: () => listKnowledgeBases(1, 100),
  });
  const nodes = useMemo(() => flattenIntentTree(query.data || []), [query.data]);
  const active = nodes.find((node) => node.id === activeId);
  const stats = intentTreeStats(query.data || []);

  useEffect(() => {
    if (!query.data) return;
    setExpanded((ids) => (ids.length ? ids : query.data.map((node) => node.id)));
    setActiveId((id) => (id && nodes.some((node) => node.id === id) ? id : nodes[0]?.id));
    setSelectedIds((ids) => ids.filter((id) => nodes.some((node) => node.id === id)));
  }, [nodes, query.data]);

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["intent-tree"] });
  const save = useMutation({
    mutationFn: (value: IntentNodeWrite) =>
      editing ? updateIntentNode(editing.id, value) : createIntentNode(value),
    onSuccess: () => {
      toast.success(editing ? "意图节点已更新" : "意图节点已创建");
      setFormOpen(false);
      setEditing(undefined);
      setParent(undefined);
      void refresh();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "节点保存失败"),
  });
  const remove = useMutation({
    mutationFn: (id: number) => deleteIntentNode(id),
    onSuccess: () => {
      toast.success("意图节点已删除");
      setDeleting(undefined);
      void refresh();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "节点删除失败"),
  });
  const batch = useMutation({
    mutationFn: ({ action, ids }: { action: BatchAction; ids: number[] }) =>
      batchIntentNodes(action, ids),
    onSuccess: (_, input) => {
      const actionName = { enable: "启用", disable: "停用", delete: "删除" }[input.action];
      toast.success(`已${actionName} ${input.ids.length} 个节点`);
      setSelectedIds([]);
      setBatchAction(undefined);
      void refresh();
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "批量操作失败"),
  });

  const openCreate = (seedParent?: IntentNode) => {
    setEditing(undefined);
    setParent(seedParent);
    setFormOpen(true);
  };
  const openEdit = (node: IntentNode) => {
    setParent(undefined);
    setEditing(node);
    setFormOpen(true);
  };
  const runBatch = (action: BatchAction) => {
    if (!selectedIds.length) return toast.error("请先选择节点");
    if (selectedIds.length > 500) return toast.error("一次最多操作 500 个节点");
    if (action === "delete") setBatchAction(action);
    else batch.mutate({ action, ids: selectedIds });
  };
  const selectNode = (id: number, checked: boolean) => {
    if (!checked) return setSelectedIds((ids) => ids.filter((item) => item !== id));
    if (selectedIds.includes(id)) return;
    if (selectedIds.length >= 500) return toast.error("一次最多选择 500 个节点");
    setSelectedIds([...selectedIds, id]);
  };
  const selectBranch = (node: IntentNode) => {
    const next = [...new Set([...selectedIds, ...intentBranchIds(node)])];
    if (next.length > 500) return toast.error("一次最多选择 500 个节点");
    setSelectedIds(next);
  };

  return (
    <main className="console-content intent-page">
      <header className="console-page-header">
        <div className="console-page-heading">
          <p>问题理解</p>
          <h1>意图树</h1>
          <span>维护问题分类层级，并为主题节点指定知识库、系统回答或工具调用。</span>
        </div>
        <Button onClick={() => openCreate()}>
          <Plus aria-hidden="true" /> 新建领域
        </Button>
      </header>

      <section className="intent-summary" aria-label="意图树概况">
        <span>
          节点 <strong>{stats.total}</strong>
        </span>
        <span>
          已启用 <strong>{stats.enabled}</strong>
        </span>
        <span>
          主题 <strong>{stats.leaves}</strong>
        </span>
        <Button variant="ghost" onClick={() => void query.refetch()}>
          <RefreshCw aria-hidden="true" /> 刷新
        </Button>
      </section>

      {selectedIds.length > 0 && (
        <section className="intent-batch-bar" aria-live="polite">
          <span>已选择 {selectedIds.length} 个节点</span>
          <div>
            <Button variant="ghost" onClick={() => runBatch("enable")}>
              <Power aria-hidden="true" /> 启用
            </Button>
            <Button variant="ghost" onClick={() => runBatch("disable")}>
              <PowerOff aria-hidden="true" /> 停用
            </Button>
            <Button variant="ghost" className="danger-text" onClick={() => runBatch("delete")}>
              <Trash2 aria-hidden="true" /> 删除
            </Button>
            <Button variant="ghost" onClick={() => setSelectedIds([])}>
              取消选择
            </Button>
          </div>
        </section>
      )}

      <section className="intent-workbench">
        <div className="intent-tree-panel">
          <header>
            <div>
              <strong>分类结构</strong>
              <span>领域 / 分类 / 主题</span>
            </div>
          </header>
          {query.isLoading ? (
            <div className="intent-panel-state">正在读取意图树…</div>
          ) : query.isError ? (
            <div className="intent-panel-state intent-panel-state--error">
              {query.error instanceof Error ? query.error.message : "意图树加载失败"}
            </div>
          ) : !query.data?.length ? (
            <div className="intent-panel-state">
              <FolderTree aria-hidden="true" />
              <strong>还没有意图节点</strong>
              <span>先创建一个领域节点。</span>
            </div>
          ) : (
            <div className="intent-tree-list" role="tree">
              {query.data.map((node) => (
                <IntentTreeRow
                  key={node.id}
                  node={node}
                  depth={0}
                  activeId={activeId}
                  expanded={expanded}
                  selectedIds={selectedIds}
                  onActivate={setActiveId}
                  onExpand={(id) =>
                    setExpanded((ids) =>
                      ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id],
                    )
                  }
                  onSelect={selectNode}
                />
              ))}
            </div>
          )}
        </div>

        <div className="intent-detail-panel">
          {active ? (
            <>
              <header className="intent-detail-header">
                <div>
                  <span className={`intent-level intent-level--${active.level}`}>
                    {levelName(active.level)}
                  </span>
                  <span className="intent-kind">{kindName(active.kind)}</span>
                  {!active.enabled && <span className="intent-disabled">已停用</span>}
                </div>
                <div>
                  <Button
                    variant="ghost"
                    aria-label={`编辑 ${active.name}`}
                    onClick={() => openEdit(active)}
                  >
                    <Edit3 aria-hidden="true" /> 编辑
                  </Button>
                  <Button
                    variant="ghost"
                    className="danger-text"
                    aria-label={`删除 ${active.name}`}
                    onClick={() => setDeleting(active)}
                  >
                    <Trash2 aria-hidden="true" /> 删除
                  </Button>
                </div>
              </header>
              <div className="intent-detail-title">
                <h2>{active.name}</h2>
                <code>{active.intentCode}</code>
                <p>{active.description || "暂无语义描述"}</p>
              </div>
              <dl className="intent-detail-grid">
                <div>
                  <dt>完整路径</dt>
                  <dd>{active.fullPath || active.name}</dd>
                </div>
                <div>
                  <dt>检索深度</dt>
                  <dd>{active.topK ? `Top ${active.topK}` : "使用系统默认值"}</dd>
                </div>
                {active.kind === 2 && (
                  <div>
                    <dt>MCP 工具</dt>
                    <dd>{active.mcpToolId || "未配置"}</dd>
                  </div>
                )}
              </dl>
              {active.kind === 0 && (
                <section className="intent-detail-section">
                  <h3>绑定 Collection</h3>
                  {effectiveCollections(active).length ? (
                    <ul className="intent-chip-list">
                      {effectiveCollections(active).map((name) => (
                        <li key={name}>{name}</li>
                      ))}
                    </ul>
                  ) : (
                    <p>未绑定知识库</p>
                  )}
                </section>
              )}
              <section className="intent-detail-section">
                <h3>示例问题</h3>
                {active.examples.length ? (
                  <ul className="intent-example-list">
                    {active.examples.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p>暂无示例问题</p>
                )}
              </section>
              <footer className="intent-detail-actions">
                {active.level < 2 && (
                  <Button variant="secondary" onClick={() => openCreate(active)}>
                    <Plus aria-hidden="true" /> 新建子节点
                  </Button>
                )}
                <Button variant="ghost" onClick={() => selectBranch(active)}>
                  选择整个分支
                </Button>
                <Button
                  variant="ghost"
                  onClick={() =>
                    batch.mutate({
                      action: active.enabled ? "disable" : "enable",
                      ids: [active.id],
                    })
                  }
                >
                  {active.enabled ? "停用节点" : "启用节点"}
                </Button>
              </footer>
            </>
          ) : (
            <div className="intent-panel-state">
              <FolderTree aria-hidden="true" />
              <strong>选择一个节点</strong>
              <span>右侧会显示配置详情。</span>
            </div>
          )}
        </div>
      </section>

      <IntentNodeDialog
        key={editing ? `edit-${editing.id}` : parent ? `child-${parent.id}` : "root"}
        open={formOpen}
        current={editing}
        parent={parent}
        nodes={nodes}
        knowledgeBases={basesQuery.data?.records || []}
        busy={save.isPending}
        onClose={() => setFormOpen(false)}
        onSubmit={(value) => save.mutate(value)}
      />
      <Dialog open={Boolean(deleting)} onOpenChange={(open) => !open && setDeleting(undefined)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除“{deleting?.name}”？</DialogTitle>
            <DialogDescription>
              只删除当前节点。若存在子节点，子节点会因失去父节点而成为根节点，请先确认层级影响。
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
      <Dialog
        open={batchAction === "delete"}
        onOpenChange={(open) => !open && setBatchAction(undefined)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除所选 {selectedIds.length} 个节点？</DialogTitle>
            <DialogDescription>
              批量删除不会自动包含未选中的子节点。失去父节点的子节点会成为根节点。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setBatchAction(undefined)}>
              取消
            </Button>
            <Button
              className="bg-[var(--danger)] hover:bg-red-700"
              disabled={batch.isPending}
              onClick={() => batch.mutate({ action: "delete", ids: selectedIds })}
            >
              确认删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}

function IntentTreeRow({
  node,
  depth,
  activeId,
  expanded,
  selectedIds,
  onActivate,
  onExpand,
  onSelect,
}: {
  node: IntentNode;
  depth: number;
  activeId?: number;
  expanded: number[];
  selectedIds: number[];
  onActivate: (id: number) => void;
  onExpand: (id: number) => void;
  onSelect: (id: number, checked: boolean) => void;
}) {
  const hasChildren = node.children.length > 0;
  const open = expanded.includes(node.id);
  const stop = (event: MouseEvent) => event.stopPropagation();
  return (
    <>
      <div
        className={`intent-tree-row${activeId === node.id ? " is-active" : ""}${!node.enabled ? " is-disabled" : ""}`}
        role="treeitem"
        aria-selected={activeId === node.id}
        aria-expanded={hasChildren ? open : undefined}
        style={{ paddingLeft: 10 + depth * 22 }}
        onClick={() => onActivate(node.id)}
      >
        <input
          type="checkbox"
          aria-label={`选择 ${node.name}`}
          checked={selectedIds.includes(node.id)}
          onClick={stop}
          onChange={(event) => onSelect(node.id, event.target.checked)}
        />
        <button
          type="button"
          className="intent-tree-expand"
          aria-label={`${open ? "收起" : "展开"} ${node.name}`}
          disabled={!hasChildren}
          onClick={(event) => {
            stop(event);
            if (hasChildren) onExpand(node.id);
          }}
        >
          {hasChildren ? open ? <ChevronDown /> : <ChevronRight /> : <span />}
        </button>
        <span className={`intent-tree-marker intent-tree-marker--${node.level}`} />
        <span className="intent-tree-name">
          {node.name}
          <small>{levelName(node.level)}</small>
        </span>
        <span className="intent-tree-kind">{kindName(node.kind)}</span>
      </div>
      {hasChildren && open && (
        <div role="group">
          {node.children.map((child) => (
            <IntentTreeRow
              key={child.id}
              node={child}
              depth={depth + 1}
              activeId={activeId}
              expanded={expanded}
              selectedIds={selectedIds}
              onActivate={onActivate}
              onExpand={onExpand}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </>
  );
}

function levelName(level: number) {
  return ["领域", "分类", "主题"][level] || "节点";
}
function kindName(kind: number) {
  return ["知识库", "系统", "MCP"][kind] || "未知";
}
function effectiveCollections(node: IntentNode) {
  return [
    ...new Set([...node.collectionNames, ...(node.collectionName ? [node.collectionName] : [])]),
  ];
}
