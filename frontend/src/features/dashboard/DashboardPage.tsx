import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Gauge,
  MessageSquareText,
  RefreshCw,
  TimerReset,
  UserRound,
  UsersRound,
} from "lucide-react";
import { useState } from "react";

import {
  getDashboardOverview,
  getDashboardPerformance,
  getDashboardTrends,
} from "@/features/dashboard/api";
import {
  describeKpiDelta,
  formatDashboardDuration,
  formatInteger,
  formatPercent,
} from "@/features/dashboard/format";
import { TrendChart } from "@/features/dashboard/TrendChart";
import type { DashboardKpi, DashboardMetric } from "@/features/dashboard/types";
import { Button } from "@/shared/ui/Button";

const windows = [
  ["24h", "24 小时"],
  ["7d", "7 天"],
  ["30d", "30 天"],
] as const;

const metrics: { value: DashboardMetric; label: string }[] = [
  { value: "sessions", label: "会话" },
  { value: "messages", label: "消息" },
  { value: "activeusers", label: "活跃用户" },
  { value: "avglatency", label: "响应耗时" },
  { value: "quality", label: "质量" },
];

function KpiCard({
  icon: Icon,
  label,
  item,
  comparison,
}: {
  icon: typeof UserRound;
  label: string;
  item?: DashboardKpi;
  comparison: boolean;
}) {
  return (
    <article className="dashboard-kpi-card">
      <header>
        <span>{label}</span>
        <Icon aria-hidden="true" />
      </header>
      <strong>{item ? formatInteger(item.value) : "—"}</strong>
      <small className={item && item.delta < 0 ? "is-negative" : undefined}>
        {item ? describeKpiDelta(item, comparison) : "正在读取"}
      </small>
    </article>
  );
}

