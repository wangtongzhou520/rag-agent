import { describe, expect, it } from "vitest";

import { buildConsoleSearchResults, documentSearchMeta } from "./globalSearch";

describe("console global search helpers", () => {
  it("keeps knowledge bases before documents and builds their navigation targets", () => {
    const results = buildConsoleSearchResults(
      [
        {
          id: 7,
          name: "产品知识库",
          collectionName: "product_docs",
          embeddingModel: "qwen3.7-text-embedding",
        },
      ],
      [
        {
          id: 11,
          kbId: 7,
          docName: "产品指南.md",
          enabled: true,
          chunkCount: 2,
          status: "success",
          sourceType: "file",
        },
      ],
    );

    expect(results).toEqual([
      {
        key: "base-7",
        kind: "base",
        label: "产品知识库",
        meta: "product_docs",
        target: "/admin/knowledge-bases/7/documents",
      },
      {
        key: "document-11",
        kind: "document",
        label: "产品指南.md",
        meta: "已完成 · 2 个 Chunk",
        target: "/admin/documents/11/chunks",
      },
    ]);
  });

  it("falls back to an unknown backend status without hiding it", () => {
    expect(documentSearchMeta("paused", 0)).toBe("paused · 0 个 Chunk");
  });
});
