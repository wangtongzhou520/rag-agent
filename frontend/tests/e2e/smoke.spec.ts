import { expect, test } from "@playwright/test";

import type { IntentNode, IntentNodeWrite } from "@/features/intent/types";
import type { QueryTermMapping, QueryTermMappingWrite } from "@/features/mapping/types";
import type { RagTraceDetail, RagTraceRun } from "@/features/trace/types";

const result = <T>(data: T) => ({ code: "0", message: "ok", data });

test("renders the blue login foundation", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "登录 Ragent AI" })).toBeVisible();
  await expect(page.getByText("知识库与文档管理", { exact: true })).toBeVisible();
});

test("shows real dashboard metrics and switches the trend scope", async ({ page }, testInfo) => {
  const start = Date.parse("2026-09-04T08:00:00.000Z");
  await page.addInitScript(() => window.localStorage.setItem("ragent.auth.token", "e2e-token"));
  await page.route("**/api/ragent/user/me", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(result({ userId: 1, username: "admin", role: "ADMIN" })),
    }),
  );
  await page.route("**/api/ragent/admin/dashboard/**", (route) => {
    const url = new URL(route.request().url());
    const window = url.searchParams.get("window") || "24h";
    if (url.pathname.endsWith("/overview")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          result({
            window,
            compareWindow: `prev_${window}`,
            updatedAt: start,
            kpis: {
              totalUsers: { value: 128, delta: 4, deltaPct: null },
              activeUsers: { value: 42, delta: 6, deltaPct: 16.7 },
              totalSessions: { value: 936, delta: 51, deltaPct: null },
              sessions24h: { value: 51, delta: 8, deltaPct: 18.6 },
              totalMessages: { value: 2840, delta: 173, deltaPct: null },
              messages24h: { value: 173, delta: 21, deltaPct: 13.8 },
            },
          }),
        ),
      });
    }
    if (url.pathname.endsWith("/performance")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          result({
            window,
            avgLatencyMs: 2420,
            p95LatencyMs: 6830,
            successRate: 98.4,
            errorRate: 1.6,
            noDocRate: 4.2,
            slowRate: 0.8,
          }),
        ),
      });
    }
    const quality = url.searchParams.get("metric") === "quality";
    return route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        result({
          metric: url.searchParams.get("metric"),
          window,
          granularity: window === "24h" ? "hour" : "day",
          series: quality
            ? [
                {
                  name: "错误率",
                  points: [1.2, 2.5, 1.6].map((value, index) => ({
                    ts: start + index * 3_600_000,
                    value,
                  })),
                },
                {
                  name: "无知识率",
                  points: [3.4, 5.1, 4.2].map((value, index) => ({
                    ts: start + index * 3_600_000,
                    value,
                  })),
                },
              ]
            : [
                {
                  name: "会话数",
                  points: [32, 44, 51].map((value, index) => ({
                    ts: start + index * 3_600_000,
                    value,
                  })),
                },
              ],
        }),
      ),
    });
  });

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/admin\/dashboard$/);
  await expect(page.getByRole("heading", { name: "系统概览" })).toBeVisible();
  await expect(page.getByText("98.4%")).toBeVisible();
  await expect(page.getByText("2.42 s")).toBeVisible();
  await page.getByRole("button", { name: "质量", exact: true }).click();
  const legend = page.locator(".dashboard-chart__legend");
  await expect(legend.getByText("错误率", { exact: true })).toBeVisible();
  await expect(legend.getByText("无知识率", { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("dashboard-desktop.png"), fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: "系统概览" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("dashboard-mobile.png"), fullPage: true });
});

