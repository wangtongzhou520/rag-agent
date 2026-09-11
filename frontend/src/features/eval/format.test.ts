import { describe, expect, it } from "vitest";

import { formatEvalLatency, routeLabel } from "@/features/eval/format";
import type { EvalResponse } from "@/features/eval/types";

const response: EvalResponse = {
  retrievedDocIds: [],
  retrievedChunkIds: [],
  retrievedContexts: [],
  retrievedScores: [],
  retrievedContextDocIds: [],
  retrievalCollections: [],
  mcpContext: "",
  hasMcpSuccess: false,
  needsClarification: false,
  hasMcpFailure: false,
  hasKb: false,
  subIntents: [],
  intentLeafIds: [],
  latencyMs: 0,
};

describe("eval formatting", () => {
  it("describes combined evidence routes", () => {
    expect(routeLabel({ ...response, hasKb: true, needsClarification: true })).toBe(
      "知识库 · 等待补参",
    );
    expect(routeLabel(response)).toBe("未命中证据");
  });

  it("formats milliseconds and seconds", () => {
    expect(formatEvalLatency(842)).toBe("842 ms");
    expect(formatEvalLatency(1250)).toBe("1.25 s");
  });
});
