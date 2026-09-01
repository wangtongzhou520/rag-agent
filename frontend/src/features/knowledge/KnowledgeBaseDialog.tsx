import { useEffect, useState, type FormEvent } from "react";

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

export function KnowledgeBaseDialog({
  open,
  current,
  busy,
  onClose,
  onSubmit,
}: {
  open: boolean;
  current?: KnowledgeBase;
  busy: boolean;
  onClose: () => void;
  onSubmit: (value: KnowledgeBaseWrite) => void;
}) {
  const [value, setValue] = useState<KnowledgeBaseWrite>({
    name: "",
    embeddingModel: "qwen3.7-text-embedding",
    collectionName: "",
  });
  const [error, setError] = useState("");

  useEffect(() => {
    setValue(
      current
        ? { ...current }
        : { name: "", embeddingModel: "qwen3.7-text-embedding", collectionName: "" },
    );
    setError("");
  }, [current, open]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const normalized = {
      name: value.name.trim(),
      embeddingModel: value.embeddingModel.trim(),
      collectionName: current?.collectionName || value.collectionName.trim(),
    };
    if (
      !normalized.name ||
      !normalized.embeddingModel ||
      (!current && !normalized.collectionName)
    ) {
      setError(
        current
          ? "名称和 Embedding 模型均不能为空"
          : "名称、Collection 和 Embedding 模型均不能为空",
      );
      return;
    }
    onSubmit(normalized);
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{current ? "编辑知识库" : "新建知识库"}</DialogTitle>
            <DialogDescription>
              Collection 创建后不可修改；已有分块文档时，Embedding 模型也不可更换。
            </DialogDescription>
          </DialogHeader>
          <div className="console-form-grid">
            <label>
              <span>知识库名称</span>
              <Input
                autoFocus
                value={value.name}
                onChange={(event) => setValue({ ...value, name: event.target.value })}
                placeholder="例如：产品知识库"
              />
            </label>
            <label>
              <span>Collection Name</span>
              <Input
                disabled={Boolean(current)}
                value={value.collectionName}
                onChange={(event) => setValue({ ...value, collectionName: event.target.value })}
                placeholder="例如：product_knowledge"
              />
            </label>
            <label>
              <span>Embedding 模型</span>
              <Input
                value={value.embeddingModel}
                onChange={(event) => setValue({ ...value, embeddingModel: event.target.value })}
              />
            </label>
            {error && <p className="console-form-error">{error}</p>}
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              取消
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "正在保存…" : "保存知识库"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
