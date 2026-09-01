import type {
  IngestionSpecSchema,
  KnowledgeBase,
  KnowledgeBaseWrite,
  KnowledgeChunk,
  KnowledgeDocument,
  UploadDocumentInput,
} from "@/features/knowledge/types";
import { request } from "@/shared/api/client";
import { normalizePage, type PageResult } from "@/shared/api/result";

export async function listKnowledgeBases(current: number, size: number, name?: string) {
  const page = await request<Omit<PageResult<KnowledgeBase>, "pages">>({
    method: "GET",
    url: "/knowledge-base",
    params: { current, size, ...(name ? { name } : {}) },
  });
  return normalizePage(page);
}

export function getKnowledgeBase(id: number) {
  return request<KnowledgeBase>({ method: "GET", url: `/knowledge-base/${id}` });
}

export function createKnowledgeBase(body: KnowledgeBaseWrite) {
  return request<string>({ method: "POST", url: "/knowledge-base", data: body });
}

export function updateKnowledgeBase(id: number, body: Omit<KnowledgeBaseWrite, "collectionName">) {
  return request<null>({ method: "PUT", url: `/knowledge-base/${id}`, data: body });
}

export function deleteKnowledgeBase(id: number) {
  return request<null>({ method: "DELETE", url: `/knowledge-base/${id}` });
}

export function getIngestionSpecSchema() {
  return request<IngestionSpecSchema>({
    method: "GET",
    url: "/knowledge-base/docs/ingestion-spec-schema",
  });
}

export async function listDocuments(
  kbId: number,
  current: number,
  size: number,
  status?: string,
  keyword?: string,
) {
  const page = await request<Omit<PageResult<KnowledgeDocument>, "pages">>({
    method: "GET",
    url: `/knowledge-base/${kbId}/docs`,
    params: {
      current,
      size,
      ...(status ? { status } : {}),
      ...(keyword ? { keyword } : {}),
    },
  });
  return normalizePage(page);
}

export function getDocument(id: number) {
  return request<KnowledgeDocument>({ method: "GET", url: `/knowledge-base/docs/${id}` });
}

export function uploadDocument(kbId: number, input: UploadDocumentInput) {
  const body = new FormData();
  body.append("sourceType", input.sourceType);
  if (input.file) body.append("file", input.file);
  if (input.sourceLocation) body.append("sourceLocation", input.sourceLocation);
  body.append("ingestionSpec", JSON.stringify(input.ingestionSpec));
  return request<KnowledgeDocument>({
    method: "POST",
    url: `/knowledge-base/${kbId}/docs/upload`,
    data: body,
  });
}

export function triggerDocumentChunk(id: number) {
  return request<null>({ method: "POST", url: `/knowledge-base/docs/${id}/chunk` });
}

export function setDocumentEnabled(id: number, value: boolean) {
  return request<null>({
    method: "PATCH",
    url: `/knowledge-base/docs/${id}/enable`,
    params: { value },
  });
}

export function deleteDocument(id: number) {
  return request<null>({ method: "DELETE", url: `/knowledge-base/docs/${id}` });
}

export async function listChunks(docId: number, current: number, size: number, enabled?: boolean) {
  const page = await request<Omit<PageResult<KnowledgeChunk>, "pages">>({
    method: "GET",
    url: `/knowledge-base/docs/${docId}/chunks`,
    params: { current, size, ...(enabled === undefined ? {} : { enabled }) },
  });
  return normalizePage(page);
}

export function updateChunk(docId: number, chunkId: string, content: string) {
  return request<null>({
    method: "PUT",
    url: `/knowledge-base/docs/${docId}/chunks/${chunkId}`,
    data: { content },
  });
}

export function setChunkEnabled(docId: number, chunkId: string, value: boolean) {
  return request<null>({
    method: "PATCH",
    url: `/knowledge-base/docs/${docId}/chunks/${chunkId}/enable`,
    params: { value },
  });
}

export function batchSetChunksEnabled(docId: number, chunkIds: string[], value: boolean) {
  return request<null>({
    method: "PATCH",
    url: `/knowledge-base/docs/${docId}/chunks/batch-enable`,
    params: { value },
    data: { chunkIds },
  });
}

export function deleteChunk(docId: number, chunkId: string) {
  return request<null>({
    method: "DELETE",
    url: `/knowledge-base/docs/${docId}/chunks/${chunkId}`,
  });
}