test("streams an answer and opens its source context", async ({ page }) => {
  const feedbackRequests: Array<{ method: string; vote?: number }> = [];
  await page.addInitScript(() => window.localStorage.setItem("ragent.auth.token", "e2e-token"));
  await page.route("**/api/ragent/user/me", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(result({ userId: 1, username: "admin", role: "ADMIN" })),
    }),
  );
  await page.route("**/api/ragent/conversations", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(result([])) }),
  );
  await page.route("**/api/ragent/conversations/*/messages", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(result([])) }),
  );
  await page.route("**/api/ragent/conversations/messages/message-e2e/feedback", (route) => {
    feedbackRequests.push({
      method: route.request().method(),
      vote: (route.request().postDataJSON() as { vote?: number } | null)?.vote,
    });
    return route.fulfill({ contentType: "application/json", body: JSON.stringify(result(null)) });
  });
  await page.route(
    "**/api/ragent/conversations/messages/message-e2e/recommended-questions",
    (route) =>
      route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          result({ status: "SUCCESS", questions: ["如何验证检索结果？", "怎样查看运行轨迹？"] }),
        ),
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
  await page.getByRole("button", { name: "赞同回答", exact: true }).click();
  await expect(page.getByRole("button", { name: "赞同回答", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(feedbackRequests).toEqual([{ method: "POST", vote: 1 }]);
  await page.getByRole("button", { name: "后续问题" }).click();
  await expect(page.getByRole("button", { name: /如何验证检索结果/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /怎样查看运行轨迹/ })).toBeVisible();
  await page.getByRole("link", { name: "1" }).click();
  await expect(page.getByText("RAG 设计文档.md")).toBeVisible();
  await expect(page.getByText("混合检索与来源引用设计。")).toBeVisible();
  await page.getByRole("button", { name: "预览文档" }).click();
  await expect(page.getByRole("heading", { name: "混合检索" })).toBeVisible();
});

test("selects a structured ambiguity scope and continues the conversation", async ({ page }) => {
  let chatRequests = 0;
  let selectedQuestion = "";
  let selectedIntentCodes = "";
  await page.addInitScript(() => window.localStorage.setItem("ragent.auth.token", "e2e-token"));
  await page.route("**/api/ragent/user/me", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(result({ userId: 1, username: "admin", role: "ADMIN" })),
    }),
  );
  await page.route("**/api/ragent/conversations", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(result([])) }),
  );
  await page.route("**/api/ragent/conversations/*/messages", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(result([])) }),
  );
  await page.route("**/api/ragent/rag/v3/chat?*", (route) => {
    chatRequests += 1;
    selectedQuestion = new URL(route.request().url()).searchParams.get("question") || "";
    selectedIntentCodes = new URL(route.request().url()).searchParams.get("intentCodes") || "";
    const body =
      chatRequests === 1
        ? [
            'event: meta\ndata: {"conversationId":"guidance-e2e","taskId":"task-guidance"}\n\n',
            'event: message\ndata: {"type":"response","delta":"这个问题可能对应多个知识范围。"}\n\n',
            'event: guidance\ndata: {"prompt":"请选择更接近你问题的知识范围","originalQuestion":"怎么配置","options":[{"id":1,"intentCode":"product.standard","label":"产品 > 标准版","query":"怎么配置（知识范围：产品 > 标准版）"},{"id":2,"intentCode":"product.enterprise","label":"产品 > 企业版","query":"怎么配置（知识范围：产品 > 企业版）"}],"allQuery":"怎么配置（知识范围：产品 > 标准版、产品 > 企业版）"}\n\n',
            'event: finish\ndata: {"messageId":"guidance-message","messageStatus":"NORMAL"}\n\n',
            "event: done\ndata: [DONE]\n\n",
          ].join("")
        : [
            'event: meta\ndata: {"conversationId":"guidance-e2e","taskId":"task-answer"}\n\n',
            'event: message\ndata: {"type":"response","delta":"已按企业版范围检索。"}\n\n',
            'event: finish\ndata: {"messageId":"answer-message","messageStatus":"NORMAL"}\n\n',
            "event: done\ndata: [DONE]\n\n",
          ].join("");
    return route.fulfill({ contentType: "text/event-stream;charset=UTF-8", body });
  });

  await page.goto("/chat");
  await page.getByLabel("输入问题").fill("怎么配置");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("请选择更接近你问题的知识范围")).toBeVisible();
  await page.getByRole("button", { name: /产品 > 企业版/ }).click();

  await expect(page.getByText("已按企业版范围检索。")).toBeVisible();
  expect(selectedQuestion).toBe("怎么配置（知识范围：产品 > 企业版）");
  expect(selectedIntentCodes).toBe("product.enterprise");
});

