import type { EvalResponse } from "@/features/eval/types";
import { request } from "@/shared/api/client";

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
