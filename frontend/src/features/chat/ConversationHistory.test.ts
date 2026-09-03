import { afterEach, describe, expect, it } from "vitest";

import { formatConversationTime } from "@/features/chat/conversation";
import { useChatStore } from "@/features/chat/store";

describe("conversation history", () => {
  afterEach(() => useChatStore.getState().reset());

  it("formats same-day and older timestamps compactly", () => {
    const now = new Date(2026, 8, 3, 12).getTime();
    expect(formatConversationTime(new Date(2026, 8, 3, 9, 25).getTime(), now)).toBe("09:25");
    expect(formatConversationTime(new Date(2026, 7, 31, 9, 25).getTime(), now)).toMatch(/08.*31/);
  });

  it("hydrates API messages into renderable chat turns", () => {
    useChatStore.getState().hydrateConversation("conversation-1", "历史会话", [
      {
        id: "message-1",
        conversationId: "conversation-1",
        role: "assistant",
        content: "历史回答",
        thinkingContent: "历史思考",
        sources: [],
        messageStatus: "NORMAL",
        createTime: 1_788_420_600_000,
      },
    ]);

    expect(useChatStore.getState()).toMatchObject({
      conversationId: "conversation-1",
      title: "历史会话",
      turns: [
        {
          id: "message-1",
          role: "assistant",
          content: "历史回答",
          thinking: "历史思考",
          messageStatus: "NORMAL",
        },
      ],
    });
  });
});
