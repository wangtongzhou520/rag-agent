import { expect, test } from "@playwright/test";

test("renders the blue login foundation", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "登录 Ragent AI" })).toBeVisible();
  await expect(page.getByText("RAG 信号轨", { exact: true })).toBeVisible();
});
