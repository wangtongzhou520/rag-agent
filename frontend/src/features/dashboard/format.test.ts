import { describe, expect, it } from "vitest";

import {
  describeKpiDelta,
  formatDashboardDuration,
  formatPercent,
} from "@/features/dashboard/format";

describe("dashboard formatting", () => {
  it("distinguishes period additions from comparisons", () => {
    const kpi = { value: 12, delta: 3, deltaPct: 33.3 };
    expect(describeKpiDelta(kpi, false)).toBe("本周期新增 +3");
    expect(describeKpiDelta(kpi, true)).toBe("环比 +33.3% · +3");
  });

  it("formats rates and latency consistently", () => {
    expect(formatPercent(99)).toBe("99.0%");
    expect(formatDashboardDuration(880)).toBe("880 ms");
    expect(formatDashboardDuration(2_500)).toBe("2.50 s");
  });
});
