import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUp,
  BrainCircuit,
  CornerDownRight,
  Database,
  ListPlus,
  LoaderCircle,
  LogOut,
  Menu,
  MessageSquarePlus,
  PanelRightOpen,
  Square,
  ThumbsDown,
  ThumbsUp,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { useAuthStore } from "@/features/auth/store";
import { DocumentPreviewDialog } from "@/features/chat/DocumentPreviewDialog";
import { listConversationMessages, listConversations } from "@/features/chat/api";
import { ConversationHistory } from "@/features/chat/ConversationHistory";
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
  const navigate = useNavigate();
  const { conversationId: routeConversationId } = useParams();
  const queryClient = useQueryClient();
  const { user, logout } = useAuthStore();
  const {
    conversationId,
    title,
    turns,
    stream,
    stopping,
    deepThinking,
    setDeepThinking,
    prepareConversation,
    hydrateConversation,
    setTitle,
    send,
    stop,
    voteMessage,
    loadRecommendations,
    reset,
  } = useChatStore();
  const [draft, setDraft] = useState("");
  const [sourceOpen, setSourceOpen] = useState(false);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [selectedSource, setSelectedSource] = useState<number>();
  const [previewSource, setPreviewSource] = useState<SourceRef>();
  const endRef = useRef<HTMLDivElement>(null);
  const busy = ["connecting", "streaming", "finishing"].includes(stream.phase);
  const conversationsQuery = useQuery({
    queryKey: ["conversations"],
    queryFn: listConversations,
  });
  const messagesQuery = useQuery({
    queryKey: ["conversation-messages", routeConversationId],
    queryFn: () => listConversationMessages(routeConversationId || ""),
    enabled: Boolean(routeConversationId),
  });

  const sources = useMemo(
    () =>
      [...turns].reverse().find((turn) => turn.role === "assistant" && turn.sources?.length)
        ?.sources || [],
    [turns],
  );

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: busy ? "auto" : "smooth", block: "end" });
  }, [busy, turns]);

  useEffect(
    () => () => {
      void stop();
    },
    [stop],
  );

  useEffect(() => {
    if (!routeConversationId) return;
    const state = useChatStore.getState();
    if (state.conversationId !== routeConversationId) {
      const selected = conversationsQuery.data?.find(
        (conversation) => conversation.conversationId === routeConversationId,
      );
      prepareConversation(routeConversationId, selected?.title || "会话记录");
    }
  }, [conversationsQuery.data, prepareConversation, routeConversationId]);

  useEffect(() => {
    if (!routeConversationId || !messagesQuery.data) return;
    const state = useChatStore.getState();
    if (state.conversationId === routeConversationId && state.turns.length === 0) {
      const selected = conversationsQuery.data?.find(
        (conversation) => conversation.conversationId === routeConversationId,
      );
      hydrateConversation(routeConversationId, selected?.title || state.title, messagesQuery.data);
    }
  }, [conversationsQuery.data, hydrateConversation, messagesQuery.data, routeConversationId]);

  useEffect(() => {
    const selected = conversationsQuery.data?.find(
      (conversation) => conversation.conversationId === conversationId,
    );
    if (selected && selected.title !== title) setTitle(selected.title);
  }, [conversationId, conversationsQuery.data, setTitle, title]);

  useEffect(() => {
    if (stream.phase !== "completed" || !stream.conversationId) return;
    void queryClient.invalidateQueries({ queryKey: ["conversations"] });
    if (routeConversationId !== stream.conversationId) {
      navigate(`/chat/${stream.conversationId}`, { replace: true });
    }
  }, [navigate, queryClient, routeConversationId, stream.conversationId, stream.phase]);

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
            navigate("/chat");
            setNavigationOpen(false);
          }}
        >
          <MessageSquarePlus aria-hidden="true" />
          新对话
        </button>
        <nav aria-label="当前工作区">
          <p>工作区</p>
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
        </nav>
        <ConversationHistory
          conversations={conversationsQuery.data || []}
          activeId={conversationId}
          loading={conversationsQuery.isLoading}
          error={
            conversationsQuery.isError
              ? conversationsQuery.error instanceof Error
                ? conversationsQuery.error.message
                : "会话列表载入失败"
              : undefined
          }
          onRetry={() => void conversationsQuery.refetch()}
          onOpen={(conversation) => {
            navigate(`/chat/${conversation.conversationId}`);
            setNavigationOpen(false);
          }}
          onRenamed={(renamedId, nextTitle) => {
            if (renamedId === conversationId) setTitle(nextTitle);
          }}
          onDeleted={(deletedId) => {
            if (deletedId === conversationId) {
              reset();
              navigate("/chat");
            }
          }}
        />
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
            <span>知识问答</span>
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
          {routeConversationId && messagesQuery.isLoading && turns.length === 0 ? (
            <div className="chat-history-state">
              <span />
              <p>正在载入会话记录…</p>
            </div>
          ) : routeConversationId && messagesQuery.isError && turns.length === 0 ? (
            <div className="chat-history-state chat-history-state--error">
              <strong>会话记录载入失败</strong>
              <p>
                {messagesQuery.error instanceof Error ? messagesQuery.error.message : "请稍后重试"}
              </p>
              <Button variant="secondary" onClick={() => void messagesQuery.refetch()}>
                重新载入
              </Button>
            </div>
          ) : turns.length === 0 ? (
            <section className="chat-empty-state">
              <p>基于知识库回答</p>
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
                        {turn.guidance ? (
                          <section className="guidance-choice" aria-label="选择知识范围">
                            <div className="guidance-choice__heading">
                              <span>范围确认</span>
                              <p>{turn.guidance.prompt}</p>
                            </div>
                            <div className="guidance-choice__options">
                              {turn.guidance.options.map((option, index) => (
                                <button
                                  type="button"
                                  key={option.intentCode}
                                  disabled={busy}
                                  onClick={() => void send(option.query, [option.intentCode])}
                                >
                                  <span>{String(index + 1).padStart(2, "0")}</span>
                                  <strong>{option.label}</strong>
                                  <CornerDownRight aria-hidden="true" />
                                </button>
                              ))}
                            </div>
                            {turn.guidance.allQuery && (
                              <button
                                className="guidance-choice__all"
                                type="button"
                                disabled={busy}
                                onClick={() =>
                                  void send(
                                    turn.guidance?.allQuery || "",
                                    turn.guidance?.options.map((option) => option.intentCode),
                                  )
                                }
                              >
                                检索以上全部范围
                                <ArrowUp aria-hidden="true" />
                              </button>
                            )}
                          </section>
                        ) : turn.content ? (
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
                          <p className="answer-status-note">生成已停止，以上为停止前保留的内容。</p>
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
                        {!turn.guidance &&
                          !turn.streaming &&
                          turn.persisted &&
                          turn.messageStatus === "NORMAL" && (
                          <div className="answer-followup">
                            <div className="answer-tools" aria-label="回答操作">
                              <span>这个回答有帮助吗</span>
                              <button
                                type="button"
                                className={cn(turn.vote === 1 && "is-active")}
                                aria-label="赞同回答"
                                aria-pressed={turn.vote === 1}
                                disabled={turn.feedbackPending}
                                onClick={() => void voteMessage(turn.id, 1)}
                              >
                                <ThumbsUp aria-hidden="true" />
                              </button>
                              <button
                                type="button"
                                className={cn(turn.vote === -1 && "is-active", "is-negative")}
                                aria-label="不赞同回答"
                                aria-pressed={turn.vote === -1}
                                disabled={turn.feedbackPending}
                                onClick={() => void voteMessage(turn.id, -1)}
                              >
                                <ThumbsDown aria-hidden="true" />
                              </button>
                              {turn.recommendedQuestions == null && (
                                <button
                                  type="button"
                                  className="answer-tools__recommend"
                                  disabled={turn.recommendationPending}
                                  onClick={() => void loadRecommendations(turn.id)}
                                >
                                  {turn.recommendationPending ? (
                                    <LoaderCircle className="is-spinning" aria-hidden="true" />
                                  ) : (
                                    <ListPlus aria-hidden="true" />
                                  )}
                                  {turn.recommendationPending ? "正在生成" : "后续问题"}
                                </button>
                              )}
                            </div>
                            {turn.recommendedQuestions && turn.recommendedQuestions.length > 0 && (
                              <div className="recommended-questions">
                                <span>接着问</span>
                                {turn.recommendedQuestions.map((question) => (
                                  <button
                                    type="button"
                                    key={question}
                                    onClick={() => askExample(question)}
                                  >
                                    {question}
                                    <ArrowUp aria-hidden="true" />
                                  </button>
                                ))}
                              </div>
                            )}
                            {turn.recommendationStatus === "EMPTY" && (
                              <p className="answer-action-note">当前回答没有合适的后续问题。</p>
                            )}
                            {turn.actionError && (
                              <p className="answer-action-note answer-action-note--error">
                                {turn.actionError}
                              </p>
                            )}
                          </div>
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
                <button
                  className="stop-stream-button"
                  type="button"
                  onClick={() => void stop()}
                  disabled={stopping}
                >
                  <Square aria-hidden="true" />
                  {stopping ? "正在停止" : "停止生成"}
                </button>
              ) : (
                <button className="send-question-button" type="submit" disabled={!draft.trim()}>
                  <ArrowUp aria-hidden="true" />
                  <span>发送</span>
                </button>
              )}
            </div>
          </div>
          <p>停止后保留已生成内容；同一任务的后续模型输出不会继续写入。</p>
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
