import { expect, test } from "@playwright/test";

const result = <T>(data: T) => ({ code: "0", message: "ok", data });

test("renders the blue login foundation", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "登录 Ragent AI" })).toBeVisible();
  await expect(page.getByText("RAG 信号轨", { exact: true })).toBeVisible();
});

test("streams an answer and opens its source context", async ({ page }) => {
  await page.addInitScript(() => window.localStorage.setItem("ragent.auth.token", "e2e-token"));
  await page.route("**/api/ragent/user/me", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(result({ userId: 1, username: "admin", role: "ADMIN" })),
    }),
  );
  await page.route("**/api/ragent/rag/v3/chat?*", (route) =>
    route.fulfill({
      contentType: "text/event-stream;charset=UTF-8",
      headers: { "cache-control": "no-cache" },
      body: [
        'event: meta\ndata: {"conversationId":"conversation-e2e","taskId":"task-e2e"}\n\n',
        'event: message\ndata: {"type":"think","delta":"正在核对检索结果"}\n\n',
        'event: message\ndata: {"type":"response","delta":"答案来自知识库 [1](#cite-1)。"}\n\n',
        'event: finish\ndata: {"messageId":"message-e2e","title":"检索说明","sources":[{"index":1,"docId":"1","docName":"RAG 设计文档.md","sourceType":"KB","fileType":"md","excerpt":"混合检索与来源引用设计。"}],"messageStatus":"NORMAL"}\n\n',
        "event: done\ndata: [DONE]\n\n",
      ].join(""),
    }),
  );
  await page.route("**/api/ragent/knowledge-base/docs/1/preview", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(result("# 混合检索\n\n问题理解、检索和重排组成完整链路。")),
    }),
  );

  await page.goto("/chat");
  await expect(page.getByRole("heading", { name: /可观察的知识路径/ })).toBeVisible();
  await page.getByLabel("输入问题").fill("当前检索流程是什么？");
  await page.getByRole("button", { name: "发送" }).click();

  await expect(page.getByText("答案来自知识库")).toBeVisible();
  await expect(page.getByText("回答已完成")).toBeVisible();
  await page.getByRole("link", { name: "1" }).click();
  await expect(page.getByText("RAG 设计文档.md")).toBeVisible();
  await expect(page.getByText("混合检索与来源引用设计。")).toBeVisible();
  await page.getByRole("button", { name: "预览文档" }).click();
  await expect(page.getByRole("heading", { name: "混合检索" })).toBeVisible();
});

test("manages knowledge bases through the admin console", async ({ page }) => {
  const records = [
    {
      id: 1,
      name: "产品知识库",
      collectionName: "product_docs",
      embeddingModel: "qwen3.7-text-embedding",
    },
  ];
  await page.addInitScript(() => window.localStorage.setItem("ragent.auth.token", "e2e-token"));
  await page.route("**/api/ragent/user/me", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(result({ userId: 1, username: "admin", role: "ADMIN" })),
    }),
  );
  await page.route("**/api/ragent/knowledge-base**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === "GET") {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          result({ records: [...records], total: records.length, current: 1, size: 20 }),
        ),
      });
    }
    if (request.method() === "POST") {
      const body = request.postDataJSON() as Omit<(typeof records)[number], "id">;
      records.push({ ...body, id: 2 });
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(result("2")) });
    }
    if (request.method() === "PUT") {
      const target = records.find((item) => path.endsWith(`/${item.id}`));
      if (target) Object.assign(target, request.postDataJSON());
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(result(null)) });
    }
    if (request.method() === "DELETE") {
      records.splice(
        records.findIndex((item) => path.endsWith(`/${item.id}`)),
        1,
      );
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(result(null)) });
    }
    return route.abort();
  });

  await page.goto("/admin/knowledge-bases");
  await expect(page.getByText("产品知识库")).toBeVisible();
  await page.getByRole("button", { name: "新建知识库" }).click();
  await page.getByLabel("知识库名称").fill("研发知识库");
  await page.getByLabel("Collection Name").fill("engineering_docs");
  await page.getByRole("button", { name: "保存知识库" }).click();
  await expect(page.getByText("研发知识库")).toBeVisible();

  await page.getByRole("button", { name: "编辑 研发知识库" }).click();
  await page.getByLabel("知识库名称").fill("研发资料库");
  await page.getByRole("button", { name: "保存知识库" }).click();
  await expect(page.getByText("研发资料库")).toBeVisible();

  await page.getByRole("button", { name: "删除 研发资料库" }).click();
  await page.getByRole("button", { name: "确认删除" }).click();
  await expect(page.getByText("研发资料库")).toHaveCount(0);
});

