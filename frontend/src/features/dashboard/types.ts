export interface DashboardKpi {
  value: number;
  delta: number;
  deltaPct: number | null;
}

export interface DashboardOverview {
  window: string;
  compareWindow: string;
  updatedAt: number;
  kpis: {
    totalUsers: DashboardKpi;
    activeUsers: DashboardKpi;
    totalSessions: DashboardKpi;
    sessions24h: DashboardKpi;
    totalMessages: DashboardKpi;
    messages24h: DashboardKpi;
  };
}

export interface DashboardPerformance {
  window: string;
  avgLatencyMs: number;
  p95LatencyMs: number;
  successRate: number;
  errorRate: number;
  noDocRate: number;
  slowRate: number;
}

export type DashboardMetric = "sessions" | "messages" | "activeusers" | "avglatency" | "quality";

export interface DashboardTrendPoint {
  ts: number;
  value: number;
}

export interface DashboardTrendSeries {
  name: string;
  points: DashboardTrendPoint[];
}

export interface DashboardTrends {
  metric: string;
  window: string;
  granularity: "hour" | "day";
  series: DashboardTrendSeries[];
}
