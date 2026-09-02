const STATUS_NAMES: Record<string, string> = {
  RUNNING: "运行中",
  SUCCESS: "成功",
  ERROR: "异常",
  CANCELLED: "已取消",
};

export function traceStatusName(status: string) {
  return STATUS_NAMES[status.toUpperCase()] || status;
}

export function formatDuration(value?: number | null) {
  if (value == null) return "—";
  if (value < 1_000) return `${value} ms`;
  if (value < 60_000) return `${(value / 1_000).toFixed(value < 10_000 ? 2 : 1)} s`;
  const minutes = Math.floor(value / 60_000);
  const seconds = Math.round((value % 60_000) / 1_000);
  return `${minutes} 分 ${seconds} 秒`;
}

export function formatTraceTime(value?: number | null) {
  if (value == null) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function shortTraceId(value: string) {
  return value.length > 20 ? `${value.slice(0, 8)}…${value.slice(-8)}` : value;
}
