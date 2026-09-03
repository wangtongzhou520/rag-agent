import { create } from "zustand";

import { useAuthStore } from "@/features/auth/store";
import { stopChat, streamChat } from "@/features/chat/api";
import {
  abortStream,
  createStreamSnapshot,
  failStream,
  transitionStream,
  type StreamSnapshot,
} from "@/features/chat/machine";
import { StreamProtocolError } from "@/features/chat/sse";
import type { ChatTurn, ConversationMessage } from "@/features/chat/types";
import { ApiError } from "@/shared/api/error";

interface ChatState {
  conversationId?: string;
  title: string;
  turns: ChatTurn[];
  stream: StreamSnapshot;
  stopping: boolean;
  deepThinking: boolean;
  setDeepThinking: (enabled: boolean) => void;
  prepareConversation: (conversationId: string, title: string) => void;
  hydrateConversation: (
    conversationId: string,
    title: string,
    messages: ConversationMessage[],
  ) => void;
  setTitle: (title: string) => void;
  send: (question: string) => Promise<void>;
  stop: () => Promise<void>;
  reset: () => void;
}

let activeController: AbortController | undefined;
let generation = 0;

function clientId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function updateAssistant(turns: ChatTurn[], snapshot: StreamSnapshot): ChatTurn[] {
  let index = -1;
  for (let cursor = turns.length - 1; cursor >= 0; cursor -= 1) {
    if (turns[cursor].role === "assistant" && turns[cursor].streaming) {
      index = cursor;
      break;
    }
  }
  if (index === -1) return turns;

  const next = [...turns];
  next[index] = {
    ...next[index],
    id: snapshot.messageId || next[index].id,
    content: snapshot.response,
    thinking: snapshot.thinking,
    sources: snapshot.sources,
    messageStatus: snapshot.messageStatus,
    error: snapshot.error,
    streaming: ["connecting", "streaming", "finishing"].includes(snapshot.phase),
  };
  return next;
}

function historyTurns(messages: ConversationMessage[]): ChatTurn[] {
  return messages.map((message) => ({
    id: message.id,
    role: message.role,
    content: message.content,
    thinking: message.thinkingContent || undefined,
    sources: message.sources || undefined,
    messageStatus: message.messageStatus,
  }));
}

export const useChatStore = create<ChatState>((set, get) => ({
  title: "新对话",
  turns: [],
  stream: createStreamSnapshot(),
  stopping: false,
  deepThinking: false,
  setDeepThinking: (deepThinking) => set({ deepThinking }),
  prepareConversation: (conversationId, title) => {
    activeController?.abort();
    activeController = undefined;
    generation += 1;
    set({
      conversationId,
      title,
      turns: [],
      stream: createStreamSnapshot(),
      stopping: false,
    });
  },
  hydrateConversation: (conversationId, title, messages) =>
    set({
      conversationId,
      title,
      turns: historyTurns(messages),
      stream: createStreamSnapshot(),
      stopping: false,
    }),
  setTitle: (title) => set({ title }),
  send: async (rawQuestion) => {
    const question = rawQuestion.trim();
    if (!question || activeController) return;

    const controller = new AbortController();
    activeController = controller;
    const requestGeneration = ++generation;
    const assistantId = clientId("assistant");
    const connecting = createStreamSnapshot("connecting");

    set((state) => ({
      stream: connecting,
      stopping: false,
      turns: [
        ...state.turns,
        { id: clientId("user"), role: "user", content: question },
        { id: assistantId, role: "assistant", content: "", streaming: true },
      ],
    }));

    try {
      for await (const event of streamChat({
        question,
        conversationId: get().conversationId,
        deepThinking: get().deepThinking,
        signal: controller.signal,
      })) {
        if (requestGeneration !== generation) return;
        set((state) => {
          const stream = transitionStream(state.stream, event);
          return {
            stream,
            conversationId: stream.conversationId || state.conversationId,
            title: stream.title || state.title,
            turns: updateAssistant(state.turns, stream),
          };
        });
      }
      if (
        requestGeneration === generation &&
        !["completed", "cancelled"].includes(get().stream.phase)
      ) {
        throw new StreamProtocolError("连接已结束，但没有收到 done 终止事件");
      }
    } catch (error) {
      if (requestGeneration !== generation) return;
      if (
        error instanceof ApiError &&
        (error.httpStatus === 401 || error.message.includes("未登录"))
      ) {
        useAuthStore.getState().clear();
      }
      set((state) => {
        const stream =
          error instanceof DOMException && error.name === "AbortError"
            ? abortStream(state.stream)
            : failStream(state.stream, error instanceof Error ? error.message : "流式问答失败");
        return { stream, turns: updateAssistant(state.turns, stream) };
      });
    } finally {
      if (requestGeneration === generation) {
        activeController = undefined;
        set({ stopping: false });
      }
    }
  },
  stop: async () => {
    const controller = activeController;
    if (!controller || get().stopping) return;
    const taskId = get().stream.taskId;
    if (taskId) {
      set({ stopping: true });
      try {
        await stopChat(taskId);
        return;
      } catch {
        // 服务端停止失败时仍断开本地流，连接关闭会触发后端 producer 取消。
      }
    }

    generation += 1;
    controller.abort();
    activeController = undefined;
    set((state) => {
      const stream = abortStream(state.stream);
      return {
        stopping: false,
        stream,
        turns: updateAssistant(state.turns, stream),
      };
    });
  },
  reset: () => {
    activeController?.abort();
    activeController = undefined;
    generation += 1;
    set({
      conversationId: undefined,
      title: "新对话",
      turns: [],
      stream: createStreamSnapshot(),
      stopping: false,
    });
  },
}));
