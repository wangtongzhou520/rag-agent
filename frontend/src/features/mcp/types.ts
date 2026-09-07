export interface McpServer {
  name: string;
  url: string;
  status: "online" | "offline" | "connecting";
  serverName?: string | null;
  serverVersion?: string | null;
  enabled: boolean;
  toolCount: number;
  errorMessage?: string | null;
  discoveredAt?: number | null;
}

export interface McpTool {
  toolId: string;
  serverName: string;
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  enabled: boolean;
  serverEnabled: boolean;
  linkedIntentCount: number;
}

export interface McpToolList {
  tools: McpTool[];
  total: number;
}

export interface McpDebugResult {
  toolId: string;
  success: boolean;
  content: string;
  structuredContent?: Record<string, unknown> | null;
  durationMs: number;
}
