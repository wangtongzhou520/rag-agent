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
