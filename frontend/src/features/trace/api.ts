import type { RagTraceDetail, RagTraceRun, TraceFilters } from "@/features/trace/types";
import { request } from "@/shared/api/client";
import { normalizePage, type PageResult } from "@/shared/api/result";

export async function listTraceRuns(current: number, size: number, filters: TraceFilters) {
  const page = await request<Omit<PageResult<RagTraceRun>, "pages">>({
    method: "GET",
    url: "/rag/traces/runs",
    params: {
      current,
      size,
      ...(filters.traceId ? { traceId: filters.traceId } : {}),
      ...(filters.conversationId ? { conversationId: filters.conversationId } : {}),
      ...(filters.taskId ? { taskId: filters.taskId } : {}),
      ...(filters.status ? { status: filters.status } : {}),
    },
  });
  return normalizePage(page);
}

export function getTraceDetail(traceId: string) {
  return request<RagTraceDetail | null>({
    method: "GET",
    url: `/rag/traces/runs/${traceId}`,
  });
}
