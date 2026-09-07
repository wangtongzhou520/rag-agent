import { CheckCircle2, Clock3, Play, XCircle } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import type { McpDebugResult, McpTool } from "@/features/mcp/types";
import { Button } from "@/shared/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/Dialog";

function initialParameters(tool?: McpTool) {
  const schema = tool?.inputSchema as {
    properties?: Record<string, { default?: unknown; type?: string }>;
    required?: string[];
  };
  const value: Record<string, unknown> = {};
  Object.entries(schema?.properties || {}).forEach(([name, definition]) => {
    if (definition.default !== undefined) value[name] = definition.default;
    else if (schema.required?.includes(name)) value[name] = definition.type === "integer" ? 0 : "";
  });
  return JSON.stringify(value, null, 2);
}

export function McpDebugDialog({
  tool,
  result,
  busy,
  onClose,
  onRun,
}: {
  tool?: McpTool;
  result?: McpDebugResult;
  busy: boolean;
  onClose: () => void;
  onRun: (parameters: Record<string, unknown>) => void;
}) {
  const [parameters, setParameters] = useState("{}");
  const [error, setError] = useState("");
  const initial = useMemo(() => initialParameters(tool), [tool]);
  useEffect(() => {
    setParameters(initial);
    setError("");
  }, [initial]);

  if (!tool) return null;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    try {
      const value = JSON.parse(parameters);
      if (!value || Array.isArray(value) || typeof value !== "object") {
        throw new Error("参数必须是 JSON 对象");
      }
      setError("");
      onRun(value as Record<string, unknown>);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "参数不是合法 JSON");
    }
  };

  return (
    <Dialog open={Boolean(tool)} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="mcp-debug-dialog">
        <form onSubmit={submit}>
          <DialogHeader>
            <div className="mcp-debug-kicker">
              <span>{tool.serverName}</span>
              <code>{tool.toolId}</code>
            </div>
            <DialogTitle>调试 {tool.name}</DialogTitle>
            <DialogDescription>
              直接以显式参数调用远端工具，不经过意图识别和模型提参。调试记录会进入审计日志。
            </DialogDescription>
          </DialogHeader>
          <div className="mcp-debug-grid">
            <section>
              <header>
                <strong>请求参数</strong>
                <span>JSON Object</span>
              </header>
              <textarea
                aria-label="MCP 调试参数"
                value={parameters}
                onChange={(event) => setParameters(event.target.value)}
                spellCheck={false}
              />
              {error && <p className="mcp-form-error">{error}</p>}
            </section>
            <section className="mcp-debug-result">
              <header>
                <strong>执行结果</strong>
                {result && (
                  <span className={result.success ? "success" : "failed"}>
                    {result.success ? <CheckCircle2 /> : <XCircle />}
                    {result.success ? "成功" : "失败"}
                  </span>
                )}
              </header>
              {!result ? (
                <div className="mcp-debug-empty">
                  <Play />
                  <span>运行后在这里检查返回内容</span>
                </div>
              ) : (
                <div className="mcp-debug-output">
                  <span>
                    <Clock3 /> {result.durationMs} ms
                  </span>
                  <pre>
                    {result.structuredContent
                      ? JSON.stringify(result.structuredContent, null, 2)
                      : result.content}
                  </pre>
                </div>
              )}
            </section>
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose}>
              关闭
            </Button>
            <Button type="submit" disabled={busy}>
              <Play aria-hidden="true" /> {busy ? "正在调用…" : "运行调试"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
