import type { EvalReportDetail, EvalReportSummary, EvalResponse } from "@/features/eval/types";
import { request } from "@/shared/api/client";
import { normalizePage, type PageResult } from "@/shared/api/result";

export function evaluateQuestion({
  question,
  includeAnswer,
}: {
  question: string;
  includeAnswer: boolean;
}) {
  return request<EvalResponse>({
    method: "GET",
    url: "/rag/eval",
    params: { question, includeAnswer },
  });
}

export async function listEvalReports(size = 8) {
  const page = await request<Omit<PageResult<EvalReportSummary>, "pages">>({
    method: "GET",
    url: "/rag/eval/reports",
    params: { current: 1, size },
  });
  return normalizePage(page);
}

export function getEvalReport(reportId: string) {
  return request<EvalReportDetail | null>({
    method: "GET",
    url: `/rag/eval/reports/${reportId}`,
  });
}
