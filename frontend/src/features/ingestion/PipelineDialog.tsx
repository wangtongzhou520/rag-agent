import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import type { NodeType, Pipeline, PipelineNode, PipelineWrite } from "@/features/ingestion/types";
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

const nodeNames: Record<NodeType, string> = {
  fetcher: "获取文件",
  parser: "解析内容",
  enhancer: "文档增强",
  chunker: "分块与向量化",
  enricher: "分块富集",
  indexer: "写入索引",
};

const defaults: Record<NodeType, Record<string, unknown>> = {
  fetcher: {},
  parser: { rules: [{ mimeType: "ALL", options: {} }] },
  enhancer: { tasks: [] },
  chunker: { chunkSize: 1024, overlapSize: 128, rowsPerChunk: 50 },
  enricher: { attachDocumentMetadata: true, tasks: [] },
  indexer: { metadataFields: [] },
};

interface DraftNode {
  key: string;
  nodeId: string;
  nodeType: NodeType;
  settings: string;
  condition: string;
}

function fromPipeline(current?: Pipeline): DraftNode[] {
  return (current?.nodes || []).map((node) => ({
    key: `${node.id || node.nodeId}`,
    nodeId: node.nodeId,
    nodeType: node.nodeType,
    settings: JSON.stringify(node.settings || {}, null, 2),
    condition: node.condition == null ? "" : JSON.stringify(node.condition, null, 2),
  }));
}

function starterNodes(): DraftNode[] {
  return (["fetcher", "parser", "chunker", "indexer"] as NodeType[]).map((nodeType, index) => ({
    key: `${nodeType}-${Date.now()}-${index}`,
    nodeId: nodeType,
    nodeType,
    settings: JSON.stringify(defaults[nodeType], null, 2),
    condition: "",
  }));
}

export function PipelineDialog({
  open,
  current,
  busy,
  onClose,
  onSubmit,
}: {
  open: boolean;
  current?: Pipeline;
  busy: boolean;
  onClose: () => void;
  onSubmit: (value: PipelineWrite) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [nodes, setNodes] = useState<DraftNode[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setName(current?.name || "");
    setDescription(current?.description || "");
    setNodes(current ? fromPipeline(current) : starterNodes());
    setError("");
  }, [current, open]);

  const patchNode = (index: number, patch: Partial<DraftNode>) =>
    setNodes((value) =>
      value.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)),
    );
  const move = (index: number, offset: number) => {
    const target = index + offset;
    if (target < 0 || target >= nodes.length) return;
    const next = [...nodes];
    [next[index], next[target]] = [next[target], next[index]];
    setNodes(next);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    try {
      if (!name.trim()) throw new Error("请填写 Pipeline 名称");
      if (!nodes.length) throw new Error("至少保留一个节点");
      const ids = nodes.map((item) => item.nodeId.trim());
      if (ids.some((item) => !item)) throw new Error("节点 ID 不能为空");
      if (new Set(ids).size !== ids.length) throw new Error("节点 ID 不能重复");
      const value: PipelineNode[] = nodes.map((item, index) => ({
        nodeId: item.nodeId.trim(),
        nodeType: item.nodeType,
        settings: JSON.parse(item.settings || "{}") as Record<string, unknown>,
        condition: item.condition.trim()
          ? (JSON.parse(item.condition) as Record<string, unknown>)
          : null,
        nextNodeId: nodes[index + 1]?.nodeId.trim() || null,
      }));
      setError("");
      onSubmit({ name: name.trim(), description: description.trim(), nodes: value });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "节点配置格式不正确");
    }
  };

  return (
    <Dialog open={open} onOpenChange={(value) => !value && onClose()}>
      <DialogContent className="pipeline-editor-dialog">
        <DialogHeader>
          <DialogTitle>{current ? "编辑 Pipeline" : "新建 Pipeline"}</DialogTitle>
          <DialogDescription>
            节点从上到下依次执行。失败会立即中断，条件不满足会记录为跳过。
          </DialogDescription>
        </DialogHeader>
        <form className="pipeline-editor" onSubmit={submit}>
          <div className="pipeline-basic-fields">
            <label>
              <span>名称</span>
              <Input
                value={name}
                onChange={(event) => setName(event.target.value)}
                maxLength={128}
              />
            </label>
            <label>
              <span>说明</span>
              <Input
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="这条入库链路用于什么场景"
                maxLength={512}
              />
            </label>
          </div>
          <section className="pipeline-node-editor">
            <header>
              <div>
                <strong>执行节点</strong>
                <span>{nodes.length} 个节点</span>
              </div>
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  const nodeType: NodeType = "parser";
                  setNodes((value) => [
                    ...value,
                    {
                      key: `node-${Date.now()}`,
                      nodeId: `node-${value.length + 1}`,
                      nodeType,
                      settings: JSON.stringify(defaults[nodeType], null, 2),
                      condition: "",
                    },
                  ]);
                }}
              >
                <Plus aria-hidden="true" /> 添加节点
              </Button>
            </header>
            <div className="pipeline-node-list">
              {nodes.map((node, index) => (
                <article className="pipeline-node-row" key={node.key}>
                  <div className="pipeline-node-sequence">
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    {index < nodes.length - 1 && <i />}
                  </div>
                  <div className="pipeline-node-body">
                    <div className="pipeline-node-fields">
                      <label>
                        <span>节点类型</span>
                        <select
                          aria-label={`节点 ${index + 1} 类型`}
                          value={node.nodeType}
                          onChange={(event) => {
                            const nodeType = event.target.value as NodeType;
                            patchNode(index, {
                              nodeType,
                              settings: JSON.stringify(defaults[nodeType], null, 2),
                            });
                          }}
                        >
                          {Object.entries(nodeNames).map(([value, label]) => (
                            <option key={value} value={value}>
                              {label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span>节点 ID</span>
                        <Input
                          aria-label={`节点 ${index + 1} ID`}
                          value={node.nodeId}
                          onChange={(event) => patchNode(index, { nodeId: event.target.value })}
                        />
                      </label>
                      <div className="pipeline-node-actions">
                        <button
                          type="button"
                          aria-label="上移节点"
                          disabled={!index}
                          onClick={() => move(index, -1)}
                        >
                          <ArrowUp />
                        </button>
                        <button
                          type="button"
                          aria-label="下移节点"
                          disabled={index === nodes.length - 1}
                          onClick={() => move(index, 1)}
                        >
                          <ArrowDown />
                        </button>
                        <button
                          type="button"
                          aria-label="删除节点"
                          onClick={() =>
                            setNodes((value) => value.filter((_, itemIndex) => itemIndex !== index))
                          }
                        >
                          <Trash2 />
                        </button>
                      </div>
                    </div>
                    <div className="pipeline-json-fields">
                      <label>
                        <span>节点参数（JSON）</span>
                        <textarea
                          value={node.settings}
                          onChange={(event) => patchNode(index, { settings: event.target.value })}
                          spellCheck={false}
                        />
                      </label>
                      <label>
                        <span>执行条件（JSON，可空）</span>
                        <textarea
                          value={node.condition}
                          onChange={(event) => patchNode(index, { condition: event.target.value })}
                          placeholder={'{"field":"source.type","operator":"eq","value":"url"}'}
                          spellCheck={false}
                        />
                      </label>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </section>
          {error && <p className="pipeline-form-error">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              取消
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "正在保存…" : "保存 Pipeline"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
