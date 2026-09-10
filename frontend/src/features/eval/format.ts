import type { EvalResponse } from "@/features/eval/types";

export function routeLabel(result: EvalResponse) {
  const routes = [];
  if (result.hasKb) routes.push("知识库");
  if (result.hasMcpSuccess) routes.push("MCP 成功");
  if (result.needsClarification) routes.push("等待补参");
  if (result.hasMcpFailure) routes.push("MCP 失败");
  return routes.length ? routes.join(" · ") : "未命中证据";
}

export function formatEvalLatency(value: number) {
  return value >= 1000 ? `${(value / 1000).toFixed(2)} s` : `${value} ms`;
}
