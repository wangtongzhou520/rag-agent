import { create } from "zustand";

import { useAuthStore } from "@/features/auth/store";
import { streamChat } from "@/features/chat/api";
import {
  abortStream,
  createStreamSnapshot,
  failStream,
  transitionStream,
  type StreamSnapshot,
} from "@/features/chat/machine";
import { StreamProtocolError } from "@/features/chat/sse";
import type { ChatTurn } from "@/features/chat/types";
import { ApiError } from "@/shared/api/error";

interface ChatState {
  conversationId?: string;
  title: string;
  turns: ChatTurn[];
  stream: StreamSnapshot;
  deepThinking: boolean;
  setDeepThinking: (enabled: boolean) => void;
  send: (question: string) => Promise<void>;
  stop: () => void;
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

export const useChatStore = create<ChatState>((set, get) => ({
  title: "新对话",
  turns: [],
  stream: createStreamSnapshot(),
  deepThinking: false,
  setDeepThinking: (deepThinking) => set({ deepThinking }),
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
      if (requestGeneration === generation) activeController = undefined;
    }
  },
  stop: () => {
    if (!activeController) return;
    generation += 1;
    activeController.abort();
    activeController = undefined;
    set((state) => {
      const stream = abortStream(state.stream);
      return { stream, turns: updateAssistant(state.turns, stream) };
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
    });
  },
}));