test("opens, renames and deletes a saved conversation", async ({ page }, testInfo) => {
  const conversationId = "01999111-1111-7111-8111-111111111111";
  const records = [
    {
      conversationId,
      title: "产品接入讨论",
      lastTime: Date.parse("2026-09-03T10:30:00+08:00"),
    },
  ];
  const messages = [
    {
      id: "01999222-2222-7222-8222-222222222222",
      conversationId,
      role: "user",
      content: "如何接入产品知识库？",
      thinkingContent: null,
      thinkingDuration: null,
      vote: null,
      sources: null,
      recommendedQuestions: null,
      messageStatus: "NORMAL",
      createTime: Date.parse("2026-09-03T10:29:00+08:00"),
    },
    {
      id: "01999333-3333-7333-8333-333333333333",
      conversationId,
      role: "assistant",
      content: "先创建知识库，再导入并分块文档。",
      thinkingContent: "读取产品接入材料",
      thinkingDuration: 1,
      vote: 1,
      sources: [],
      recommendedQuestions: [],
      messageStatus: "NORMAL",
      createTime: Date.parse("2026-09-03T10:30:00+08:00"),
    },
  ];

  await page.addInitScript(() => window.localStorage.setItem("ragent.auth.token", "e2e-token"));
  await page.route("**/api/ragent/user/me", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(result({ userId: 1, username: "admin", role: "ADMIN" })),
    }),
  );
  await page.route("**/api/ragent/conversations**", (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === "GET" && path.endsWith(`/${conversationId}/messages`)) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(result(messages)),
      });
    }
    if (request.method() === "GET") {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(result(records)),
      });
    }
    if (request.method() === "PUT") {
      records[0].title = (request.postDataJSON() as { title: string }).title;
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(result(null)) });
    }
    if (request.method() === "DELETE") {
      records.splice(0, 1);
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(result(null)) });
    }
    return route.abort();
  });

  await page.goto(`/chat/${conversationId}`);
  await expect(page.getByText("先创建知识库，再导入并分块文档。")).toBeVisible();
  await expect(page.getByRole("button", { name: /^产品接入讨论/ })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("conversation-history.png"), fullPage: true });

  await page.getByRole("button", { name: "管理 产品接入讨论" }).click();
  await page.getByRole("menuitem", { name: "重命名" }).click();
  await page.getByLabel("会话标题").fill("配置方案讨论");
  await page.getByRole("button", { name: "保存标题" }).click();
  await expect(page.getByRole("button", { name: /^配置方案讨论/ })).toBeVisible();

  await page.getByRole("button", { name: "管理 配置方案讨论" }).click();
  await page.getByRole("menuitem", { name: "删除" }).click();
  await page.getByRole("button", { name: "确认删除" }).click();
  await expect(page).toHaveURL(/\/chat$/);
  await expect(page.getByText("首次提问后，会话会保存在这里。")).toBeVisible();
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

