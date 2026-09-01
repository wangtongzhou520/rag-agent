import { describe, expect, it } from "vitest";

import { ApiError } from "@/shared/api/error";
import { normalizePage, unwrapResult } from "@/shared/api/result";

describe("unwrapResult", () => {
  it("returns data for a successful result", () => {
    expect(unwrapResult({ code: "0", message: "ok", data: { status: "UP" } })).toEqual({
      status: "UP",
    });
  });

  it("preserves business code and request id", () => {
    expect(() =>
      unwrapResult({
        code: "A0001",
        message: "未登录或登录已过期",
        data: null,
        requestId: "req-1",
      }),
    ).toThrowError(ApiError);
    try {
      unwrapResult({
        code: "A0001",
        message: "未登录或登录已过期",
        data: null,
        requestId: "req-1",
      });
    } catch (error) {
      expect(error).toMatchObject({ code: "A0001", requestId: "req-1" });
    }
  });

  it("rejects a malformed response", () => {
    expect(() => unwrapResult({ data: [] })).toThrow("服务响应格式不正确");
  });
});

describe("normalizePage", () => {
  it("derives pages from total and size", () => {
    expect(normalizePage({ records: [1], total: 21, current: 1, size: 10 }).pages).toBe(3);
  });

  it("keeps an empty result on page one", () => {
    expect(normalizePage({ records: [], total: 0, current: 0, size: 0 })).toMatchObject({
      current: 1,
      size: 1,
      total: 0,
      pages: 1,
    });
  });
});