test("imports documents and manages chunks", async ({ page }, testInfo) => {
  const documents = [
    {
      id: 11,
      kbId: 1,
      docName: "产品指南.md",
      enabled: true,
      chunkCount: 2,
      fileType: "md",
      mimeType: "text/markdown",
      fileSize: 2048,
      status: "success",
      sourceType: "file",
      ingestionSpec: null,
    },
  ];
  const chunks = [
    {
      id: "11111111-1111-4111-8111-111111111111",
      docId: 11,
      chunkIndex: 0,
      content: "Ragent 使用混合检索整合多路召回结果。",
      enabled: true,
    },
    {
      id: "22222222-2222-4222-8222-222222222222",
      docId: 11,
      chunkIndex: 1,
      content: "重排模型负责优化最终上下文顺序。",
      enabled: true,
    },
  ];

  await page.addInitScript(() => window.localStorage.setItem("ragent.auth.token", "e2e-token"));
  await page.route("**/api/ragent/user/me", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(result({ userId: 1, username: "admin", role: "ADMIN" })),
    }),
  );
  await page.route("**/api/ragent/knowledge-base**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path.endsWith("/docs/ingestion-spec-schema")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          result({
            version: 2,
            parseProfiles: ["fast", "fidelity"],
            budget: {
              maxChars: { default: 1024, min: 128, max: 50000, whole: -1 },
              overlapChars: { default: 128, min: 0 },
              rowsPerChunk: { default: 50, min: 1, max: 1000 },
              toleranceFactor: { default: 3 },
            },
          }),
        ),
      });
    }
    if (path.endsWith("/knowledge-base/1") && request.method() === "GET") {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          result({
            id: 1,
            name: "产品知识库",
            collectionName: "product_docs",
            embeddingModel: "qwen3.7-text-embedding",
          }),
        ),
      });
    }
    if (path.endsWith("/knowledge-base/1/docs") && request.method() === "GET") {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          result({ records: documents, total: documents.length, current: 1, size: 20 }),
        ),
      });
    }
    if (path.endsWith("/knowledge-base/1/docs/upload") && request.method() === "POST") {
      const document = {
        ...documents[0],
        id: 12,
        docName: "test-guide.md",
        chunkCount: 0,
        status: "pending",
        fileSize: 24,
      };
      documents.push(document);
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(result(document)),
      });
    }
    if (path.endsWith("/knowledge-base/docs/12/chunk") && request.method() === "POST") {
      documents[1].status = "running";
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(result(null)) });
    }
    if (path.endsWith("/knowledge-base/docs/11") && request.method() === "GET") {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(result(documents[0])),
      });
    }
    if (path.endsWith("/knowledge-base/docs/11/chunks") && request.method() === "GET") {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          result({ records: chunks, total: chunks.length, current: 1, size: 20 }),
        ),
      });
    }
    if (
      path.endsWith("/knowledge-base/docs/11/chunks/batch-enable") &&
      request.method() === "PATCH"
    ) {
      chunks.forEach((chunk) => {
        chunk.enabled = url.searchParams.get("value") === "true";
      });
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(result(null)) });
    }
    if (path.includes("/knowledge-base/docs/11/chunks/") && request.method() === "PUT") {
      const target = chunks.find((chunk) => path.endsWith(chunk.id));
      if (target) target.content = (request.postDataJSON() as { content: string }).content;
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(result(null)) });
    }
    return route.fulfill({ contentType: "application/json", body: JSON.stringify(result(null)) });
  });

  await page.goto("/admin/knowledge-bases/1/documents");
  await expect(page.getByRole("heading", { name: "文档管理" })).toBeVisible();
  await expect(page.getByText("产品指南.md")).toBeVisible();

  await page.getByRole("button", { name: "导入文档" }).click();
  await page.getByLabel("选择文档文件").setInputFiles("tests/fixtures/test-guide.md");
  await page.getByRole("button", { name: "创建文档" }).click();
  await expect(page.getByText("test-guide.md")).toBeVisible();
  await page.getByRole("button", { name: "开始分块 test-guide.md" }).click();
  await expect(page.getByRole("table").getByText("处理中")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("document-workbench.png"), fullPage: true });

  const documentRow = page.getByRole("row").filter({ hasText: "产品指南.md" });
  await documentRow.getByRole("link", { name: "2" }).click();
  await expect(page.getByRole("heading", { name: "产品指南.md" })).toBeVisible();
  await expect(page.getByText("Ragent 使用混合检索整合多路召回结果。")).toBeVisible();

  await page.getByText("选择当前页").click();
  await page.getByRole("button", { name: "批量停用" }).click();
  await expect(page.getByText("已停用 2 个 Chunk")).toBeVisible();

  await page.getByRole("button", { name: "编辑 Chunk 0" }).click();
  await page.getByLabel("分块内容").fill("更新后的混合检索说明。");
  await page.getByRole("button", { name: "保存并重新向量化" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.getByText("更新后的混合检索说明。")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("chunk-workbench.png"), fullPage: true });
});
