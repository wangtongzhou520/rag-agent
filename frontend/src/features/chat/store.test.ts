import { afterEach, describe, expect, it, vi } from "vitest";

import { useChatStore } from "@/features/chat/store";

const apiMocks = vi.hoisted(() => ({
  stopChat: vi.fn(),
  streamChat: vi.fn(),
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
});
