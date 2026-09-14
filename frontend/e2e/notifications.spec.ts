import { test, expect } from "@playwright/test";
test("failures use a quiet inbox and new failures toast with direct inspection", async ({
  page,
}) => {
  const old = {
    id: "old-failure",
    notebook_id: "n",
    status: "failed",
    progress: "Failed",
    error: "The Notebook build needs repair.",
    created_at: "2026-09-13T00:00:00Z",
    request: { prompt: "How memory works", provider: "codex" },
  };
  let status = "running";
  await page.route("**/api/jobs", (route) =>
    route.fulfill({
      json: [
        old,
        {
          ...old,
          id: "new-failure",
          status,
          created_at: "2026-09-14T00:00:00Z",
        },
      ],
    }),
  );
  await page.route("**/api/jobs/new-failure/debug", (route) =>
    route.fulfill({
      json: {
        job: { ...old, id: "new-failure" },
        containers: [],
        updated_at: new Date().toISOString(),
      },
    }),
  );
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Notifications, 1 unread" }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.locator(".error")).toHaveCount(0);
  status = "failed";
  await expect(page.getByRole("alert")).toBeVisible();
  await page.screenshot({ path: "test-results/notification-toast.png" });
  await page
    .getByRole("alert")
    .getByRole("button", { name: /Inspect job/ })
    .click();
  await expect(page.getByText("Generation inspector")).toBeVisible();
  await page.goto("/");
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: /Notifications/ }).click();
  const inbox = page.getByRole("region", {
    name: "Notifications",
    exact: true,
  });
  await expect(inbox).toBeVisible();
  await page.screenshot({ path: "test-results/notification-mobile.png" });
  await inbox.getByRole("button", { name: "Mark all as read" }).click();
  await page.keyboard.press("Escape");
  await expect(inbox).toHaveCount(0);
  await page.reload();
  await expect(
    page.getByRole("button", { name: "Notifications", exact: true }),
  ).toBeVisible();
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
  }
});
