import { describe, expect, it } from "vitest";

import { decodeChatEvent, SseParser, StreamProtocolError } from "@/features/chat/sse";

const encoder = new TextEncoder();

describe("SseParser", () => {
  it("handles split frames, sticky frames and UTF-8 boundaries", () => {
    const parser = new SseParser();
    const bytes = encoder.encode(
      'event: message\ndata: {"type":"response","delta":"你好"}\n\n' +
        "event: done\ndata: [DONE]\n\n",
    );

    const frames = [
      ...parser.push(bytes.slice(0, 49)),
      ...parser.push(bytes.slice(49, 52)),
      ...parser.push(bytes.slice(52)),
      ...parser.finish(),
    ];

    expect(frames).toHaveLength(2);
    expect(decodeChatEvent(frames[0])).toEqual({
      event: "message",
      data: { type: "response", delta: "你好" },
    });
    expect(decodeChatEvent(frames[1])).toEqual({ event: "done", data: "[DONE]" });
  });

  it("joins multiple data lines and accepts CRLF", () => {
    const parser = new SseParser();
    const [frame] = parser.push(
      encoder.encode("event: note\r\ndata: first\r\ndata: second\r\n\r\n"),
    );
    expect(frame).toEqual({ event: "note", data: "first\nsecond", id: undefined });
  });

  it("rejects unknown events and malformed payloads", () => {
    expect(() => decodeChatEvent({ event: "ping", data: "{}" })).toThrow(StreamProtocolError);
    expect(() => decodeChatEvent({ event: "meta", data: "{}" })).toThrow("meta 事件字段不符合契约");
  });
});
