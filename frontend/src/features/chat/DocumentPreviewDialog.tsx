import { FileText } from "lucide-react";
import { useEffect, useState } from "react";

import { getDocumentPreview } from "@/features/chat/api";
import { MarkdownAnswer } from "@/features/chat/MarkdownAnswer";
import type { SourceRef } from "@/features/chat/types";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/Dialog";

export function DocumentPreviewDialog({
  source,
  onClose,
}: {
  source?: SourceRef;
  onClose: () => void;
}) {
  const [content, setContent] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!source) return;
    let current = true;
    setContent("");
    setError("");
    setLoading(true);

    void getDocumentPreview(source.docId)
      .then((preview) => {
        if (current) setContent(preview);
      })
      .catch((reason) => {
        if (current) setError(reason instanceof Error ? reason.message : "文档预览加载失败");
      })
      .finally(() => {
        if (current) setLoading(false);
      });

    return () => {
      current = false;
    };
  }, [source]);

  return (
    <Dialog open={Boolean(source)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="document-preview-dialog">
        <DialogHeader>
          <span className="document-preview-dialog__kicker">
            <FileText aria-hidden="true" /> DOCUMENT PREVIEW
          </span>
          <DialogTitle>{source?.docName || "文档预览"}</DialogTitle>
          <DialogDescription>
            来源 {source?.index} · {source?.fileType || source?.sourceType} · Doc ID {source?.docId}
          </DialogDescription>
        </DialogHeader>
        <div className="document-preview-dialog__body">
          {loading && <p className="document-preview-status">正在读取文档分块…</p>}
          {error && <p className="document-preview-error">{error}</p>}
          {!loading && !error && content && (
            <MarkdownAnswer onCitation={() => undefined}>{content}</MarkdownAnswer>
          )}
          {!loading && !error && !content && (
            <p className="document-preview-status">文档暂无可预览内容</p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
