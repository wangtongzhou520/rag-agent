import { FileUp, Link2, SlidersHorizontal, UploadCloud } from "lucide-react";
import { useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";

import type {
  DocumentSourceType,
  IngestionSpecSchema,
  UploadDocumentInput,
} from "@/features/knowledge/types";
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

interface DocumentUploadDialogProps {
  open: boolean;
  schema?: IngestionSpecSchema;
  schemaError?: string;
  busy: boolean;
  onClose: () => void;
  onSubmit: (input: UploadDocumentInput) => void;
}

export function DocumentUploadDialog({
  open,
  schema,
  schemaError,
  busy,
  onClose,
  onSubmit,
}: DocumentUploadDialogProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [sourceType, setSourceType] = useState<DocumentSourceType>("file");
  const [file, setFile] = useState<File>();
  const [sourceLocation, setSourceLocation] = useState("");
  const [parseProfile, setParseProfile] = useState("fast");
  const [maxChars, setMaxChars] = useState(1024);
  const [overlapChars, setOverlapChars] = useState(128);
  const [rowsPerChunk, setRowsPerChunk] = useState(50);
  const [toleranceFactor, setToleranceFactor] = useState(3);
  const [advanced, setAdvanced] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open || !schema) return;
    setParseProfile(schema.parseProfiles[0] || "fast");
    setMaxChars(schema.budget.maxChars.default);
    setOverlapChars(schema.budget.overlapChars.default);
    setRowsPerChunk(schema.budget.rowsPerChunk.default);
    setToleranceFactor(schema.budget.toleranceFactor.default);
  }, [open, schema]);

  const reset = () => {
    setFile(undefined);
    setSourceLocation("");
    setError("");
    setAdvanced(false);
  };

  const close = () => {
    reset();
    onClose();
  };

  const chooseFile = (next?: File) => {
    if (next) {
      setFile(next);
      setError("");
    }
  };

  const onDrop = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    chooseFile(event.dataTransfer.files[0]);
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (sourceType === "file" && !file) return setError("请选择要上传的文档");
    if (sourceType === "url") {
      try {
        const url = new URL(sourceLocation);
        if (!["http:", "https:"].includes(url.protocol)) throw new Error();
      } catch {
        return setError("请输入有效的 HTTP(S) 文档地址");
      }
    }
    if (maxChars !== -1 && overlapChars >= maxChars) {
      return setError("重叠字符数必须小于单块最大字符数");
    }
    if (
      schema &&
      maxChars !== schema.budget.maxChars.whole &&
      (maxChars < schema.budget.maxChars.min || maxChars > schema.budget.maxChars.max)
    ) {
      return setError(
        `单块最大字符数应为 ${schema.budget.maxChars.min}–${schema.budget.maxChars.max}，或使用 -1`,
      );
    }
    if (schema && overlapChars < schema.budget.overlapChars.min) {
      return setError(`重叠字符数不能小于 ${schema.budget.overlapChars.min}`);
    }
    if (
      schema &&
      (rowsPerChunk < schema.budget.rowsPerChunk.min ||
        rowsPerChunk > schema.budget.rowsPerChunk.max)
    ) {
      return setError(
        `表格每块行数应为 ${schema.budget.rowsPerChunk.min}–${schema.budget.rowsPerChunk.max}`,
      );
    }
    if (toleranceFactor < 1) return setError("容差系数必须大于 0");
    setError("");
    onSubmit({
      sourceType,
      file,
      sourceLocation: sourceType === "url" ? sourceLocation.trim() : undefined,
      ingestionSpec: {
        version: schema?.version || 2,
        parseProfile,
        budget: { maxChars, overlapChars, rowsPerChunk, toleranceFactor },
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && close()}>
      <DialogContent className="document-upload-dialog">
        <form onSubmit={submit}>
          <DialogHeader>
            <span className="dialog-kicker">
              <UploadCloud aria-hidden="true" /> INGEST DOCUMENT
            </span>
            <DialogTitle>导入知识文档</DialogTitle>
            <DialogDescription>
              导入后文档处于待处理状态。检查配置无误后，再从列表显式启动分块。
            </DialogDescription>
          </DialogHeader>

          <div className="source-type-switch" aria-label="导入方式">
            <button
              type="button"
              className={sourceType === "file" ? "is-active" : ""}
              onClick={() => setSourceType("file")}
            >
              <FileUp aria-hidden="true" /> 本地文件
            </button>
            <button
              type="button"
              className={sourceType === "url" ? "is-active" : ""}
              onClick={() => setSourceType("url")}
            >
              <Link2 aria-hidden="true" /> URL 导入
            </button>
          </div>

          {sourceType === "file" ? (
            <>
              <input
                ref={inputRef}
                className="sr-only"
                type="file"
                aria-label="选择文档文件"
                onChange={(event) => chooseFile(event.target.files?.[0])}
              />
              <button
                type="button"
                className={`document-dropzone${file ? " document-dropzone--selected" : ""}`}
                onClick={() => inputRef.current?.click()}
                onDragOver={(event) => event.preventDefault()}
                onDrop={onDrop}
              >
                <UploadCloud aria-hidden="true" />
                <strong>{file?.name || "拖放文件到这里，或点击选择"}</strong>
                <span>{file ? formatFileSize(file.size) : "支持后端解析器已启用的文档类型"}</span>
              </button>
            </>
          ) : (
            <label className="console-field">
              <span>文档 URL</span>
              <Input
                aria-label="文档 URL"
                value={sourceLocation}
                placeholder="https://example.com/guide.pdf"
                onChange={(event) => setSourceLocation(event.target.value)}
              />
              <small>服务端会下载并校验内容类型，地址需要可直接访问。</small>
            </label>
          )}

          <button
            type="button"
            className="advanced-toggle"
            aria-expanded={advanced}
            onClick={() => setAdvanced((value) => !value)}
          >
            <SlidersHorizontal aria-hidden="true" />
            分块参数
            <span>{advanced ? "收起" : "使用服务端默认值"}</span>
          </button>

          {advanced && (
            <div className="ingestion-budget-grid">
              <label>
                <span>解析档位</span>
                <select
                  aria-label="解析档位"
                  value={parseProfile}
                  onChange={(event) => setParseProfile(event.target.value)}
                >
                  {(schema?.parseProfiles || ["fast", "fidelity"]).map((profile) => (
                    <option key={profile} value={profile}>
                      {profile}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>单块最大字符</span>
                <Input
                  aria-label="单块最大字符"
                  type="number"
                  value={maxChars}
                  onChange={(event) => setMaxChars(Number(event.target.value))}
                />
              </label>
              <label>
                <span>重叠字符</span>
                <Input
                  aria-label="重叠字符"
                  type="number"
                  min={0}
                  value={overlapChars}
                  onChange={(event) => setOverlapChars(Number(event.target.value))}
                />
              </label>
              <label>
                <span>表格每块行数</span>
                <Input
                  aria-label="表格每块行数"
                  type="number"
                  min={1}
                  value={rowsPerChunk}
                  onChange={(event) => setRowsPerChunk(Number(event.target.value))}
                />
              </label>
              <label>
                <span>容差系数</span>
                <Input
                  aria-label="容差系数"
                  type="number"
                  min={1}
                  value={toleranceFactor}
                  onChange={(event) => setToleranceFactor(Number(event.target.value))}
                />
              </label>
            </div>
          )}

          {(error || schemaError) && (
            <p className="console-form-error" role="alert">
              {error || schemaError}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={close}>
              取消
            </Button>
            <Button type="submit" disabled={busy || !schema}>
              {busy ? "正在导入…" : "创建文档"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}