test("searches the admin console and opens results with keyboard or pointer", async ({
  page,
}, testInfo) => {
  const base = {
    id: 1,
    name: "产品知识库",
    collectionName: "product_docs",
    embeddingModel: "qwen3.7-text-embedding",
  };
  const document = {
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
  };

  await page.addInitScript(() => window.localStorage.setItem("ragent.auth.token", "e2e-token"));
  await page.route("**/api/ragent/user/me", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(result({ userId: 1, username: "admin", role: "ADMIN" })),
    }),
  );
  await page.route("**/api/ragent/knowledge-base**", (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path.endsWith("/knowledge-base/docs/search")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(result([document])),
      });
    }
    if (path.endsWith("/knowledge-base/1/docs")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(result({ records: [document], total: 1, current: 1, size: 20 })),
      });
    }
    if (path.endsWith("/knowledge-base/docs/11/chunks")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(result({ records: [], total: 0, current: 1, size: 20 })),
      });
    }
    if (path.endsWith("/knowledge-base/docs/11")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(result(document)),
      });
    }
    if (path.endsWith("/knowledge-base/1")) {
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(result(base)) });
    }
    return route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(result({ records: [base], total: 1, current: 1, size: 5 })),
    });
  });

  await page.goto("/admin/knowledge-bases");
  const search = page.getByRole("combobox", { name: "全局搜索" });
  await search.fill("产品");
  await expect(page.getByRole("option", { name: /产品知识库/ })).toBeVisible();
  await expect(page.getByRole("option", { name: /产品指南\.md/ })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("console-global-search.png") });

  await search.press("ArrowDown");
  await expect(page.getByRole("option", { name: /产品知识库/ })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await search.press("Enter");
  await expect(page).toHaveURL(/\/admin\/knowledge-bases\/1\/documents$/);

  const isMac = await page.evaluate(() => navigator.platform.toLowerCase().includes("mac"));
  await page.keyboard.press(isMac ? "Meta+k" : "Control+k");
  await expect(search).toBeFocused();
  await search.fill("指南");
  await page.getByRole("option", { name: /产品指南\.md/ }).click();
  await expect(page).toHaveURL(/\/admin\/documents\/11\/chunks$/);
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

test("manages the intent tree including disabled nodes", async ({ page }, testInfo) => {
  const roots: IntentNode[] = [
    {
      id: 1,
      intentCode: "product",
      name: "产品",
      level: 0,
      kind: 0,
      description: "产品相关问题",
      examples: [],
      collectionNames: [],
      enabled: true,
      fullPath: "产品",
      children: [
        {
          id: 2,
          intentCode: "product.guide",
          name: "使用指南",
          level: 1,
          parentCode: "product",
          kind: 0,
          description: "产品使用与配置",
          examples: [],
          collectionNames: [],
          enabled: true,
          fullPath: "产品 > 使用指南",
          children: [
            {
              id: 3,
              intentCode: "product.guide.install",
              name: "安装说明",
              level: 2,
              parentCode: "product.guide",
              kind: 0,
              description: "安装与部署问题",
              examples: ["如何安装？"],
              collectionName: "product_docs",
              collectionNames: ["product_docs"],
              enabled: false,
              fullPath: "产品 > 使用指南 > 安装说明",
              children: [],
            },
          ],
        },
      ],
    },
  ];
  const flatten = (nodes: IntentNode[]): IntentNode[] =>
    nodes.flatMap((node) => [node, ...flatten(node.children)]);

  await page.addInitScript(() => window.localStorage.setItem("ragent.auth.token", "e2e-token"));
  await page.route("**/api/ragent/user/me", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(result({ userId: 1, username: "admin", role: "ADMIN" })),
    }),
  );
  await page.route("**/api/ragent/knowledge-base?*", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        result({
          records: [
            {
              id: 1,
              name: "产品知识库",
              collectionName: "product_docs",
              embeddingModel: "qwen3.7-text-embedding",
            },
          ],
          total: 1,
          current: 1,
          size: 100,
        }),
      ),
    }),
  );
  await page.route("**/api/ragent/intent-tree**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === "GET") {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(result(roots)),
      });
    }
    if (request.method() === "POST" && path.endsWith("/intent-tree")) {
      const body = request.postDataJSON() as IntentNodeWrite;
      const parent = flatten(roots).find((node) => node.intentCode === body.parentCode);
      const created: IntentNode = {
        ...body,
        id: 4,
        fullPath: `${parent?.fullPath} > ${body.name}`,
        children: [],
      };
      parent?.children.push(created);
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(result("4")) });
    }
    if (request.method() === "PUT") {
      const id = Number(path.split("/").pop());
      const target = flatten(roots).find((node) => node.id === id);
      if (target) {
        Object.assign(target, request.postDataJSON());
        const parent = flatten(roots).find((node) => node.intentCode === target.parentCode);
        target.fullPath = parent ? `${parent.fullPath} > ${target.name}` : target.name;
      }
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(result(null)) });
    }
    if (request.method() === "POST" && path.includes("/batch/")) {
      const ids = (request.postDataJSON() as { ids: number[] }).ids;
      const enabled = path.endsWith("/enable");
      flatten(roots)
        .filter((node) => ids.includes(node.id))
        .forEach((node) => {
          node.enabled = enabled;
        });
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(result(null)) });
    }
    return route.fulfill({ contentType: "application/json", body: JSON.stringify(result(null)) });
  });

  await page.goto("/admin/intent-tree");
  await expect(page.getByRole("heading", { name: "意图树" })).toBeVisible();
  await page.getByRole("button", { name: "展开 使用指南" }).click();
  await page.getByRole("treeitem").filter({ hasText: "安装说明" }).click();
  await expect(page.getByText("已停用", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "启用节点" }).click();
  await expect(page.getByText("已停用")).toHaveCount(0);

  await page.getByRole("treeitem").filter({ hasText: "使用指南" }).click();
  await page.getByRole("button", { name: "新建子节点" }).click();
  await page.getByLabel("节点名称").fill("常见问题");
  await page.getByLabel("意图编码").fill("product.guide.faq");
  await page.getByText("产品知识库").click();
  await page.getByLabel("示例问题").fill("如何解决常见故障？");
  await page.getByRole("button", { name: "添加" }).click();
  await page.getByRole("button", { name: "保存节点" }).click();
  await expect(page.getByRole("treeitem").filter({ hasText: "常见问题" })).toBeVisible();

  await page.getByRole("treeitem").filter({ hasText: "常见问题" }).click();
  await page.getByRole("button", { name: "编辑 常见问题" }).click();
  await expect(page.getByLabel("意图编码")).toHaveValue("product.guide.faq");
  await page.getByLabel("节点名称").fill("故障排查");
  await page.getByRole("button", { name: "保存节点" }).click();
  await expect(page.getByRole("treeitem").filter({ hasText: "故障排查" })).toBeVisible();
  await page.getByRole("checkbox", { name: "选择 故障排查" }).check();
  await page.getByRole("button", { name: "停用", exact: true }).click();
  await expect(page.getByText("已停用", { exact: true })).toBeVisible();
  await expect(page.getByText("已停用 1 个节点")).toBeHidden({ timeout: 6_000 });
  await page.screenshot({ path: testInfo.outputPath("intent-tree.png"), fullPage: true });
});

