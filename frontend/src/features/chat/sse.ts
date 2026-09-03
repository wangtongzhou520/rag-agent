import { z } from "zod";

import {
  completionSchema,
  guidanceSchema,
  messageDeltaSchema,
  metaSchema,
  type ChatStreamEvent,
} from "@/features/chat/types";

export interface SseFrame {
  event: string;
  data: string;
  id?: string;
}

export class StreamProtocolError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "StreamProtocolError";
  }
}

function parseFrame(rawFrame: string): SseFrame | null {
  let event = "message";
  let id: string | undefined;
  const data: string[] = [];

  for (const line of rawFrame.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) continue;
    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    let value = separator === -1 ? "" : line.slice(separator + 1);
    if (value.startsWith(" ")) value = value.slice(1);

    if (field === "event") event = value;
    if (field === "data") data.push(value);
    if (field === "id") id = value;
  }

  if (data.length === 0) return null;
  return { event, data: data.join("\n"), id };
}

export class SseParser {
  private readonly decoder = new TextDecoder();
  private buffer = "";

  push(chunk: Uint8Array): SseFrame[] {
    this.buffer += this.decoder.decode(chunk, { stream: true });
    return this.drain(false);
  }

  finish(): SseFrame[] {
    this.buffer += this.decoder.decode();
    return this.drain(true);
  }

  private drain(flush: boolean): SseFrame[] {
    const frames: SseFrame[] = [];
    let boundary = /\r?\n\r?\n/.exec(this.buffer);

    while (boundary) {
      const rawFrame = this.buffer.slice(0, boundary.index);
      this.buffer = this.buffer.slice(boundary.index + boundary[0].length);
      const frame = parseFrame(rawFrame);
      if (frame) frames.push(frame);
      boundary = /\r?\n\r?\n/.exec(this.buffer);
    }

    if (flush && this.buffer.trim()) {
      const frame = parseFrame(this.buffer);
      if (frame) frames.push(frame);
      this.buffer = "";
    }

    return frames;
  }
}

function decodeJson(data: string): unknown {
  try {
    return JSON.parse(data);
  } catch {
    throw new StreamProtocolError("SSE data 不是有效 JSON");
  }
}

function decodePayload<T>(schema: z.ZodType<T>, data: string, event: string): T {
  const parsed = schema.safeParse(decodeJson(data));
  if (!parsed.success) throw new StreamProtocolError(`${event} 事件字段不符合契约`);
  return parsed.data;
}

export function decodeChatEvent(frame: SseFrame): ChatStreamEvent {
  switch (frame.event) {
    case "meta":
      return { event: "meta", data: decodePayload(metaSchema, frame.data, "meta") };
    case "message":
      return { event: "message", data: decodePayload(messageDeltaSchema, frame.data, "message") };
    case "finish":
      return { event: "finish", data: decodePayload(completionSchema, frame.data, "finish") };
    case "cancel":
      return { event: "cancel", data: decodePayload(completionSchema, frame.data, "cancel") };
    case "reject":
      return { event: "reject", data: decodePayload(messageDeltaSchema, frame.data, "reject") };
    case "guidance":
      return { event: "guidance", data: decodePayload(guidanceSchema, frame.data, "guidance") };
    case "done":
      if (frame.data !== "[DONE]") throw new StreamProtocolError("done 事件缺少 [DONE] 哨兵");
      return { event: "done", data: "[DONE]" };
    default:
      throw new StreamProtocolError(`不支持的 SSE 事件：${frame.event}`);
  }
}

export async function* readSseStream(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<ChatStreamEvent> {
  const reader = body.getReader();
  const parser = new SseParser();

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      for (const frame of parser.push(value)) yield decodeChatEvent(frame);
    }
    for (const frame of parser.finish()) yield decodeChatEvent(frame);
  } finally {
    reader.releaseLock();
  }
}
