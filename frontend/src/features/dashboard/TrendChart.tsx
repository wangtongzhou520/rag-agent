import { useId } from "react";

import { formatTrendTime } from "@/features/dashboard/format";
import type { DashboardTrendSeries } from "@/features/dashboard/types";

const WIDTH = 760;
const HEIGHT = 238;
const PADDING = { top: 18, right: 18, bottom: 34, left: 46 };
const COLORS = ["#2563eb", "#df4b55"];

interface TrendChartProps {
  series: DashboardTrendSeries[];
  granularity: "hour" | "day";
  percentage?: boolean;
  duration?: boolean;
}

function pathFor(values: number[], maximum: number) {
  const chartWidth = WIDTH - PADDING.left - PADDING.right;
  const chartHeight = HEIGHT - PADDING.top - PADDING.bottom;
  return values
    .map((value, index) => {
      const x =
        PADDING.left +
        (values.length === 1 ? chartWidth / 2 : (index / (values.length - 1)) * chartWidth);
      const y = PADDING.top + chartHeight - (value / maximum) * chartHeight;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export function TrendChart({ series, granularity, percentage, duration }: TrendChartProps) {
  const titleId = useId();
  const allValues = series.flatMap((item) => item.points.map((point) => point.value));
  const naturalMaximum = Math.max(0, ...allValues);
  const maximum = percentage
    ? Math.min(100, Math.max(10, Math.ceil(naturalMaximum / 10) * 10))
    : Math.max(1, naturalMaximum);
  const points = series[0]?.points || [];
  const labelIndexes = Array.from(
    new Set(
      [0, Math.floor((points.length - 1) / 2), points.length - 1].filter((index) => index >= 0),
    ),
  );
  const formatAxis = (value: number) => {
    if (percentage) return `${value.toFixed(0)}%`;
    if (duration) return value >= 1_000 ? `${(value / 1_000).toFixed(1)}s` : `${value}ms`;
    return String(Math.round(value));
  };

  return (
    <div className="dashboard-chart">
      <div className="dashboard-chart__legend" aria-hidden="true">
        {series.map((item, index) => (
          <span key={item.name}>
            <i style={{ background: COLORS[index] }} />
            {item.name}
          </span>
        ))}
      </div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-labelledby={titleId}>
        <title id={titleId}>{series.map((item) => item.name).join("、")}趋势</title>
        {[0, 0.5, 1].map((ratio) => {
          const y = PADDING.top + (1 - ratio) * (HEIGHT - PADDING.top - PADDING.bottom);
          return (
            <g key={ratio}>
              <line x1={PADDING.left} x2={WIDTH - PADDING.right} y1={y} y2={y} />
              <text x={PADDING.left - 9} y={y + 4} textAnchor="end">
                {formatAxis(maximum * ratio)}
              </text>
            </g>
          );
        })}
        {series.map((item, index) => (
          <path
            className="dashboard-chart__line"
            d={pathFor(
              item.points.map((point) => point.value),
              maximum,
            )}
            key={item.name}
            style={{ stroke: COLORS[index] }}
          />
        ))}
        {labelIndexes.map((index) => {
          const chartWidth = WIDTH - PADDING.left - PADDING.right;
          const x =
            PADDING.left +
            (points.length === 1 ? chartWidth / 2 : (index / (points.length - 1)) * chartWidth);
          return (
            <text
              className="dashboard-chart__time"
              key={index}
              x={x}
              y={HEIGHT - 8}
              textAnchor="middle"
            >
              {formatTrendTime(points[index].ts, granularity)}
            </text>
          );
        })}
      </svg>
    </div>
  );
}
