import type { EvalResponse } from "@/features/eval/types";
import { request } from "@/shared/api/client";

export function evaluateQuestion(question: string) {
  return request<EvalResponse>({
    method: "GET",
    url: "/rag/eval",
    params: { question },
  });
}
