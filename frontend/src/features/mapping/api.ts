import type { QueryTermMapping, QueryTermMappingWrite } from "@/features/mapping/types";
import { request } from "@/shared/api/client";
import { normalizePage, type PageResult } from "@/shared/api/result";

export async function listMappings(current: number, size: number, keyword?: string) {
  const page = await request<Omit<PageResult<QueryTermMapping>, "pages">>({
    method: "GET",
    url: "/mappings",
    params: { current, size, ...(keyword ? { keyword } : {}) },
  });
  return normalizePage(page);
}

export function createMapping(body: QueryTermMappingWrite) {
  return request<string>({ method: "POST", url: "/mappings", data: body });
}

export function updateMapping(id: number, body: QueryTermMappingWrite) {
  return request<null>({ method: "PUT", url: `/mappings/${id}`, data: body });
}

export function deleteMapping(id: number) {
  return request<null>({ method: "DELETE", url: `/mappings/${id}` });
}
