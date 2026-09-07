import type { McpDebugResult, McpServer, McpToolList } from "@/features/mcp/types";
import { request } from "@/shared/api/client";

export function listMcpServers() {
  return request<McpServer[]>({ method: "GET", url: "/mcp/servers" });
}

export function refreshMcpServer(name: string) {
  return request<McpServer>({ method: "POST", url: `/mcp/servers/${name}/refresh` });
}

export function setMcpServerEnabled(name: string, enabled: boolean) {
  return request<null>({
    method: "PUT",
    url: `/mcp/servers/${name}/enabled`,
    data: { enabled },
  });
}

export function listMcpTools() {
  return request<McpToolList>({ method: "GET", url: "/mcp/tools" });
}

export function setMcpToolEnabled(serverName: string, toolName: string, enabled: boolean) {
  return request<null>({
    method: "PUT",
    url: `/mcp/tools/${serverName}/${toolName}/enabled`,
    data: { enabled },
  });
}

export function debugMcpTool(
  serverName: string,
  toolName: string,
  parameters: Record<string, unknown>,
) {
  return request<McpDebugResult>({
    method: "POST",
    url: `/mcp/tools/${serverName}/${toolName}/debug`,
    data: { parameters },
  });
}
