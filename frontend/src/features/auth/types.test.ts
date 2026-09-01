import { describe, expect, it } from "vitest";

import { normalizeRole } from "@/features/auth/types";

describe("normalizeRole", () => {
  it.each(["admin", "ADMIN", "Admin"])("normalizes %s as admin", (role) => {
    expect(normalizeRole(role)).toBe("admin");
  });

  it("uses user for unknown roles", () => {
    expect(normalizeRole("viewer")).toBe("user");
  });
});
