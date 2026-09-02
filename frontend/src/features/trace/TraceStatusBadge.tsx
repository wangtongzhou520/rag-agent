import { traceStatusName } from "@/features/trace/format";

export function TraceStatusBadge({ status }: { status: string }) {
  const normalized = status.toUpperCase();
  return (
    <span className={`trace-status trace-status--${normalized.toLowerCase()}`}>
      <i aria-hidden="true" />
      {traceStatusName(status)}
    </span>
  );
}
