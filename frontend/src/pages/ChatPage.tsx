import {
  ArrowUp,
  BrainCircuit,
  Database,
  LogOut,
  Menu,
  MessageSquarePlus,
  PanelRightOpen,
  Square,
  Workflow,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link } from "react-router-dom";

import { useAuthStore } from "@/features/auth/store";
import { DocumentPreviewDialog } from "@/features/chat/DocumentPreviewDialog";
import { MarkdownAnswer } from "@/features/chat/MarkdownAnswer";
import { SourcePanel } from "@/features/chat/SourcePanel";
import { ThinkingPanel } from "@/features/chat/ThinkingPanel";
import { useChatStore } from "@/features/chat/store";
import type { SourceRef } from "@/features/chat/types";
import { BrandMark } from "@/shared/components/BrandMark";
import { cn } from "@/shared/lib/cn";
import { Button } from "@/shared/ui/Button";

const examples = ["知识库里有哪些文档？", "请说明当前 RAG 检索流程", "如何追踪一次问答的来源？"];

function phaseCopy(phase: ReturnType<typeof useChatStore.getState>["stream"]["phase"]) {
  const labels = {
    idle: "准备就绪",
    connecting: "正在建立连接",
    streaming: "正在生成回答",
    finishing: "正在整理来源",
    completed: "回答已完成",
    failed: "连接异常",
    cancelled: "已停止接收",
  };
  return labels[phase];
}

