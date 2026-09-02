import { useEffect, useState, type FormEvent } from "react";

import {
  MATCH_TYPE_LABELS,
  type MappingMatchType,
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

const emptyValue: QueryTermMappingWrite = {
  sourceTerm: "",
  targetTerm: "",
  matchType: 1,
  priority: 100,
  enabled: true,
  domain: "",
  remark: "",
};

function initialValue(current?: QueryTermMapping): QueryTermMappingWrite {
  return current
    ? {
        sourceTerm: current.sourceTerm,
        targetTerm: current.targetTerm,
        matchType: current.matchType,
        priority: current.priority,
        enabled: current.enabled,
        domain: current.domain || "",
        remark: current.remark || "",
      }
    : { ...emptyValue };
}

export function MappingDialog({
  open,
  current,
  busy,
  onClose,
  onSubmit,
}: {
  open: boolean;
  current?: QueryTermMapping;
  busy: boolean;
  onClose: () => void;
  onSubmit: (value: QueryTermMappingWrite) => void;
}) {
  const [value, setValue] = useState<QueryTermMappingWrite>(() => initialValue(current));
  const [error, setError] = useState("");

  useEffect(() => {
    setValue(initialValue(current));
    setError("");
  }, [current, open]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const sourceTerm = value.sourceTerm.trim();
    const targetTerm = value.targetTerm.trim();
    if (!sourceTerm || !targetTerm) {
      setError("原始词和标准词均不能为空");
      return;
    }
    if (value.priority != null && !Number.isInteger(value.priority)) {
      setError("优先级必须是整数");
      return;
    }
    onSubmit({
      ...value,
      sourceTerm,
      targetTerm,
      domain: value.domain?.trim() || undefined,
      remark: value.remark?.trim() || undefined,
    });
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="mapping-dialog">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{current ? "编辑查询词映射" : "新建查询词映射"}</DialogTitle>
            <DialogDescription>
              将用户常用说法归一化为标准术语。数值越大，匹配时优先级越高。
            </DialogDescription>
          </DialogHeader>

          <div className="mapping-form-grid">
            <label>
              <span>原始词</span>
              <Input
                autoFocus
                aria-label="原始词"
                value={value.sourceTerm}
                onChange={(event) => setValue({ ...value, sourceTerm: event.target.value })}
                placeholder="例如：RAG Agent"
              />
            </label>
            <label>
              <span>标准词</span>
              <Input
                aria-label="标准词"
                value={value.targetTerm}
                onChange={(event) => setValue({ ...value, targetTerm: event.target.value })}
                placeholder="例如：Ragent AI"
              />
            </label>
            <label>
              <span>匹配方式</span>
              <select
                aria-label="匹配方式"
                value={value.matchType}
                onChange={(event) =>
                  setValue({ ...value, matchType: Number(event.target.value) as MappingMatchType })
                }
              >
                {(Object.entries(MATCH_TYPE_LABELS) as [string, string][]).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                    {key === "1" ? "" : "（暂未执行）"}
                  </option>
                ))}
              </select>
              {value.matchType !== 1 && (
                <small className="mapping-field-note">
                  后端已保留该类型，但当前问题归一化仅执行精确匹配。
                </small>
              )}
            </label>
            <label>
              <span>优先级</span>
              <Input
                aria-label="优先级"
                type="number"
                step={1}
                value={value.priority ?? ""}
                onChange={(event) =>
                  setValue({
                    ...value,
                    priority: event.target.value ? Number(event.target.value) : undefined,
                  })
                }
                placeholder="默认 100"
              />
            </label>
            <label className="mapping-form-wide">
              <span>所属领域（可选）</span>
              <Input
                aria-label="所属领域"
                value={value.domain || ""}
                onChange={(event) => setValue({ ...value, domain: event.target.value })}
                placeholder="例如：产品文档"
              />
            </label>
            <label className="mapping-form-wide">
              <span>备注（可选）</span>
              <textarea
                aria-label="备注"
                value={value.remark || ""}
                onChange={(event) => setValue({ ...value, remark: event.target.value })}
                placeholder="说明词汇来源或使用范围"
              />
            </label>
          </div>

          <label className="mapping-enabled-field">
            <input
              type="checkbox"
              checked={value.enabled}
              onChange={(event) => setValue({ ...value, enabled: event.target.checked })}
            />
            <span>
              <strong>启用这条映射</strong>
              <small>停用后配置仍会保留，但不会进入问题改写链路。</small>
            </span>
          </label>
          {error && <p className="console-form-error">{error}</p>}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              取消
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "正在保存…" : "保存映射"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
