import { Plus, X } from "lucide-react";
import { useEffect, useState, type FormEvent, type KeyboardEvent } from "react";

import type { KnowledgeBase } from "@/features/knowledge/types";
import type { IntentKind, IntentLevel, IntentNode, IntentNodeWrite } from "@/features/intent/types";
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

const emptyValue: IntentNodeWrite = {
  intentCode: "",
  name: "",
  level: 0,
  examples: [],
  collectionNames: [],
  kind: 0,
  enabled: true,
};

function initialValue(current?: IntentNode, parent?: IntentNode): IntentNodeWrite {
  if (current) {
    const collections = [
      ...current.collectionNames,
      ...(current.collectionName ? [current.collectionName] : []),
    ];
    return {
      kbId: current.kbId,
      intentCode: current.intentCode,
      name: current.name,
      level: current.level,
      parentCode: current.parentCode,
      description: current.description,
      examples: [...current.examples],
      collectionName: current.collectionName,
      collectionNames: [...new Set(collections)],
      kind: current.kind,
      mcpToolId: current.mcpToolId,
      topK: current.topK,
      enabled: current.enabled,
    };
  }
  if (parent) {
    return {
      ...emptyValue,
      examples: [],
      collectionNames: [],
      intentCode: `${parent.intentCode}.`,
      level: Math.min(parent.level + 1, 2) as IntentLevel,
      parentCode: parent.intentCode,
    };
  }
  return { ...emptyValue, examples: [], collectionNames: [] };
}

