import { describe, expect, it } from "vitest";

import { flattenIntentTree, intentBranchIds, intentTreeStats } from "@/features/intent/tree";
import type { IntentNode } from "@/features/intent/types";

const leaf: IntentNode = {
  id: 3,
  intentCode: "product.guide.install",
  name: "安装说明",
  level: 2,
  kind: 0,
  examples: [],
  collectionNames: ["product_docs"],
  enabled: false,
  fullPath: "产品 > 使用指南 > 安装说明",
  children: [],
};
const root: IntentNode = {
  id: 1,
  intentCode: "product",
  name: "产品",
  level: 0,
  kind: 0,
  examples: [],
  collectionNames: [],
  enabled: true,
  fullPath: "产品",
  children: [
    {
      ...leaf,
      id: 2,
      intentCode: "product.guide",
      name: "使用指南",
      level: 1,
      enabled: true,
      children: [leaf],
    },
  ],
};

describe("intent tree helpers", () => {
  it("flattens in display order and counts management states", () => {
    expect(flattenIntentTree([root]).map((node) => node.id)).toEqual([1, 2, 3]);
    expect(intentTreeStats([root])).toEqual({ total: 3, enabled: 2, leaves: 1 });
  });

  it("collects a branch for explicit batch selection", () => {
    expect(intentBranchIds(root)).toEqual([1, 2, 3]);
  });
});
