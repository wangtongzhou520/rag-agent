import type { DashboardKpi } from "@/features/dashboard/types";

export function formatInteger(value: number) {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(value);
}

export function formatPercent(value: number) {
  return `${value.toFixed(1)}%`;
}

export function formatDashboardDuration(value: number) {
  if (value < 1_000) return `${value} ms`;
  return `${(value / 1_000).toFixed(value < 10_000 ? 2 : 1)} s`;
}

export function describeKpiDelta(kpi: DashboardKpi, comparison: boolean) {
  const sign = kpi.delta > 0 ? "+" : "";
  if (!comparison) return `本周期新增 ${sign}${formatInteger(kpi.delta)}`;
  const percentage = kpi.deltaPct == null ? "暂无环比" : `环比 ${sign}${kpi.deltaPct.toFixed(1)}%`;
  return `${percentage} · ${sign}${formatInteger(kpi.delta)}`;
}

export function formatTrendTime(value: number, granularity: "hour" | "day") {
  return new Date(value).toLocaleString(
    "zh-CN",
    granularity === "hour"
      ? { month: "2-digit", day: "2-digit", hour: "2-digit", hour12: false }
      : { month: "2-digit", day: "2-digit" },
  );
}