export function IntentNodeDialog({
  open,
  current,
  parent,
  nodes,
  knowledgeBases,
  busy,
  onClose,
  onSubmit,
}: {
  open: boolean;
  current?: IntentNode;
  parent?: IntentNode;
  nodes: IntentNode[];
  knowledgeBases: KnowledgeBase[];
  busy: boolean;
  onClose: () => void;
  onSubmit: (value: IntentNodeWrite) => void;
}) {
  const [value, setValue] = useState<IntentNodeWrite>(() => initialValue(current, parent));
  const [example, setExample] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setValue(initialValue(current, parent));
    setExample("");
    setError("");
  }, [current, open, parent]);

  const addExample = () => {
    const normalized = example.trim();
    if (!normalized || value.examples.includes(normalized)) return;
    setValue({ ...value, examples: [...value.examples, normalized] });
    setExample("");
  };

  const exampleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    addExample();
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const intentCode = value.intentCode.trim();
    const name = value.name.trim();
    if (!intentCode || !name) return setError("节点名称和意图编码不能为空");
    if (value.level > 0 && !value.parentCode) return setError("请选择父节点");
    if (value.kind === 2 && !value.mcpToolId?.trim()) return setError("MCP 节点必须填写工具 ID");
    if (value.topK !== undefined && value.topK < 1) return setError("Top K 必须是正整数");
    if (value.kind === 0 && value.level === 2 && !value.collectionNames.length) {
      return setError("知识库意图至少绑定一个 Collection");
    }

    const collections = value.kind === 0 && value.level === 2 ? value.collectionNames : [];
    onSubmit({
      ...value,
      intentCode,
      name,
      parentCode: value.level === 0 ? undefined : value.parentCode,
      description: value.description?.trim() || undefined,
      examples: value.examples,
      kbId: collections.length ? value.kbId : undefined,
      collectionName: collections[0],
      collectionNames: collections,
      mcpToolId: value.kind === 2 ? value.mcpToolId?.trim() : undefined,
      topK: value.topK || undefined,
    });
  };

  const parentOptions = nodes.filter((node) => node.level === value.level - 1);

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="intent-node-dialog">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>
              {current ? "编辑意图节点" : parent ? `在“${parent.name}”下新建节点` : "新建意图节点"}
            </DialogTitle>
            <DialogDescription>
              三级结构为领域、分类和主题。主题节点用于决定检索知识库、系统回答或 MCP 工具。
            </DialogDescription>
          </DialogHeader>

          <div className="intent-form-grid">
            <label>
              <span>节点名称</span>
              <Input
                autoFocus
                aria-label="节点名称"
                value={value.name}
                onChange={(event) => setValue({ ...value, name: event.target.value })}
                placeholder="例如：安装与部署"
              />
            </label>
            <label>
              <span>意图编码</span>
              <Input
                aria-label="意图编码"
                value={value.intentCode}
                onChange={(event) => setValue({ ...value, intentCode: event.target.value })}
                placeholder="例如：product.guide.install"
              />
            </label>
            <label>
              <span>节点层级</span>
              <select
                aria-label="节点层级"
                value={value.level}
                onChange={(event) =>
                  setValue({
                    ...value,
                    level: Number(event.target.value) as IntentLevel,
                    parentCode: undefined,
                  })
                }
              >
                <option value={0}>领域</option>
                <option value={1}>分类</option>
                <option value={2}>主题</option>
              </select>
            </label>
            {value.level > 0 && (
              <label>
                <span>父节点</span>
                <select
                  aria-label="父节点"
                  value={value.parentCode || ""}
                  onChange={(event) =>
                    setValue({ ...value, parentCode: event.target.value || undefined })
                  }
                >
                  <option value="">请选择</option>
                  {parentOptions.map((node) => (
                    <option key={node.id} value={node.intentCode}>
                      {node.fullPath || node.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <label>
              <span>处理类型</span>
              <select
                aria-label="处理类型"
                value={value.kind}
                onChange={(event) =>
                  setValue({ ...value, kind: Number(event.target.value) as IntentKind })
                }
              >
                <option value={0}>知识库检索</option>
                <option value={1}>系统回答</option>
                <option value={2}>MCP 工具</option>
              </select>
            </label>
            <label>
              <span>Top K（可选）</span>
              <Input
                aria-label="Top K"
                type="number"
                min={1}
                value={value.topK ?? ""}
                onChange={(event) =>
                  setValue({
                    ...value,
                    topK: event.target.value ? Number(event.target.value) : undefined,
                  })
                }
                placeholder="使用系统默认值"
              />
            </label>
            <label className="intent-form-wide">
              <span>语义描述</span>
              <textarea
                aria-label="语义描述"
                value={value.description || ""}
                onChange={(event) => setValue({ ...value, description: event.target.value })}
                placeholder="说明这个节点覆盖什么问题，帮助模型准确分类。"
              />
            </label>
          </div>

          {value.kind === 0 && value.level === 2 && (
            <fieldset className="collection-selector">
              <legend>绑定知识库</legend>
              {knowledgeBases.length === 0 ? (
                <p>暂无可绑定的知识库，请先创建知识库。</p>
              ) : (
                knowledgeBases.map((base) => {
                  const checked = value.collectionNames.includes(base.collectionName);
                  return (
                    <label key={base.id}>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(event) =>
                          setValue({
                            ...value,
                            kbId: event.target.checked
                              ? value.kbId || base.id
                              : value.kbId === base.id
                                ? undefined
                                : value.kbId,
                            collectionNames: event.target.checked
                              ? [...value.collectionNames, base.collectionName]
                              : value.collectionNames.filter(
                                  (name) => name !== base.collectionName,
                                ),
                          })
                        }
                      />
                      <span>
                        <strong>{base.name}</strong>
                        <small>{base.collectionName}</small>
                      </span>
                    </label>
                  );
                })
              )}
            </fieldset>
          )}

          {value.kind === 2 && (
            <label className="intent-mcp-field">
              <span>MCP 工具 ID</span>
              <Input
                aria-label="MCP 工具 ID"
                value={value.mcpToolId || ""}
                onChange={(event) => setValue({ ...value, mcpToolId: event.target.value })}
                placeholder="例如：internal:stock_query"
              />
            </label>
          )}

          <section className="examples-editor">
            <label htmlFor="intent-example">示例问题</label>
            <div>
              <Input
                id="intent-example"
                aria-label="示例问题"
                value={example}
                onChange={(event) => setExample(event.target.value)}
                onKeyDown={exampleKeyDown}
                placeholder="输入示例后按 Enter"
              />
              <Button type="button" variant="secondary" onClick={addExample}>
                <Plus aria-hidden="true" /> 添加
              </Button>
            </div>
            {value.examples.length > 0 && (
              <ul>
                {value.examples.map((item) => (
                  <li key={item}>
                    {item}
                    <button
                      type="button"
                      aria-label={`删除示例 ${item}`}
                      onClick={() =>
                        setValue({
                          ...value,
                          examples: value.examples.filter((value) => value !== item),
                        })
                      }
                    >
                      <X />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <label className="intent-enabled-field">
            <input
              type="checkbox"
              checked={value.enabled}
              onChange={(event) => setValue({ ...value, enabled: event.target.checked })}
            />
            <span>
              <strong>启用节点</strong>
              <small>停用后不会参与问题分类，但仍保留在管理树中。</small>
            </span>
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
              {busy ? "正在保存…" : "保存节点"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
