import { test, expect } from "@playwright/test";

test("subscription sign-in, persistence, sign-out and return to API settings", async ({ page, request }, testInfo) => {
  test.skip(process.env.OPENATLAS_PROFILE_E2E !== "1", "Run against an isolated test library");
  const previous = await (await request.get("/api/settings")).json();
  let status: Record<string, unknown> = { status: "signed_out", runner_available: true };
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/api/subscription**", async route => {
    if (route.request().method() === "POST") status = { status: "waiting", runner_available: true, user_code: "ABCD-1234", verification_url: "https://auth.openai.com/codex/device" };
    if (route.request().method() === "DELETE") status = { status: "signed_out", runner_available: true };
    await route.fulfill({ json: status });
  });
  try {
    await page.goto("/");
    await page.getByLabel("Settings", { exact: true }).click();
    await page.getByLabel("Inference authentication").selectOption("chatgpt");
    await page.getByRole("button", { name: "Sign in with ChatGPT" }).click();
    await expect(page.getByText("ABCD-1234", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Open OpenAI sign-in" })).toHaveAttribute("href", "https://auth.openai.com/codex/device");
    await page.screenshot({ path: testInfo.outputPath("subscription-desktop.png") });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByText("ABCD-1234", { exact: true }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath("subscription-mobile.png") });
    expect(await page.getByRole("dialog").evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
    status = { status: "signed_in", runner_available: true, email: "fixture@example.com", plan: "pro" };
    await expect(page.getByText(/Signed in as fixture@example.com/)).toBeVisible();
    await page.getByRole("button", { name: "Save settings" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.reload();
    await page.getByLabel("Settings", { exact: true }).click();
    await expect(page.getByLabel("Inference authentication")).toHaveValue("chatgpt");
    await page.getByRole("button", { name: "Sign out of ChatGPT" }).click();
    await expect(page.getByRole("button", { name: "Sign in with ChatGPT" })).toBeVisible();
    await page.getByLabel("Inference authentication").selectOption("api_key");
    await expect(page.getByLabel("API provider profile")).toBeVisible();
    expect(errors).toEqual([]);
  } finally {
    await request.put("/api/settings", { data: previous });
  }
});
