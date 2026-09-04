import type { AuditFilters, AuditLog } from "@/features/audit/types";
import { request } from "@/shared/api/client";
import { normalizePage, type PageResult } from "@/shared/api/result";

export async function listAuditLogs(current: number, size: number, filters: AuditFilters) {
  const page = await request<PageResult<AuditLog>>({
    method: "GET",
    url: "/biz-change-logs",
    params: {
      current,
      size,
      ...Object.fromEntries(Object.entries(filters).filter(([, value]) => value)),
    },
  });
  return normalizePage(page);
}

export function getAuditLog(id: number) {
  return request<AuditLog>({ method: "GET", url: `/biz-change-logs/${id}` });
}
