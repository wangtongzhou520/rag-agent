import type { ChatStreamEvent, MessageStatus, SourceRef } from "@/features/chat/types";
import { StreamProtocolError } from "@/features/chat/sse";

export type StreamPhase =
  "idle" | "connecting" | "streaming" | "finishing" | "completed" | "failed" | "cancelled";

export interface StreamSnapshot {
  phase: StreamPhase;
  conversationId?: string;
  taskId?: string;
  messageId?: string | null;
  title?: string | null;
  thinking: string;
  response: string;
  sources: SourceRef[];
  messageStatus?: MessageStatus;
  error?: string;
}

export function createStreamSnapshot(phase: StreamPhase = "idle"): StreamSnapshot {
  return { phase, thinking: "", response: "", sources: [] };
}

function ensurePhase(snapshot: StreamSnapshot, allowed: StreamPhase[], event: string) {
  if (!allowed.includes(snapshot.phase)) {
    throw new StreamProtocolError(`${event} 不能出现在 ${snapshot.phase} 阶段`);
  }
}

export function transitionStream(
  snapshot: StreamSnapshot,
  incoming: ChatStreamEvent,
): StreamSnapshot {
  if (["completed", "failed", "cancelled"].includes(snapshot.phase)) return snapshot;

  switch (incoming.event) {
    case "meta":
      ensurePhase(snapshot, ["connecting"], "meta");
      return {
        ...snapshot,
        phase: "streaming",
        conversationId: incoming.data.conversationId,
        taskId: incoming.data.taskId,
      };
    case "message":
      ensurePhase(snapshot, ["streaming"], "message");
      return incoming.data.type === "think"
        ? { ...snapshot, thinking: snapshot.thinking + incoming.data.delta }
        : { ...snapshot, response: snapshot.response + incoming.data.delta };
    case "reject":
      ensurePhase(snapshot, ["streaming"], "reject");
      return {
        ...snapshot,
        phase: "finishing",
        response: snapshot.response + incoming.data.delta,
        messageStatus: "REJECTED",
      };
    case "finish":
      ensurePhase(snapshot, ["streaming", "finishing"], "finish");
      return {
        ...snapshot,
        phase: "finishing",
        messageId: incoming.data.messageId,
        title: incoming.data.title,
        sources: incoming.data.sources || [],
        messageStatus: incoming.data.messageStatus,
      };
    case "cancel":
      ensurePhase(snapshot, ["streaming"], "cancel");
      return {
        ...snapshot,
        phase: "finishing",
        messageId: incoming.data.messageId,
        title: incoming.data.title,
        sources: incoming.data.sources || [],
        messageStatus: "INTERRUPTED",
      };
    case "done":
      ensurePhase(snapshot, ["finishing"], "done");
      return {
        ...snapshot,
        phase: snapshot.messageStatus === "INTERRUPTED" ? "cancelled" : "completed",
      };
  }
}

export function failStream(snapshot: StreamSnapshot, error: string): StreamSnapshot {
  if (["completed", "cancelled"].includes(snapshot.phase)) return snapshot;
  return { ...snapshot, phase: "failed", error };
}

export function abortStream(snapshot: StreamSnapshot): StreamSnapshot {
  if (!["connecting", "streaming", "finishing"].includes(snapshot.phase)) return snapshot;
  return { ...snapshot, phase: "cancelled", messageStatus: "INTERRUPTED" };
}
