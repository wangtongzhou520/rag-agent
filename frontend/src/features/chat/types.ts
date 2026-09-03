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

export const guidanceOptionSchema = z.object({
  id: z.number().int().positive(),
  intentCode: z.string().min(1),
  label: z.string().min(1),
  query: z.string().min(1).max(4000),
});

export const guidanceSchema = z.object({
  prompt: z.string().min(1),
  originalQuestion: z.string().min(1),
  options: z.array(guidanceOptionSchema).min(2).max(6),
  allQuery: z.string().min(1).max(4000).nullable().optional(),
});

export type SourceRef = z.infer<typeof sourceRefSchema>;
export type MessageDelta = z.infer<typeof messageDeltaSchema>;
export type CompletionPayload = z.infer<typeof completionSchema>;
export type MetaPayload = z.infer<typeof metaSchema>;
export type MessageStatus = CompletionPayload["messageStatus"];
export type RecommendationStatus = "SUCCESS" | "EMPTY" | "FAILED";
export type GuidancePayload = z.infer<typeof guidanceSchema>;

export type ChatStreamEvent =
  | { event: "meta"; data: MetaPayload }
  | { event: "message"; data: MessageDelta }
  | { event: "finish"; data: CompletionPayload }
  | { event: "cancel"; data: CompletionPayload }
  | { event: "reject"; data: MessageDelta }
  | { event: "guidance"; data: GuidancePayload }
  | { event: "done"; data: "[DONE]" };

export interface ChatTurn {
  id: string;
  role: "user" | "assistant";
  content: string;
  thinking?: string;
  sources?: SourceRef[];
  messageStatus?: MessageStatus;
  vote?: 1 | -1 | null;
  recommendedQuestions?: string[] | null;
  recommendationStatus?: RecommendationStatus;
  guidance?: GuidancePayload;
  feedbackPending?: boolean;
  recommendationPending?: boolean;
  actionError?: string;
  persisted?: boolean;
  error?: string;
  streaming?: boolean;
}

export interface RecommendedQuestionsResult {
  status: RecommendationStatus;
  questions: string[];
}

export interface ConversationSummary {
  conversationId: string;
  title: string;
  lastTime: number;
}

export interface ConversationMessage {
  id: string;
  conversationId: string;
  role: "user" | "assistant";
  content: string;
  thinkingContent?: string | null;
  thinkingDuration?: number | null;
  vote?: 1 | -1 | null;
  sources?: SourceRef[] | null;
  recommendedQuestions?: string[] | null;
  messageStatus: MessageStatus;
  createTime: number;
}
