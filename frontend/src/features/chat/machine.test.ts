import { describe, expect, it } from "vitest";

import { abortStream, createStreamSnapshot, transitionStream } from "@/features/chat/machine";

describe("chat stream state machine", () => {
  it("completes a normal meta-message-finish-done sequence", () => {
    let state = createStreamSnapshot("connecting");
    state = transitionStream(state, {
      event: "meta",
      data: { conversationId: "conversation-1", taskId: "task-1" },
    });
    state = transitionStream(state, {
      event: "message",
      data: { type: "think", delta: "分析" },
    });
    state = transitionStream(state, {
      event: "message",
      data: { type: "response", delta: "答案" },
    });
    state = transitionStream(state, {
      event: "finish",
      data: { messageId: "message-1", messageStatus: "NORMAL", sources: [] },
    });
    state = transitionStream(state, { event: "done", data: "[DONE]" });

    expect(state).toMatchObject({
      phase: "completed",
      thinking: "分析",
      response: "答案",
      messageId: "message-1",
    });
  });

  it("preserves rejected content through finish and done", () => {
    let state = transitionStream(createStreamSnapshot("connecting"), {
      event: "meta",
      data: { conversationId: "conversation-1", taskId: "task-1" },
    });
    state = transitionStream(state, {
      event: "reject",
      data: { type: "response", delta: "系统繁忙" },
    });
    state = transitionStream(state, {
      event: "finish",
      data: { messageStatus: "REJECTED" },
    });
    state = transitionStream(state, { event: "done", data: "[DONE]" });

    expect(state.phase).toBe("completed");
    expect(state.messageStatus).toBe("REJECTED");
    expect(state.response).toBe("系统繁忙");
  });

  it("stores structured guidance before the normal terminal sequence", () => {
    let state = transitionStream(createStreamSnapshot("connecting"), {
      event: "meta",
      data: { conversationId: "conversation-1", taskId: "task-1" },
    });
    state = transitionStream(state, {
      event: "message",
      data: { type: "response", delta: "请选择知识范围" },
    });
    state = transitionStream(state, {
      event: "guidance",
      data: {
        prompt: "请选择更接近你问题的知识范围",
        originalQuestion: "怎么配置",
        options: [
          {
            id: 1,
            intentCode: "product.standard",
            label: "产品 > 标准版",
            query: "怎么配置（知识范围：产品 > 标准版）",
          },
          {
            id: 2,
            intentCode: "product.enterprise",
            label: "产品 > 企业版",
            query: "怎么配置（知识范围：产品 > 企业版）",
          },
        ],
      },
    });
    state = transitionStream(state, {
      event: "finish",
      data: { messageId: "message-1", messageStatus: "NORMAL" },
    });
    state = transitionStream(state, { event: "done", data: "[DONE]" });

    expect(state.phase).toBe("completed");
    expect(state.guidance?.options[1].intentCode).toBe("product.enterprise");
  });

  it("marks client abort and ignores late frames", () => {
    const cancelled = abortStream(createStreamSnapshot("streaming"));
    const afterLateFrame = transitionStream(cancelled, {
      event: "message",
      data: { type: "response", delta: "late" },
    });
    expect(afterLateFrame).toBe(cancelled);
    expect(afterLateFrame.phase).toBe("cancelled");
  });

  it("rejects a message before meta", () => {
    expect(() =>
      transitionStream(createStreamSnapshot("connecting"), {
        event: "message",
        data: { type: "response", delta: "invalid" },
      }),
    ).toThrow("message 不能出现在 connecting 阶段");
  });
});
