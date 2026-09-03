import { API_BASE_URL, request, tokenStorage } from "@/shared/api/client";
import { ApiError } from "@/shared/api/error";
import { readSseStream } from "@/features/chat/sse";
import type {
  ChatStreamEvent,
  ConversationMessage,
  ConversationSummary,
} from "@/features/chat/types";

export interface StreamChatInput {
  question: string;
  conversationId?: string;
  deepThinking: boolean;
  signal: AbortSignal;
}

export function getDocumentPreview(docId: string) {
  return request<string>({ method: "GET", url: `/knowledge-base/docs/${docId}/preview` });
}

export function listConversations() {
  return request<ConversationSummary[]>({ method: "GET", url: "/conversations" });
}

export function listConversationMessages(conversationId: string) {
  return request<ConversationMessage[]>({
    method: "GET",
    url: `/conversations/${conversationId}/messages`,
  });
}

export function renameConversation(conversationId: string, title: string) {
  return request<null>({
    method: "PUT",
    url: `/conversations/${conversationId}`,
    data: { title },
  });
}

export function deleteConversation(conversationId: string) {
  return request<null>({ method: "DELETE", url: `/conversations/${conversationId}` });
}

async function responseError(response: Response): Promise<ApiError> {
  let message = `问答请求失败（HTTP ${response.status}）`;
  let code = "HTTP_ERROR";
  let requestId = response.headers.get("x-request-id") || undefined;

  try {
    const payload = (await response.json()) as {
      code?: string;
      message?: string;
      requestId?: string;
    };
    if (payload.message) message = payload.message;
    if (payload.code) code = payload.code;
    if (payload.requestId) requestId = payload.requestId;
  } catch {
    // Keep the HTTP fallback when the body is not JSON.
  }

  return new ApiError(message, code, requestId, response.status);
}

export async function* streamChat(input: StreamChatInput): AsyncGenerator<ChatStreamEvent> {
  const params = new URLSearchParams({
    question: input.question,
    deepThinking: String(input.deepThinking),
  });
  if (input.conversationId) params.set("conversationId", input.conversationId);

  const token = tokenStorage.get();
  const response = await fetch(`${API_BASE_URL}/rag/v3/chat?${params}`, {
    method: "GET",
    headers: {
      Accept: "text/event-stream;charset=UTF-8",
      ...(token ? { Authorization: token } : {}),
    },
    signal: input.signal,
  });

  const contentType = response.headers.get("content-type") || "";
  if (!response.ok || contentType.includes("application/json")) throw await responseError(response);
  if (!response.body) throw new ApiError("浏览器未提供流式响应体", "EMPTY_STREAM");

  yield* readSseStream(response.body);
}
