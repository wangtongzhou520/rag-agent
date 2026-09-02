export type TraceStatus = "RUNNING" | "SUCCESS" | "ERROR" | "CANCELLED" | string;

export interface RagTraceRun {
  traceId: string;
  traceName: string;
  entryPoint: string;
  conversationId: string;
  taskId: string;
  userId: number;
  status: TraceStatus;
  errorMessage?: string | null;
  durationMs?: number | null;
  question?: string | null;
  startTime: number;
  endTime?: number | null;
}

export interface RagTraceNode {
  nodeId: string;
  nodeType: string;
  nodeName: string;
  status: TraceStatus;
  durationMs: number;
  extraData?: Record<string, unknown> | null;
}

export interface RagTraceDetail {
  run: RagTraceRun;
  nodes: RagTraceNode[];
}

export interface TraceFilters {
  traceId: string;
  conversationId: string;
  taskId: string;
  status: string;
}
