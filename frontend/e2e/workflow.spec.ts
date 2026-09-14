import { test, expect } from "@playwright/test";
test("prompt → persisted job → library → isolated interactive reader → revision", async ({
  page,
  request,
}) => {
  const previous = await (await request.get("/api/settings")).json();
  try {
    await request.put("/api/settings", {
      data: { provider: "demo", concurrency: 2, model: "gpt-6-astra" },
    });
    await page.goto("/");
    await page
      .getByLabel("What do you want to learn?", { exact: true })
      .fill("E2E: teach me caching");
    await page
      .locator("summary")
      .filter({ hasText: "Generation skills" })
      .click();
    await page.getByRole("checkbox", { name: /visual-explainer/ }).check();
    await page.getByRole("slider", { name: "Time to explore" }).focus();
    await page.getByRole("slider", { name: "Time to explore" }).press("End");
    await expect(
      page.getByRole("slider", { name: "Time to explore" }),
    ).toHaveValue("50");
    const created = page.waitForResponse(
      (r) => r.url().endsWith("/api/jobs") && r.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Generate Notebook" }).click();
    const job = await (await created).json();
    expect(job.status).toBe("queued");
    expect(job.request.reading_minutes).toBe(50);
    await expect(
      page.locator(`a[href="/notebooks/${job.notebook_id}"]`),
    ).toBeVisible({ timeout: 30000 });
    await page.locator(`a[href="/notebooks/${job.notebook_id}"]`).click();
    await expect(page.locator("iframe")).toHaveAttribute(
      "sandbox",
      "allow-scripts",
    );
    const frame = page.frameLocator("iframe");
    await expect(
      frame.getByText("Demo content.", { exact: true }),
    ).toBeVisible();
    await frame.getByRole("button", { name: "Enable caching" }).click();
    await expect(frame.locator("#cost")).toHaveText("4 calculations");
    await frame
      .getByRole("button", { name: "Earlier key/value projections" })
      .click();
    await expect(frame.locator("#feedback")).toContainText("Exactly.");
    const sandbox = page.frames().find((f) => f.url().includes("/artifacts/"))!;
    expect(
      await sandbox.evaluate(() => {
        try {
          void parent.document.body;
          return false;
        } catch {
          return true;
        }
      }),
    ).toBe(true);
    expect(
      await sandbox.evaluate(() => {
        try {
          localStorage.setItem("test", "x");
          return false;
        } catch {
          return true;
        }
      }),
    ).toBe(true);
    await page.reload();
    await expect(frame.locator("#cost")).toHaveText("10 calculations");
    await page.getByRole("button", { name: "Revise Notebook" }).click();
    await expect(
      page.getByRole("slider", { name: "Time to explore" }),
    ).toHaveValue("50");
    await page
      .locator("summary")
      .filter({ hasText: "Generation skills" })
      .click();
    await expect(
      page.getByRole("checkbox", { name: /visual-explainer/ }),
    ).toBeChecked();
    await page
      .getByLabel("What do you want to learn?", { exact: true })
      .fill("Add another visual example");
    await page.getByRole("button", { name: "Create revision" }).click();
    await expect(
      page.getByLabel("Notebook version").locator("option"),
    ).toHaveCount(2, { timeout: 30000 });
  } finally {
    await request.put("/api/settings", { data: previous });
  }
});
test("mobile composer fits and works", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "What do you want to learn?" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page
    .getByLabel("What do you want to learn?", { exact: true })
    .fill("How do trees grow?");
  await expect(
    page.getByRole("button", { name: "Generate Notebook" }),
  ).toBeEnabled();
});

test("Settings displays Astra and write-only credential controls on mobile", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.getByLabel("Codex model")).toHaveValue("gpt-6-astra");
  await expect(page.getByLabel("OpenAI API key")).toHaveAttribute(
    "type",
    "password",
  );
  await expect(page.getByLabel("OpenAI API key")).toHaveValue("");
  await expect(
    page.getByRole("button", { name: "Save settings" }),
  ).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBe(true);
});

test("debug toggle persists and opens a generation inspector on mobile", async ({
  page,
  request,
}) => {
  const jobs = await (await request.get("/api/jobs")).json();
  const demo = jobs.find(
    (j: { request: { provider: string } }) => j.request.provider === "demo",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page
    .getByRole("checkbox", { name: "Debug mode · inspect generation activity" })
    .check();
  await page.getByRole("button", { name: "Close settings" }).click();
  await page.reload();
  await page.getByLabel("Inspect a generation").selectOption(demo.id);
  await expect(
    page.getByRole("dialog", { name: "Generation inspector" }),
  ).toBeVisible();
  await expect(
    page.getByText(/Demo generation uses no Codex container/),
  ).toBeVisible();
  await page.getByRole("button", { name: "Pause live updates" }).click();
  await expect(
    page.getByRole("button", { name: "Resume live updates" }),
  ).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBe(true);
  await page.getByRole("button", { name: "Close inspector" }).click();
  await page.getByRole("button", { name: "Turn off debug mode" }).click();
  await expect(page.getByLabel("Inspect a generation")).toHaveCount(0);
});

test("Jobs dropdown filters failures and opens debug without enabling Settings", async ({
  page,
}) => {
  const failed = {
    id: "failed-test",
    status: "failed",
    progress: "Generation failed",
    error: "Interaction check 9 failed",
    created_at: "2026-09-14",
    request: { prompt: "Test failed Notebook", provider: "codex" },
  };
  await page.route("**/api/jobs", (route) => route.fulfill({ json: [failed] }));
  await page.route("**/api/jobs/failed-test/debug", (route) =>
    route.fulfill({ json: { job: failed, containers: [], updated_at: null } }),
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.locator(".jobs-dropdown > summary").click();
  await page.getByLabel("Filter jobs").selectOption("failed");
  await expect(
    page.getByRole("region", { name: "Generation jobs" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Debug failed job" }).first().click();
  await expect(
    page.getByRole("dialog", { name: "Generation inspector" }),
  ).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBe(true);
});
