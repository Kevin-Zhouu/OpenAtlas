import { test, expect } from "@playwright/test";

test("save, switch, reopen and delete inference profiles", async ({ page, request }, testInfo) => {
  test.skip(process.env.OPENATLAS_PROFILE_E2E !== "1", "Run against an isolated test library");
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const previous = await (await request.get("/api/settings")).json();
  const initial = await (await request.get("/api/inference-profiles")).json();
  const created: string[] = [];
  try {
    await page.goto("/");
    const open = async () => {
      await page.getByLabel("Settings", { exact: true }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await expect(page.getByRole("button", { name: "Save settings" })).toBeEnabled();
    };
    const save = async () => {
      await page.getByRole("button", { name: "Save settings" }).click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
    };
    await open();
    await page.getByLabel("API provider profile").selectOption("new");
    await page.getByLabel("Provider name").fill("Provider Alpha");
    await page.getByLabel("API base URL").fill("https://alpha.example/gateway/v2");
    await page.getByLabel("API key", { exact: true }).fill("alpha-test-token");
    await page.getByLabel("Codex model", { exact: true }).fill("vendor/codex:latest");
    await page.getByRole("button", { name: "Planner", exact: true }).click();
    await page.getByLabel("Planner model", { exact: true }).fill("vendor/planner:v2");
    await save();
    created.push((await (await request.get("/api/inference-profiles")).json()).active_id);
    await open();
    await expect(page.getByLabel("API base URL")).toHaveValue("https://alpha.example/gateway/v2");
    await expect(page.getByLabel("API key", { exact: true })).toHaveValue("");
    await page.getByLabel("API provider profile").selectOption("new");
    await page.getByLabel("Provider name").fill("Provider Beta");
    await page.getByLabel("API base URL").fill("https://beta.example/v1/");
    await page.getByLabel("API key", { exact: true }).fill("beta-test-token");
    await save();
    created.push((await (await request.get("/api/inference-profiles")).json()).active_id);
    await page.reload();
    await open();
    await expect(page.getByLabel("API provider profile")).toHaveValue(created[1]);
    await expect(page.getByLabel("API base URL")).toHaveValue("https://beta.example/v1");
    await page.getByLabel("API provider profile").selectOption(created[0]);
    await expect(page.getByLabel("API base URL")).toHaveValue("https://alpha.example/gateway/v2");
    await expect(page.getByLabel("API key", { exact: true })).toHaveValue("");
    await save();
    await page.reload();
    await open();
    await expect(page.getByLabel("API provider profile")).toHaveValue(created[0]);
    await page.getByLabel("API provider profile").scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath("profiles-desktop.png") });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByLabel("API provider profile").scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath("profiles-mobile.png") });
    expect(await page.getByRole("dialog").evaluate((node) => node.scrollWidth <= node.clientWidth)).toBe(true);
    await page.getByRole("button", { name: "Delete provider profile" }).click();
    await expect(page.getByLabel("API provider profile")).toHaveValue("host");
    await expect(page.getByRole("option", { name: "Provider Alpha" })).toHaveCount(0);
    await expect(page.getByRole("option", { name: "Provider Beta" })).toHaveCount(1);
    const response = await request.get("/api/inference-profiles");
    expect(await response.text()).not.toContain("beta-test-token");
    expect(errors).toEqual([]);
  } finally {
    for (const id of created) await request.delete(`/api/inference-profiles/${id}`);
    await request.put("/api/inference-profile-selection", { data: { profile_id: initial.active_id } });
    await request.put("/api/settings", { data: previous });
  }
});
