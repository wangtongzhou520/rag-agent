import {
  formatDuration,
  formatTraceTime,
  shortTraceId,
  traceStatusName,
} from "@/features/trace/format";

describe("trace display formatting", () => {
  it("formats millisecond and second durations", () => {
    expect(formatDuration(820)).toBe("820 ms");
    expect(formatDuration(1_250)).toBe("1.25 s");
    expect(formatDuration(null)).toBe("—");
  });

  it("uses Chinese status labels without hiding unknown values", () => {
    expect(traceStatusName("SUCCESS")).toBe("成功");
    expect(traceStatusName("QUEUED")).toBe("QUEUED");
  });

  it("shortens long identifiers from the middle", () => {
    expect(shortTraceId("01994111-1111-7111-8111-111111111111")).toBe("01994111…11111111");
  });

  it("formats nullable epoch milliseconds", () => {
    expect(formatTraceTime(null)).toBe("—");
    expect(formatTraceTime(Number.NaN)).toBe("—");
  });
});
