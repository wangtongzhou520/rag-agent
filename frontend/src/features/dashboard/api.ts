import type {
  DashboardMetric,
  DashboardOverview,
  DashboardPerformance,
  DashboardTrends,
} from "@/features/dashboard/types";
import { request } from "@/shared/api/client";

export function getDashboardOverview(window: string) {
  return request<DashboardOverview>({
    method: "GET",
    url: "/admin/dashboard/overview",
    params: { window },
  });
}

export function getDashboardPerformance(window: string) {
  return request<DashboardPerformance>({
    method: "GET",
    url: "/admin/dashboard/performance",
    params: { window },
  });
}

export function getDashboardTrends(metric: DashboardMetric, window: string) {
  return request<DashboardTrends>({
    method: "GET",
    url: "/admin/dashboard/trends",
    params: { metric, window },
  });
}
