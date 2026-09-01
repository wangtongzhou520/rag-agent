import { z } from "zod";

export const sourceRefSchema = z.object({
  index: z.number().int().positive(),
  docId: z.string(),
  docName: z.string(),
  sourceType: z.string(),
  fileType: z.string().optional(),
  url: z.string().optional(),
  excerpt: z.string().optional(),
});

export const messageDeltaSchema = z.object({
  type: z.enum(["think", "response"]),
  delta: z.string(),
});

export const completionSchema = z.object({
  messageId: z.string().nullable().optional(),
  title: z.string().nullable().optional(),
  sources: z.array(sourceRefSchema).nullable().optional(),
  messageStatus: z.enum(["NORMAL", "INTERRUPTED", "REJECTED"]),
});

export const metaSchema = z.object({
  conversationId: z.string().min(1),
  taskId: z.string().min(1),
});

export type SourceRef = z.infer<typeof sourceRefSchema>;
export type MessageDelta = z.infer<typeof messageDeltaSchema>;
export type CompletionPayload = z.infer<typeof completionSchema>;
export type MetaPayload = z.infer<typeof metaSchema>;
export type MessageStatus = CompletionPayload["messageStatus"];

export type ChatStreamEvent =
  | { event: "meta"; data: MetaPayload }
  | { event: "message"; data: MessageDelta }
  | { event: "finish"; data: CompletionPayload }
  | { event: "cancel"; data: CompletionPayload }
  | { event: "reject"; data: MessageDelta }
  | { event: "done"; data: "[DONE]" };

export interface ChatTurn {
  id: string;
  role: "user" | "assistant";
  content: string;
  thinking?: string;
  sources?: SourceRef[];
  messageStatus?: MessageStatus;
  error?: string;
  streaming?: boolean;
}
