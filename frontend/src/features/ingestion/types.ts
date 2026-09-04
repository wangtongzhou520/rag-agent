export type NodeType = "fetcher" | "parser" | "enhancer" | "chunker" | "enricher" | "indexer";

export interface PipelineNode {
  id?: number;
  nodeId: string;
  nodeType: NodeType;
  settings: Record<string, unknown>;
  condition?: Record<string, unknown> | string | boolean | null;
  nextNodeId?: string | null;
}

export interface Pipeline {
  id: number;
  name: string;
  description?: string | null;
  createdBy: number;
  nodes: PipelineNode[];
  createTime: number;
  updateTime: number;
}

export interface PipelineWrite {
  name: string;
  description?: string;
  nodes: PipelineNode[];
}

export type PipelineTaskStatus = "pending" | "running" | "failed" | "completed";

export interface PipelineTask {
  id: number;
  pipelineId: number;
  sourceType: "file" | "url" | "feishu";
  sourceLocation?: string | null;
  sourceFileName?: string | null;
  status: PipelineTaskStatus;
  chunkCount: number;
  errorMessage?: string | null;
  logs: Array<{
    nodeId: string;
    nodeType: NodeType;
    status: "success" | "failed" | "skipped";
    durationMs: number;
    message: string;
    error?: string | null;
  }>;
  metadata: Record<string, unknown>;
  startedAt?: number | null;
  completedAt?: number | null;
  createdBy: number;
  createTime: number;
  updateTime: number;
}

export interface TaskNode {
  id: number;
  taskId: number;
  pipelineId: number;
  nodeId: string;
  nodeType: NodeType;
  nodeOrder: number;
  status: "success" | "failed" | "skipped";
  durationMs: number;
  message?: string | null;
  errorMessage?: string | null;
  output?: unknown;
  createTime: number;
  updateTime: number;
}

export interface AsyncTask {
  id: number;
  eventId: string;
  taskType: string;
  bizKey?: string | null;
  status: "pending" | "running" | "success" | "failed";
  retryCount: number;
  maxRetries: number;
  nextRetryAt?: number | null;
  leaseUntil?: number | null;
  errorMessage?: string | null;
  createTime: number;
  updateTime: number;
}