test("manages query term mappings and keeps search in the URL", async ({ page }, testInfo) => {
  const records: QueryTermMapping[] = [
    {
      id: 1,
      sourceTerm: "AI 助理",
      targetTerm: "智能助手",
      matchType: 1,
      priority: 100,
      enabled: true,
      domain: "产品文档",
      remark: "统一产品名称",
    },
  ];

  await page.addInitScript(() => window.localStorage.setItem("ragent.auth.token", "e2e-token"));
  await page.route("**/api/ragent/user/me", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(result({ userId: 1, username: "admin", role: "ADMIN" })),
    }),
  );
  await page.route("**/api/ragent/mappings**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (request.method() === "GET") {
      const keyword = url.searchParams.get("keyword") || "";
      const filtered = records.filter(
        (item) => item.sourceTerm.includes(keyword) || item.targetTerm.includes(keyword),
      );
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          result({ records: filtered, total: filtered.length, current: 1, size: 20 }),
        ),
      });
    }
    if (request.method() === "POST") {
      records.push({ ...(request.postDataJSON() as QueryTermMappingWrite), id: 2 });
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(result("2")) });
    }
    if (request.method() === "PUT") {
      const id = Number(path.split("/").pop());
      const target = records.find((item) => item.id === id);
      if (target) Object.assign(target, request.postDataJSON());
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(result(null)) });
    }
    if (request.method() === "DELETE") {
      const id = Number(path.split("/").pop());
      records.splice(
        records.findIndex((item) => item.id === id),
        1,
      );
      return route.fulfill({ contentType: "application/json", body: JSON.stringify(result(null)) });
    }
    return route.abort();
  });

  await page.goto("/admin/mappings");
  await expect(page.getByRole("heading", { name: "查询词映射" })).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: "AI 助理" })).toBeVisible();

  await page.getByRole("button", { name: "新建映射" }).click();
  await page.getByLabel("原始词").fill("RAG 助手");
  await page.getByLabel("标准词").fill("Ragent AI");
  await page.getByLabel("所属领域").fill("技术支持");
  await page.getByLabel("备注").fill("客户常用称呼");
  await page.getByRole("button", { name: "保存映射" }).click();
  await expect(page.getByRole("row").filter({ hasText: "RAG 助手" })).toBeVisible();

  await page.getByRole("button", { name: "编辑 RAG 助手" }).click();
  await page.getByLabel("标准词").fill("Ragent 平台");
  await page.getByRole("button", { name: "保存映射" }).click();
  await expect(page.getByRole("row").filter({ hasText: "Ragent 平台" })).toBeVisible();

  await page.getByRole("button", { name: "停用 RAG 助手" }).click();
  await expect(page.getByRole("button", { name: "启用 RAG 助手" })).toBeVisible();

  await page.getByLabel("搜索查询词映射").fill("RAG");
  await page.getByLabel("搜索查询词映射").press("Enter");
  await expect(page).toHaveURL(/keyword=RAG/);
  await expect(page.getByRole("row").filter({ hasText: "RAG 助手" })).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: "AI 助理" })).toHaveCount(0);
  await expect(page.getByText("已停用“RAG 助手”")).toBeHidden({ timeout: 6_000 });
  await page.screenshot({ path: testInfo.outputPath("query-term-mappings.png"), fullPage: true });

  await page.getByRole("button", { name: "删除 RAG 助手" }).click();
  await page.getByRole("button", { name: "确认删除" }).click();
  await expect(page.getByText("RAG 助手")).toHaveCount(0);
});