export function ChatPage() {
  const { user, logout } = useAuthStore();
  const { title, turns, stream, deepThinking, setDeepThinking, send, stop, reset } = useChatStore();
  const [draft, setDraft] = useState("");
  const [sourceOpen, setSourceOpen] = useState(false);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [selectedSource, setSelectedSource] = useState<number>();
  const [previewSource, setPreviewSource] = useState<SourceRef>();
  const endRef = useRef<HTMLDivElement>(null);
  const busy = ["connecting", "streaming", "finishing"].includes(stream.phase);

  const sources = useMemo(
    () =>
      [...turns].reverse().find((turn) => turn.role === "assistant" && turn.sources?.length)
        ?.sources || [],
    [turns],
  );

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: busy ? "auto" : "smooth", block: "end" });
  }, [busy, turns]);

  useEffect(() => () => stop(), [stop]);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const question = draft.trim();
    if (!question || busy) return;
    setDraft("");
    await send(question);
  };

  const onComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  };

  const askExample = (question: string) => {
    if (busy) return;
    setDraft("");
    void send(question);
  };

  const showSource = (index: number) => {
    setSelectedSource(index);
    setSourceOpen(true);
    window.setTimeout(() => document.getElementById(`cite-${index}`)?.scrollIntoView(), 0);
  };

  return (
    <main className="chat-workspace">
      <aside className={cn("chat-sidebar", navigationOpen && "chat-sidebar--open")}>
        <BrandMark compact className="[&_strong]:text-white [&_span_span]:text-blue-100" />
        <button
          className="chat-sidebar__close"
          type="button"
          onClick={() => setNavigationOpen(false)}
          aria-label="关闭导航"
        >
          <X aria-hidden="true" />
        </button>
        <button
          className="new-chat-button"
          type="button"
          onClick={() => {
            reset();
            setNavigationOpen(false);
          }}
        >
          <MessageSquarePlus aria-hidden="true" />
          新对话
        </button>
        <nav aria-label="当前工作区">
          <p>WORKSPACE</p>
          <span className="chat-nav-item chat-nav-item--active">
            <BrainCircuit aria-hidden="true" />
            智能问答
          </span>
          {user?.role === "admin" && (
            <Link className="chat-nav-item" to="/admin" onClick={() => setNavigationOpen(false)}>
              <Database aria-hidden="true" />
              管理控制台
            </Link>
          )}
          <span className="chat-nav-item chat-nav-item--disabled">
            <Workflow aria-hidden="true" />
            会话历史
            <small>F3</small>
          </span>
        </nav>
        <div className="chat-sidebar__session">
          <span>本轮会话</span>
          <strong>{title}</strong>
          <small>
            {stream.conversationId ? stream.conversationId.slice(0, 13) : "等待首次提问"}
          </small>
        </div>
        <div className="chat-sidebar__user">
          <span>{user?.username?.slice(0, 1).toUpperCase()}</span>
          <div>
            <strong>{user?.username}</strong>
            <small>{user?.role === "admin" ? "管理员" : "用户"}</small>
          </div>
          <button
            type="button"
            onClick={() => {
              reset();
              void logout();
            }}
            aria-label="退出登录"
          >
            <LogOut aria-hidden="true" />
          </button>
        </div>
      </aside>
      {navigationOpen && (
        <button
          className="chat-sidebar-backdrop"
          type="button"
          aria-label="关闭导航"
          onClick={() => setNavigationOpen(false)}
        />
      )}

      <section className="chat-main">
        <header className="chat-topbar">
          <button
            className="chat-mobile-menu"
            type="button"
            aria-label="打开导航"
            onClick={() => setNavigationOpen(true)}
          >
            <Menu aria-hidden="true" />
          </button>
          <div>
            <span>RAG WORKSPACE</span>
            <strong>{title}</strong>
          </div>
          <div className={cn("stream-status", `stream-status--${stream.phase}`)}>
            <i />
            {phaseCopy(stream.phase)}
          </div>
          <Button
            className="source-mobile-trigger"
            variant="secondary"
            onClick={() => setSourceOpen(true)}
          >
            <PanelRightOpen className="h-4 w-4" />
            来源 {sources.length || ""}
          </Button>
        </header>

        <div className="chat-scroll-region">
          {turns.length === 0 ? (
            <section className="chat-empty-state">
              <p>AGENTIC ANSWER PATH</p>
              <h1>
                让问题进入一条
                <span>可观察的知识路径。</span>
              </h1>
              <div className="chat-empty-state__line" aria-hidden="true">
                <i />
                <i />
                <i />
                <i />
                <i />
              </div>
              <p className="chat-empty-state__description">
                提问后，你可以分别查看模型思考、检索来源和最终回答。以下问题仅作为输入示例。
              </p>
              <div className="example-grid">
                {examples.map((example, index) => (
                  <button type="button" key={example} onClick={() => askExample(example)}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    {example}
                    <ArrowUp aria-hidden="true" />
                  </button>
                ))}
              </div>
            </section>
          ) : (
            <div className="message-flow">
              {turns.map((turn) => (
                <article className={cn("chat-turn", `chat-turn--${turn.role}`)} key={turn.id}>
                  {turn.role === "user" ? (
                    <div className="user-question">{turn.content}</div>
                  ) : (
                    <div className="assistant-answer">
                      <div className="assistant-answer__mark">RA</div>
                      <div className="assistant-answer__content">
                        <ThinkingPanel
                          thinking={turn.thinking || ""}
                          phase={turn.streaming ? stream.phase : "completed"}
                          hasAnswer={Boolean(turn.content)}
                        />
                        {turn.content ? (
                          <MarkdownAnswer onCitation={showSource}>{turn.content}</MarkdownAnswer>
                        ) : turn.error ? null : (
                          <p className="answer-pending">正在理解问题并准备检索…</p>
                        )}
                        {turn.error && (
                          <div className="answer-error">
                            <strong>本次回答未完成</strong>
                            <p>{turn.error}</p>
                          </div>
                        )}
                        {turn.messageStatus === "INTERRUPTED" && (
                          <p className="answer-status-note">已在当前浏览器中停止接收后续内容。</p>
                        )}
                        {turn.sources && turn.sources.length > 0 && (
                          <button
                            className="answer-sources-link"
                            type="button"
                            onClick={() => showSource(turn.sources?.[0].index || 1)}
                          >
                            <PanelRightOpen aria-hidden="true" />
                            查看 {turn.sources.length} 条回答来源
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </article>
              ))}
              <div ref={endRef} />
            </div>
          )}
        </div>

        <form className="chat-composer-shell" onSubmit={(event) => void submit(event)}>
          <div className="chat-composer">
            <textarea
              aria-label="输入问题"
              maxLength={4000}
              placeholder="输入一个需要从知识中寻找答案的问题…"
              rows={1}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={onComposerKeyDown}
            />
            <div className="chat-composer__actions">
              <button
                className={cn("thinking-toggle", deepThinking && "thinking-toggle--active")}
                type="button"
                aria-pressed={deepThinking}
                onClick={() => setDeepThinking(!deepThinking)}
                disabled={busy}
              >
                <BrainCircuit aria-hidden="true" />
                深度思考
              </button>
              <span>Enter 发送 · Shift + Enter 换行</span>
              {busy ? (
                <button className="stop-stream-button" type="button" onClick={stop}>
                  <Square aria-hidden="true" />
                  停止接收
                </button>
              ) : (
                <button className="send-question-button" type="submit" disabled={!draft.trim()}>
                  <ArrowUp aria-hidden="true" />
                  <span>发送</span>
                </button>
              )}
            </div>
          </div>
          <p>停止仅中断当前浏览器连接；服务端任务停止接口将在 F3 接入。</p>
        </form>
      </section>

      <SourcePanel
        sources={sources as SourceRef[]}
        selected={selectedSource}
        open={sourceOpen}
        onSelect={setSelectedSource}
        onPreview={setPreviewSource}
        onClose={() => setSourceOpen(false)}
      />
      <DocumentPreviewDialog source={previewSource} onClose={() => setPreviewSource(undefined)} />
      {sourceOpen && (
        <button
          className="source-panel-backdrop"
          type="button"
          aria-label="关闭来源面板"
          onClick={() => setSourceOpen(false)}
        />
      )}
    </main>
  );
}
