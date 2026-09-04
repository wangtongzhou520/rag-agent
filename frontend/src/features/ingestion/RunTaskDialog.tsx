import { useEffect, useState, type FormEvent } from "react";

import type { Pipeline } from "@/features/ingestion/types";
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

export interface RunTaskValue {
  pipelineId: number;
  sourceType: "file" | "url" | "feishu";
  file?: File;
  location?: string;
  fileName?: string;
  vectorSpaceId?: string;
}

export function RunTaskDialog({
  open,
  pipelines,
  initialPipeline,
  busy,
  onClose,
  onSubmit,
}: {
  open: boolean;
  pipelines: Pipeline[];
  initialPipeline?: number;
  busy: boolean;
  onClose: () => void;
  onSubmit: (value: RunTaskValue) => void;
}) {
  const [pipelineId, setPipelineId] = useState(0);
  const [sourceType, setSourceType] = useState<RunTaskValue["sourceType"]>("file");
  const [file, setFile] = useState<File>();
  const [location, setLocation] = useState("");
  const [fileName, setFileName] = useState("");
  const [vectorSpaceId, setVectorSpaceId] = useState("");

  useEffect(() => {
    if (!open) return;
    setPipelineId(initialPipeline || pipelines[0]?.id || 0);
    setSourceType("file");
    setFile(undefined);
    setLocation("");
    setFileName("");
    setVectorSpaceId("");
  }, [initialPipeline, open, pipelines]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit({ pipelineId, sourceType, file, location, fileName, vectorSpaceId });
  };

  return (
    <Dialog open={open} onOpenChange={(value) => !value && onClose()}>
      <DialogContent className="pipeline-run-dialog">
        <DialogHeader>
          <DialogTitle>运行 Pipeline</DialogTitle>
          <DialogDescription>
            同步执行整条链路，完成后可查看每个节点的耗时、摘要和错误。
          </DialogDescription>
        </DialogHeader>
        <form className="pipeline-run-form" onSubmit={submit}>
          <label>
            <span>Pipeline</span>
            <select
              value={pipelineId}
              onChange={(event) => setPipelineId(Number(event.target.value))}
              required
            >
              {pipelines.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>来源类型</span>
            <select
              value={sourceType}
              onChange={(event) => setSourceType(event.target.value as RunTaskValue["sourceType"])}
            >
              <option value="file">本地文件</option>
              <option value="url">URL</option>
              <option value="feishu">飞书文档</option>
            </select>
          </label>
          {sourceType === "file" ? (
            <label className="pipeline-file-field">
              <span>选择文件</span>
              <input type="file" required onChange={(event) => setFile(event.target.files?.[0])} />
            </label>
          ) : (
            <>
              <label>
                <span>来源地址</span>
                <Input
                  type="url"
                  required
                  value={location}
                  onChange={(event) => setLocation(event.target.value)}
                  placeholder="https://…"
                />
              </label>
              <label>
                <span>文件名（可选）</span>
                <Input
                  value={fileName}
                  onChange={(event) => setFileName(event.target.value)}
                  placeholder="用于识别文件类型"
                />
              </label>
            </>
          )}
          <label>
            <span>向量空间</span>
            <Input
              value={vectorSpaceId}
              onChange={(event) => setVectorSpaceId(event.target.value)}
              placeholder="包含 chunker/indexer 时必填"
            />
          </label>
          <p>运行会实际调用解析、Embedding、LLM 和 pgvector；未配置的能力会返回明确失败节点。</p>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              取消
            </Button>
            <Button
              type="submit"
              disabled={busy || !pipelineId || (sourceType === "file" && !file)}
            >
              {busy ? "正在执行…" : "开始运行"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