test("filters trace runs and inspects node output", async ({ page }, testInfo) => {
  const traceId = "01994111-1111-7111-8111-111111111111";
  const taskId = "01994222-2222-7222-8222-222222222222";
  const run: RagTraceRun = {
    traceId,
    traceName: "rag-stream-chat",
    entryPoint: "app.rag.pipeline.StreamChatPipeline.execute",
    conversationId: "01994333-3333-7333-8333-333333333333",
    taskId,
    userId: 1,
    status: "SUCCESS",
    durationMs: 1_480,
    question: "当前检索流程在哪一步耗时最多？",
    startTime: Date.parse("2026-09-02T12:30:00.000Z"),
    endTime: Date.parse("2026-09-02T12:30:01.480Z"),
  };
  const failedRun: RagTraceRun = {
    ...run,
    traceId: "01994444-4444-7444-8444-444444444444",
    taskId: "01994555-5555-7555-8555-555555555555",
    status: "ERROR",
    durationMs: 690,
    question: "查询失败的知识内容",
    errorMessage: "模型服务暂时不可用",
  };
  const detail: RagTraceDetail = {
    run,
    nodes: [
      {
        nodeId: "01994666-6666-7666-8666-666666666666",
        nodeType: "REWRITE",
        nodeName: "query-rewrite",
        status: "SUCCESS",
        durationMs: 84,
        extraData: { rewrittenQuestion: "检索流程耗时分析" },
      },
      {
        nodeId: "01994777-7777-7777-8777-777777777777",
        nodeType: "RETRIEVE",
        nodeName: "retrieval-engine",
        status: "SUCCESS",
        durationMs: 620,
        extraData: {
          vectorCandidates: 12,
          finalChunkIds: ["chunk-01", "chunk-02"],
          channels: { vector: "SUCCESS", keyword: "DISABLED" },
        },
      },
      {
        nodeId: "01994888-8888-7888-8888-888888888888",
        nodeType: "RERANK",
        nodeName: "qwen3-rerank",
        status: "SUCCESS",
        durationMs: 410,
        extraData: { inputCount: 12, outputCount: 5 },
      },
    ],
  };

  await page.addInitScript(() => window.localStorage.setItem("ragent.auth.token", "e2e-token"));
  await page.route("**/api/ragent/user/me", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(result({ userId: 1, username: "admin", role: "ADMIN" })),
    }),
  );
  await page.route("**/api/ragent/rag/traces/runs**", (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path.endsWith(`/runs/${traceId}`)) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(result(detail)),
      });
    }
    const records = [run, failedRun].filter(
      (item) =>
        (!url.searchParams.get("status") || item.status === url.searchParams.get("status")) &&
        (!url.searchParams.get("taskId") || item.taskId === url.searchParams.get("taskId")),
    );
    return route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(result({ records, total: records.length, current: 1, size: 20 })),
    });
  });

  await page.goto("/admin/traces");
  await expect(page.getByRole("heading", { name: "RAG Trace" })).toBeVisible();
  await expect(page.getByText("当前检索流程在哪一步耗时最多？")).toBeVisible();
  await expect(page.getByText("查询失败的知识内容")).toBeVisible();

  await page.getByLabel("运行状态").selectOption("SUCCESS");
  await page.getByLabel("任务 ID").fill(taskId);
  await page.getByRole("button", { name: "查询" }).click();
  await expect(page).toHaveURL(/status=SUCCESS/);
  await expect(page).toHaveURL(new RegExp(`taskId=${taskId}`));
  await expect(page.getByText("查询失败的知识内容")).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("trace-list.png"), fullPage: true });

  await page.getByRole("link", { name: `查看 Trace ${traceId}` }).click();
  await expect(page.getByRole("heading", { name: "当前检索流程在哪一步耗时最多？" })).toBeVisible();
  await expect(page.getByText("retrieval-engine")).toBeVisible();
  await page.getByRole("button", { name: /retrieval-engine/ }).click();
  await expect(page.getByText(/vectorCandidates/)).toBeVisible();
  await expect(page.getByText(/finalChunkIds/)).toBeVisible();
  await expect(page.getByText("最慢")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("trace-detail.png"), fullPage: true });
});