function PerformanceItem({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: typeof Gauge;
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div
      className={`dashboard-performance-item${tone ? ` dashboard-performance-item--${tone}` : ""}`}
    >
      <Icon aria-hidden="true" />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function DashboardPage() {
  const [window, setWindow] = useState("24h");
  const [metric, setMetric] = useState<DashboardMetric>("sessions");
  const overview = useQuery({
    queryKey: ["dashboard-overview", window],
    queryFn: () => getDashboardOverview(window),
  });
  const performance = useQuery({
    queryKey: ["dashboard-performance", window],
    queryFn: () => getDashboardPerformance(window),
  });
  const trends = useQuery({
    queryKey: ["dashboard-trends", metric, window],
    queryFn: () => getDashboardTrends(metric, window),
  });
  const loading = overview.isLoading || performance.isLoading;
  const failed = overview.isError || performance.isError;
  const refresh = () =>
    void Promise.all([overview.refetch(), performance.refetch(), trends.refetch()]);
  const currentWindow = windows.find(([value]) => value === window)?.[1] || window;
  const updatedAt = overview.data?.updatedAt
    ? new Date(overview.data.updatedAt).toLocaleString("zh-CN", { hour12: false })
    : "—";
  const data = overview.data?.kpis;
  const qualityMetric = metric === "quality";

  return (
    <main className="console-content dashboard-page">
      <header className="console-page-header dashboard-page-header">
        <div className="console-page-heading">
          <p>运行观测</p>
          <h1>系统概览</h1>
          <span>查看真实使用量、响应表现和问答质量。</span>
        </div>
        <div className="dashboard-header-actions">
          <div className="dashboard-window-switch" aria-label="统计周期">
            {windows.map(([value, label]) => (
              <button
                className={window === value ? "is-active" : undefined}
                key={value}
                onClick={() => setWindow(value)}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>
          <Button variant="secondary" onClick={refresh}>
            <RefreshCw aria-hidden="true" /> 刷新
          </Button>
        </div>
      </header>

      {failed ? (
        <section className="dashboard-error" role="alert">
          <AlertTriangle aria-hidden="true" />
          <div>
            <strong>概览数据加载失败</strong>
            <p>
              {overview.error instanceof Error
                ? overview.error.message
                : performance.error instanceof Error
                  ? performance.error.message
                  : "请稍后重试"}
            </p>
          </div>
          <Button variant="secondary" onClick={refresh}>
            重新加载
          </Button>
        </section>
      ) : (
        <>
          <section
            className={`dashboard-kpi-grid${loading ? " is-loading" : ""}`}
            aria-label="使用概况"
          >
            <KpiCard
              icon={UsersRound}
              label={`${currentWindow}活跃用户`}
              item={data?.activeUsers}
              comparison
            />
            <KpiCard
              icon={Activity}
              label={`${currentWindow}会话`}
              item={data?.sessions24h}
              comparison
            />
            <KpiCard
              icon={MessageSquareText}
              label={`${currentWindow}消息`}
              item={data?.messages24h}
              comparison
            />
            <KpiCard icon={UserRound} label="用户总数" item={data?.totalUsers} comparison={false} />
            <KpiCard
              icon={Activity}
              label="会话总数"
              item={data?.totalSessions}
              comparison={false}
            />
            <KpiCard
              icon={MessageSquareText}
              label="消息总数"
              item={data?.totalMessages}
              comparison={false}
            />
          </section>

          <section className="dashboard-section dashboard-performance">
            <header>
              <div>
                <h2>响应表现</h2>
                <p>仅使用已完成 Trace；慢请求阈值为 20 秒。</p>
              </div>
              <time>更新于 {updatedAt}</time>
            </header>
            <div className="dashboard-performance-grid">
              <PerformanceItem
                icon={CheckCircle2}
                label="成功率"
                value={performance.data ? formatPercent(performance.data.successRate) : "—"}
                tone="success"
              />
              <PerformanceItem
                icon={Clock3}
                label="平均耗时"
                value={
                  performance.data ? formatDashboardDuration(performance.data.avgLatencyMs) : "—"
                }
              />
              <PerformanceItem
                icon={TimerReset}
                label="P95 耗时"
                value={
                  performance.data ? formatDashboardDuration(performance.data.p95LatencyMs) : "—"
                }
              />
              <PerformanceItem
                icon={AlertTriangle}
                label="错误率"
                value={performance.data ? formatPercent(performance.data.errorRate) : "—"}
                tone={performance.data?.errorRate ? "danger" : undefined}
              />
              <PerformanceItem
                icon={Gauge}
                label="无知识率"
                value={performance.data ? formatPercent(performance.data.noDocRate) : "—"}
              />
              <PerformanceItem
                icon={Activity}
                label="慢请求率"
                value={performance.data ? formatPercent(performance.data.slowRate) : "—"}
              />
            </div>
          </section>
        </>
      )}

      <section className="dashboard-section dashboard-trends">
        <header>
          <div>
            <h2>趋势</h2>
            <p>
              按{trends.data?.granularity === "hour" ? "小时" : "天"}补齐无数据时段，数据实时聚合。
            </p>
          </div>
          <div className="dashboard-metric-switch" aria-label="趋势指标">
            {metrics.map((item) => (
              <button
                className={metric === item.value ? "is-active" : undefined}
                key={item.value}
                onClick={() => setMetric(item.value)}
                type="button"
              >
                {item.label}
              </button>
            ))}
          </div>
        </header>
        {trends.isLoading ? (
          <div className="dashboard-chart-state">正在聚合趋势…</div>
        ) : trends.isError ? (
          <div className="dashboard-chart-state dashboard-chart-state--error">
            {trends.error instanceof Error ? trends.error.message : "趋势加载失败"}
          </div>
        ) : trends.data?.series.length ? (
          <TrendChart
            series={trends.data.series}
            granularity={trends.data.granularity}
            percentage={qualityMetric}
            duration={metric === "avglatency"}
          />
        ) : (
          <div className="dashboard-chart-state">当前指标暂无数据</div>
        )}
      </section>
    </main>
  );
}
