import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Cable,
  Check,
  CircleOff,
  Clock3,
  Link2,
  Play,
  RefreshCw,
  Server,
  SlidersHorizontal,
  Wrench,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import "@/features/mcp/McpPage.css";
import { McpDebugDialog } from "@/features/mcp/McpDebugDialog";
import {
  debugMcpTool,
  listMcpServers,
  listMcpTools,
  refreshMcpServer,
  setMcpServerEnabled,
  setMcpToolEnabled,
} from "@/features/mcp/api";
import type { McpDebugResult, McpTool } from "@/features/mcp/types";
import { formatTraceTime } from "@/features/trace/format";
import { Button } from "@/shared/ui/Button";

export function McpPage() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string>();
  const [debugTool, setDebugTool] = useState<McpTool>();
  const [debugResult, setDebugResult] = useState<McpDebugResult>();
  const servers = useQuery({ queryKey: ["mcp-servers"], queryFn: listMcpServers });
  const tools = useQuery({ queryKey: ["mcp-tools"], queryFn: listMcpTools });
  const records = useMemo(() => tools.data?.tools || [], [tools.data?.tools]);
  const selected = records.find((item) => item.toolId === selectedId) || records[0];

  useEffect(() => {
    if (selected && selected.toolId !== selectedId) setSelectedId(selected.toolId);
  }, [selected, selectedId]);

  const refreshQueries = () => {
    void queryClient.invalidateQueries({ queryKey: ["mcp-servers"] });
    void queryClient.invalidateQueries({ queryKey: ["mcp-tools"] });
  };
  const rediscover = useMutation({
    mutationFn: refreshMcpServer,
    onSuccess: () => {
      toast.success("工具清单已重新发现");
      refreshQueries();
    },
    onError: showError,
  });
  const serverToggle = useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      setMcpServerEnabled(name, enabled),
    onSuccess: refreshQueries,
    onError: showError,
  });
  const toolToggle = useMutation({
    mutationFn: ({ tool, enabled }: { tool: McpTool; enabled: boolean }) =>
      setMcpToolEnabled(tool.serverName, tool.name, enabled),
    onSuccess: refreshQueries,
    onError: showError,
  });
  const debug = useMutation({
    mutationFn: ({ tool, parameters }: { tool: McpTool; parameters: Record<string, unknown> }) =>
      debugMcpTool(tool.serverName, tool.name, parameters),
    onSuccess: setDebugResult,
    onError: showError,
  });
  const online = servers.data?.filter((item) => item.status === "online").length || 0;
  const enabled = records.filter((item) => item.enabled).length;

  return (
    <main className="console-content mcp-page">
      <header className="console-page-header mcp-page-header">
        <div className="console-page-heading">
          <p>工具连接</p>
          <h1>MCP 管理与调试</h1>
          <span>检查远端服务发现结果，控制工具是否参与问答，并用显式参数验证协议返回。</span>
        </div>
        <Button variant="secondary" onClick={refreshQueries}>
          <RefreshCw aria-hidden="true" /> 刷新状态
        </Button>
      </header>

      <section className="mcp-summary-strip">
        <div>
          <Server />
          <span>服务连接</span>
          <strong>{online}</strong>
          <small>/ {servers.data?.length || 0} 在线</small>
        </div>
        <div>
          <Wrench />
          <span>发现工具</span>
          <strong>{records.length}</strong>
          <small>{enabled} 项已启用</small>
        </div>
        <p>
          Server 地址来自部署配置；页面启停状态持久化到 PostgreSQL，重新发现不会覆盖人工停用结果。
        </p>
      </section>

      <section className="mcp-server-rack">
        <header>
          <div>
            <Cable />
            <h2>服务连接</h2>
          </div>
          <span>{servers.data?.length || 0} 个配置端点</span>
        </header>
        {servers.isLoading ? (
          <McpState text="正在连接 MCP Server…" />
        ) : servers.isError ? (
          <McpState text={errorText(servers.error)} error />
        ) : !servers.data?.length ? (
          <McpState text="尚未配置 MCP Server" />
        ) : (
          <div className="mcp-server-list">
            {servers.data.map((server) => (
              <article className={`mcp-server-card status-${server.status}`} key={server.name}>
                <div className="mcp-server-mark">
                  <span />
                  <Server />
                </div>
                <div className="mcp-server-copy">
                  <div>
                    <strong>{server.name}</strong>
                    <i>{statusName(server.status)}</i>
                    {!server.enabled && <i className="disabled">已停用</i>}
                  </div>
                  <code>{server.url}</code>
                  <span>
                    {server.serverName || "未读取服务信息"}
                    {server.serverVersion ? ` · v${server.serverVersion}` : ""}
                    {server.discoveredAt ? ` · 发现于 ${formatTraceTime(server.discoveredAt)}` : ""}
                    {server.errorMessage ? ` · ${server.errorMessage}` : ""}
                  </span>
                </div>
                <div className="mcp-server-meta">
                  <strong>{server.toolCount}</strong>
                  <span>TOOLS</span>
                </div>
                <div className="mcp-server-actions">
                  <button
                    onClick={() =>
                      serverToggle.mutate({ name: server.name, enabled: !server.enabled })
                    }
                  >
                    {server.enabled ? <CircleOff /> : <Check />}
                    {server.enabled ? "停用" : "启用"}
                  </button>
                  <button onClick={() => rediscover.mutate(server.name)}>
                    <RefreshCw /> 重新发现
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      <div className="mcp-tool-workbench">
        <section className="mcp-tool-list-panel">
          <header>
            <div>
              <SlidersHorizontal />
              <h2>工具清单</h2>
            </div>
            <span>{tools.data?.total || 0} 项</span>
          </header>
          {tools.isLoading ? (
            <McpState text="正在读取工具清单…" />
          ) : tools.isError ? (
            <McpState text={errorText(tools.error)} error />
          ) : !records.length ? (
            <McpState text="当前没有已发现工具" />
          ) : (
            <div className="mcp-tool-list">
              {records.map((tool) => (
                <button
                  className={selected?.toolId === tool.toolId ? "active" : ""}
                  key={tool.toolId}
                  onClick={() => setSelectedId(tool.toolId)}
                >
                  <span className={tool.enabled ? "enabled" : ""} />
                  <div>
                    <strong>{tool.name}</strong>
                    <code>{tool.toolId}</code>
                  </div>
                  <i>{tool.linkedIntentCount} 个意图</i>
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="mcp-tool-inspector">
          {!selected ? (
            <McpState text="请选择一个工具" />
          ) : (
            <>
              <header>
                <div>
                  <span>{selected.serverName} / TOOL</span>
                  <h2>{selected.name}</h2>
                  <p>{selected.description || "该工具未提供说明"}</p>
                </div>
                <div>
                  <Button
                    variant="secondary"
                    disabled={!selected.serverEnabled || toolToggle.isPending}
                    onClick={() =>
                      toolToggle.mutate({ tool: selected, enabled: !selected.enabled })
                    }
                  >
                    {selected.enabled ? <CircleOff /> : <Check />}
                    {selected.enabled ? "停用工具" : "启用工具"}
                  </Button>
                  <Button
                    disabled={!selected.enabled}
                    onClick={() => {
                      setDebugResult(undefined);
                      setDebugTool(selected);
                    }}
                  >
                    <Play /> 调试调用
                  </Button>
                </div>
              </header>
              <div className="mcp-tool-facts">
                <div>
                  <span>运行状态</span>
                  <strong className={selected.enabled ? "success" : "muted"}>
                    {selected.enabled ? "可参与问答" : "已从运行时移除"}
                  </strong>
                </div>
                <div>
                  <span>意图绑定</span>
                  <strong>{selected.linkedIntentCount}</strong>
                </div>
                <div>
                  <span>参数字段</span>
                  <strong>{propertyCount(selected.inputSchema)}</strong>
                </div>
              </div>
              <section className="mcp-schema-panel">
                <header>
                  <div>
                    <Link2 />
                    <strong>Input Schema</strong>
                  </div>
                  <span>来自 tools/list</span>
                </header>
                <pre>{JSON.stringify(selected.inputSchema, null, 2)}</pre>
              </section>
              <footer className="mcp-inspector-footer">
                <Clock3 />
                服务发现后工具定义保存在进程内；启停状态由数据库覆盖。
              </footer>
            </>
          )}
        </section>
      </div>

      <McpDebugDialog
        tool={debugTool}
        result={debugResult}
        busy={debug.isPending}
        onClose={() => {
          setDebugTool(undefined);
          setDebugResult(undefined);
        }}
        onRun={(parameters) => debug.mutate({ tool: debugTool!, parameters })}
      />
    </main>
  );
}

function propertyCount(schema: Record<string, unknown>) {
  const properties = schema.properties;
  return properties && typeof properties === "object" ? Object.keys(properties).length : 0;
}

function statusName(status: string) {
  return { online: "在线", offline: "离线", connecting: "连接中" }[status] || status;
}

function McpState({ text, error = false }: { text: string; error?: boolean }) {
  return <div className={`mcp-page-state${error ? " error" : ""}`}>{text}</div>;
}

function errorText(error: unknown) {
  return error instanceof Error ? error.message : "数据加载失败";
}

function showError(error: unknown) {
  toast.error(errorText(error));
}
