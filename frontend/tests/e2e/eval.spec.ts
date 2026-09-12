import { expect, test } from "@playwright/test";

const result = <T>(data: T) => ({ code: "0", message: "ok", data });

test("runs a retrieval probe and renders evidence on desktop and mobile", async ({
  page,
}, testInfo) => {
  await page.addInitScript(() => window.localStorage.setItem("ragent.auth.token", "e2e-token"));
  await page.route("**/api/ragent/user/me", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(result({ userId: 1, username: "admin", role: "ADMIN" })),
    }),
  );
  await page.route("**/api/ragent/rag/eval**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/rag/eval/reports")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          result({
            records: [
              {
                reportId: "0199d13d-eval-7000-8000-000000000030",
                label: "阈值校准后",
                dataset: "evals/datasets/rag_quality.v2.jsonl",
                collections: ["m5_quality_baseline"],
                includeAnswers: true,
                summary: {
                  total: 30,
                  errors: 0,
                  docHitRate: 1,
                  mrr: 1,
                  contextPrecision: 0.9556,
                  answerKeywordRecall: 1,
                  answerCompleteRate: 1,
                  semanticScore: 0.96,
                  semanticPassRate: 1,
                  latencyP95Ms: 3144,
                  thresholdsPassed: true,
                },
                createdBy: 1,
                createTime: 1_789_099_200_000,
              },
            ],
            total: 1,
            current: 1,
            size: 8,
          }),
        ),
      });
    }
    if (path.includes("/rag/eval/reports/")) {
      return route.fulfill({
        contentType: "application/json",
        body: JSON.stringify(
          result({
            reportId: "0199d13d-eval-7000-8000-000000000030",
            label: "阈值校准后",
            dataset: "evals/datasets/rag_quality.v2.jsonl",
            collections: ["m5_quality_baseline"],
            includeAnswers: true,
            summary: {
              total: 30,
              errors: 0,
              docHitRate: 1,
              mrr: 1,
              contextPrecision: 0.9556,
              answerKeywordRecall: 1,
              answerCompleteRate: 1,
              semanticScore: 0.96,
              semanticPassRate: 1,
              latencyP95Ms: 3144,
              thresholdsPassed: true,
            },
            thresholds: { minHitRate: 0.8 },
            cases: [
              {
                id: "leave-01",
                question: "年假有几天？",
                passed: true,
                semantic_score: 0.96,
                semantic_verdict: "PASS",
              },
            ],
            createdBy: 1,
            createTime: 1_789_099_200_000,
          }),
        ),
      });
    }
    return route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(
        result({
          retrievedDocIds: ["incident_response"],
          retrievedChunkIds: ["0199d13d-eval-7000-8000-000000000001"],
          retrievedContexts: [
            "P0 故障需要立即通知技术负责人和业务负责人，并在 15 分钟内建立应急沟通群。",
          ],
          retrievedScores: [0.9821],
          retrievedContextDocIds: ["incident_response"],
          retrievalCollections: [],
          answer: "P0 故障应在 15 分钟内建立应急沟通群。[1](#cite-1)",
          answerLatencyMs: 1260,
          mcpContext: "",
          hasMcpSuccess: false,
          needsClarification: false,
          hasMcpFailure: false,
          hasKb: true,
          subIntents: ["P0 故障发生后多久要建立应急沟通群？"],
          intentLeafIds: ["701"],
          latencyMs: 842,
        }),
      ),
    });
  });

  await page.setViewportSize({ width: 1440, height: 960 });
  await page.goto("/admin/eval");
  await expect(page.getByRole("heading", { name: "检索质量实验台" })).toBeVisible();
  await page.getByRole("button", { name: /P0 故障发生后多久要建立应急沟通群/ }).click();
  await page.getByRole("checkbox", { name: /同时生成答案/ }).check();
  await page.getByRole("button", { name: "运行单题评测" }).click();
  await expect(page.getByText("incident_response", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("842 ms", { exact: true })).toBeVisible();
  await expect(page.getByText("1.26 s", { exact: true })).toBeVisible();
  await expect(page.getByText(/P0 故障应在 15 分钟内/)).toBeVisible();
  await expect(page.getByText("知识库", { exact: true }).last()).toBeVisible();
  await expect(page.getByRole("heading", { name: "批次评测记录" })).toBeVisible();
  await page.getByRole("button", { name: /阈值校准后/ }).click();
  await expect(page.getByText("96.0%", { exact: true })).toBeVisible();
  await expect(page.getByText("本批次没有失败或语义风险用例。")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("eval-desktop.png"), fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: "检索质量实验台" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await page.screenshot({ path: testInfo.outputPath("eval-mobile.png"), fullPage: true });
});
