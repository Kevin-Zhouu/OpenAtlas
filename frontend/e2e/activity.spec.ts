import { test, expect } from "@playwright/test";

test("activity merges live updates, follows the bottom, and respects reading older entries", async ({
  page,
}) => {
  const job = {
    id: "activity-test",
    status: "running",
    progress: "Testing the Notebook in Chromium",
    request: {
      prompt: "Explain memory paging",
      provider: "codex",
      model: "gpt-6-astra",
    },
    created_at: "2026-09-14T00:00:00Z",
  };
  const events = Array.from({ length: 18 }, (_, i) => ({
    type: "item.completed",
    item: {
      id: "message-" + i,
      type: "agent_message",
      text: `Step ${i + 1}: I am checking how this explanation connects to the interactive diagram. The learner should be able to predict the result before trying the control.`,
    },
  }));
  events.push({
    type: "item.completed",
    item: {
      id: "files",
      type: "file_change",
      text: "",
      changes: [
        { path: "src/lesson.tsx", kind: "update" },
        { path: "src/diagram.tsx", kind: "add" },
      ],
    },
  });
  events.push({
    type: "item.completed",
    item: {
      id: "plan",
      type: "todo_list",
      text: "",
      items: [
        { text: "Build the explanation and diagram", completed: true },
        { text: "Connect the interactive controls", completed: true },
        { text: "Check desktop and phone layouts", completed: false },
      ],
    },
  });
  events.push({
    type: "item.started",
    item: { id: "build", type: "command_execution", text: "" },
  });
  let phase = 0;
  await page.route("**/api/jobs", (r) => r.fulfill({ json: [job] }));
  await page.route("**/api/jobs/activity-test/debug", (r) =>
    r.fulfill({
      json: {
        job,
        updated_at: new Date().toISOString(),
        containers: [
          {
            id: "container-123",
            role: "agent",
            status: "running",
            image: "openatlas-generation:local",
            started_at: "2026-09-14T00:00:00Z",
            cpu_limit: 2,
            memory_limit: 2147483648,
            read_only: true,
            processes: [["123", "codex"]],
            container_log: "",
            agent_log: [
              ...events,
              {
                type: phase ? "item.completed" : "item.started",
                item: {
                  id: "build",
                  type: "command_execution",
                  command: "npm run build && npm test",
                  status: phase ? "completed" : "in_progress",
                  aggregated_output: phase ? "All browser checks passed." : "",
                },
              },
              ...(phase
                ? [
                    {
                      type: "item.completed",
                      item: {
                        id: "new-message",
                        type: "agent_message",
                        text: "The Notebook is ready for publication.",
                      },
                    },
                  ]
                : []),
            ]
              .map((e) => JSON.stringify(e))
              .join("\n"),
          },
        ],
      },
    }),
  );
  await page.goto("/");
  await page.locator(".jobs-dropdown>summary").click();
  await page.getByRole("button", { name: "Inspect job", exact: true }).click();
  const feed = page.getByRole("log", { name: "Agent activity" });
  await expect(feed).toBeVisible();
  await expect(
    feed.locator('[data-activity-id="container-123:build"]'),
  ).toHaveCount(1);
  await expect(
    feed.getByRole("img", { name: "Running", exact: true }),
  ).toBeVisible();
  expect(
    await feed
      .getByRole("img", { name: "Running", exact: true })
      .evaluate((el) => getComputedStyle(el).animationName),
  ).toBe("activity-spin");
  await expect
    .poll(() =>
      feed.evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight),
    )
    .toBeLessThan(3);
  await page.screenshot({ path: "test-results/activity-live.png" });
  await feed.evaluate((el) => {
    el.scrollTop = 0;
    el.dispatchEvent(new Event("scroll"));
  });
  await expect(
    page.getByRole("button", { name: "Jump to latest" }),
  ).toBeVisible();
  phase = 1;
  await expect(
    feed.getByText("The Notebook is ready for publication."),
  ).toBeAttached({ timeout: 6000 });
  await expect.poll(() => feed.evaluate((el) => el.scrollTop)).toBeLessThan(3);
  await expect(
    feed.locator('[data-activity-id="container-123:build"]'),
  ).toHaveCount(1);
  await expect(
    feed.getByRole("img", { name: "Running", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Jump to latest" }).click();
  await expect
    .poll(() =>
      feed.evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight),
    )
    .toBeLessThan(3);
  await page.getByRole("button", { name: "Pause live updates" }).click();
  await expect(feed.getByText("Live updates paused")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBe(true);
  await expect(page.getByRole("dialog").getByRole("textbox")).toHaveCount(0);
  await page.screenshot({ path: "test-results/activity-mobile.png" });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole("button", { name: "Resume live updates" }).click();
  await expect(
    page.getByRole("img", { name: "Generation running" }),
  ).toBeVisible();
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(
    await page
      .getByRole("img", { name: "Generation running" })
      .evaluate((el) => getComputedStyle(el).animationName),
  ).toBe("none");
  await page.screenshot({ path: "test-results/activity-desktop.png" });
});
