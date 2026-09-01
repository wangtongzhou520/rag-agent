import { ApiError } from "@/shared/api/error";

export interface ApiResult<T> {
  code: string;
  message: string;
  data: T;
  requestId?: string;
}

export interface PageResult<T> {
  records: T[];
  total: number;
  current: number;
  size: number;
  pages: number;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function unwrapResult<T>(payload: unknown, httpStatus?: number): T {
  if (!isRecord(payload) || typeof payload.code !== "string") {
    throw new ApiError("服务响应格式不正确", "INVALID_RESPONSE", undefined, httpStatus);
  }
  const requestId = typeof payload.requestId === "string" ? payload.requestId : undefined;
  if (payload.code !== "0") {
    const message = typeof payload.message === "string" ? payload.message : "请求失败";
    throw new ApiError(message, payload.code, requestId, httpStatus);
  }
  return payload.data as T;
}

export function normalizePage<T>(value: Omit<PageResult<T>, "pages"> & { pages?: number }) {
  const size = Math.max(1, Number(value.size) || 1);
  const total = Math.max(0, Number(value.total) || 0);
  return {
    ...value,
    current: Math.max(1, Number(value.current) || 1),
    size,
    total,
    pages: Math.max(1, Number(value.pages) || Math.ceil(total / size)),
  } satisfies PageResult<T>;
}
