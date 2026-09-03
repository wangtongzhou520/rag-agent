import { afterEach, describe, expect, it, vi } from "vitest";

import { useChatStore } from "@/features/chat/store";

const apiMocks = vi.hoisted(() => ({
  deleteMessageFeedback: vi.fn(),
  generateRecommendedQuestions: vi.fn(),
  stopChat: vi.fn(),
  streamChat: vi.fn(),
  submitMessageFeedback: vi.fn(),
}));

vi.mock("@/features/chat/api", () => apiMocks);

describe("chat store server-side stop", () => {
  afterEach(() => {
    useChatStore.getState().reset();
    vi.clearAllMocks();
  });

  it("requests server stop and waits for cancel/done terminal events", async () => {
    let releaseStream: () => void = () => undefined;
    const stopped = new Promise<void>((resolve) => {
      releaseStream = resolve;
    });
    apiMocks.streamChat.mockImplementation(async function* () {
      yield {
        event: "meta",
        data: { conversationId: "conversation-1", taskId: "task-1" },
      };
      yield { event: "message", data: { type: "response", delta: "部分回答" } };
      await stopped;
      yield {
        event: "cancel",
        data: { messageId: "message-1", messageStatus: "INTERRUPTED" },
      };
      yield { event: "done", data: "[DONE]" };
    });
    apiMocks.stopChat.mockImplementation(async () => releaseStream());

    const sendPromise = useChatStore.getState().send("测试停止");
    await vi.waitFor(() => expect(useChatStore.getState().stream.taskId).toBe("task-1"));
    await useChatStore.getState().stop();
    await sendPromise;

    expect(apiMocks.stopChat).toHaveBeenCalledWith("task-1");
    expect(useChatStore.getState()).toMatchObject({
      stopping: false,
      stream: {
        phase: "cancelled",
        response: "部分回答",
        messageId: "message-1",
        messageStatus: "INTERRUPTED",
      },
    });
  });

  it("optimistically toggles feedback and removes the same vote", async () => {
    apiMocks.submitMessageFeedback.mockResolvedValue(null);
    apiMocks.deleteMessageFeedback.mockResolvedValue(null);
    useChatStore.getState().hydrateConversation("conversation-1", "历史会话", [
      {
        id: "message-1",
        conversationId: "conversation-1",
        role: "assistant",
        content: "回答",
        vote: null,
        recommendedQuestions: null,
        messageStatus: "NORMAL",
        createTime: 1,
      },
    ]);

    await useChatStore.getState().voteMessage("message-1", 1);
    expect(apiMocks.submitMessageFeedback).toHaveBeenCalledWith("message-1", 1);
    expect(useChatStore.getState().turns[0].vote).toBe(1);

    await useChatStore.getState().voteMessage("message-1", 1);
    expect(apiMocks.deleteMessageFeedback).toHaveBeenCalledWith("message-1");
    expect(useChatStore.getState().turns[0].vote).toBeNull();
  });

  it("stores generated follow-up questions on the assistant turn", async () => {
    apiMocks.generateRecommendedQuestions.mockResolvedValue({
      status: "SUCCESS",
      questions: ["下一步是什么？", "如何验证？"],
    });
    useChatStore.getState().hydrateConversation("conversation-1", "历史会话", [
      {
        id: "message-1",
        conversationId: "conversation-1",
        role: "assistant",
        content: "回答",
        vote: null,
        recommendedQuestions: null,
        messageStatus: "NORMAL",
        createTime: 1,
      },
    ]);

    await useChatStore.getState().loadRecommendations("message-1");

    expect(apiMocks.generateRecommendedQuestions).toHaveBeenCalledWith("message-1");
    expect(useChatStore.getState().turns[0]).toMatchObject({
      recommendationStatus: "SUCCESS",
      recommendedQuestions: ["下一步是什么？", "如何验证？"],
      recommendationPending: false,
    });
  });
});
