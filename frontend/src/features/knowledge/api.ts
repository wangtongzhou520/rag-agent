import type { KnowledgeBase, KnowledgeBaseWrite } from "@/features/knowledge/types";
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

export function createKnowledgeBase(body: KnowledgeBaseWrite) {
  return request<string>({ method: "POST", url: "/knowledge-base", data: body });
}

export function updateKnowledgeBase(id: number, body: Omit<KnowledgeBaseWrite, "collectionName">) {
  return request<null>({ method: "PUT", url: `/knowledge-base/${id}`, data: body });
}

export function deleteKnowledgeBase(id: number) {
  return request<null>({ method: "DELETE", url: `/knowledge-base/${id}` });
}
