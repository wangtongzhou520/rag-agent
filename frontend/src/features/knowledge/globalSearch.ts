import type { KnowledgeBase, KnowledgeDocument } from "@/features/knowledge/types";

export interface ConsoleSearchResult {
  key: string;
  kind: "base" | "document";
  label: string;
  meta: string;
  target: string;
}

const documentStatusNames: Record<string, string> = {
  pending: "待处理",
  running: "处理中",
  success: "已完成",
  failed: "处理失败",
};

export function documentSearchMeta(status: string, chunkCount: number) {
  return `${documentStatusNames[status] || status} · ${chunkCount} 个 Chunk`;
}

export function buildConsoleSearchResults(
  bases: KnowledgeBase[],
  documents: KnowledgeDocument[],
): ConsoleSearchResult[] {
  return [
    ...bases.map((base) => ({
      key: `base-${base.id}`,
      kind: "base" as const,
      label: base.name,
      meta: base.collectionName,
      target: `/admin/knowledge-bases/${base.id}/documents`,
    })),
    ...documents.map((document) => ({
      key: `document-${document.id}`,
      kind: "document" as const,
      label: document.docName,
      meta: documentSearchMeta(document.status, document.chunkCount),
      target: `/admin/documents/${document.id}/chunks`,
    })),
  ];
}
