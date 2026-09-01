import { ExternalLink, FileText, LibraryBig, X } from "lucide-react";

import type { SourceRef } from "@/features/chat/types";
import { cn } from "@/shared/lib/cn";

function safeExternalUrl(value?: string) {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : undefined;
  } catch {
    return undefined;
  }
}

export function SourcePanel({
  sources,
  selected,
  open,
  onSelect,
  onPreview,
  onClose,
}: {
  sources: SourceRef[];
  selected?: number;
  open: boolean;
  onSelect: (index: number) => void;
  onPreview: (source: SourceRef) => void;
  onClose: () => void;
}) {
  return (
    <aside className={cn("source-panel", open && "source-panel--open")} aria-label="回答来源">
      <header>
        <div>
          <span>SOURCE CONTEXT</span>
          <h2>回答来源</h2>
        </div>
        <button type="button" onClick={onClose} aria-label="关闭来源面板">
          <X aria-hidden="true" />
        </button>
      </header>

      {sources.length === 0 ? (
        <div className="source-empty">
          <LibraryBig aria-hidden="true" />
          <strong>来源会出现在这里</strong>
          <p>完成知识检索后，可以逐条核对文档、摘录与原始链接。</p>
        </div>
      ) : (
        <div className="source-list">
          {sources.map((source) => {
            const sourceUrl = safeExternalUrl(source.url);
            return (
              <article
                className={cn("source-card", selected === source.index && "source-card--active")}
                id={`cite-${source.index}`}
                key={`${source.index}-${source.docId}`}
              >
                <button type="button" onClick={() => onSelect(source.index)}>
                  <span className="source-card__index">
                    {String(source.index).padStart(2, "0")}
                  </span>
                  <span className="source-card__meta">
                    <FileText aria-hidden="true" />
                    {source.fileType || source.sourceType}
                  </span>
                  <strong>{source.docName}</strong>
                  {source.excerpt && <p>{source.excerpt}</p>}
                </button>
                {(sourceUrl || /^\d+$/.test(source.docId)) && (
                  <div className="source-card__actions">
                    {/^\d+$/.test(source.docId) && (
                      <button type="button" onClick={() => onPreview(source)}>
                        预览文档
                      </button>
                    )}
                    {sourceUrl && (
                      <a href={sourceUrl} target="_blank" rel="noreferrer">
                        查看原文 <ExternalLink aria-hidden="true" />
                      </a>
                    )}
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </aside>
  );
}
