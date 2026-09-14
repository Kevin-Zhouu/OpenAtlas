import React from "react";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { App } from "./App";
const fetcher = vi.fn();
beforeEach(() => {
  vi.stubGlobal("fetch", fetcher);
  fetcher.mockImplementation(async (url: string) => ({
    ok: true,
    json: async () =>
      url.endsWith("/settings")
        ? { provider: "demo", concurrency: 2, model: "gpt-6-astra" }
        : url.endsWith("/credentials")
          ? { configured: false, source: "none" }
          : url.endsWith("/models")
            ? [{ id: "gpt-6-astra", name: "GPT-6 Astra", default: true }]
            : url.endsWith("/skills")
              ? [
                  {
                    id: "builtin:visual-explainer",
                    name: "visual-explainer",
                    description: "Visual teaching",
                    valid: true,
                    required: false,
                  },
                ]
              : [],
  }));
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  fetcher.mockReset();
});
it("keeps skills secondary and submits explicit selection and instructions", async () => {
  render(<App />);
  expect(
    screen.getByRole("button", { name: /Generate Notebook/ }),
  ).toBeDisabled();
  fireEvent.change(screen.getByLabelText("What do you want to learn?"), {
    target: { value: "Teach me caching" },
  });
  fireEvent.click(
    await screen.findByRole("checkbox", { name: /visual-explainer/ }),
  );
  fireEvent.change(
    screen.getByLabelText(/Additional generation instructions/),
    { target: { value: "Add a diagram" } },
  );
  fireEvent.change(screen.getByLabelText("Time to explore"), {
    target: { value: "50" },
  });
  fireEvent.click(screen.getByRole("button", { name: /Generate Notebook/ }));
  await waitFor(() =>
    expect(fetcher).toHaveBeenCalledWith(
      "/api/jobs",
      expect.objectContaining({
        body: JSON.stringify({
          prompt: "Teach me caching",
          skills: ["builtin:visual-explainer"],
          skills_enabled: true,
          instructions: "Add a diagram",
          provider: "demo",
          reading_minutes: 50,
        }),
      }),
    ),
  );
});
it("shows empty library and explicit demo mode", async () => {
  render(<App />);
  expect(
    await screen.findByText("A little curiosity goes a long way."),
  ).toBeInTheDocument();
  expect(screen.getByText(/Demo mode/)).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText("Settings"));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  await screen.findByText("No API key configured");
  expect(screen.getByLabelText("Concurrent generations")).toHaveValue(2);
});
it("displays persisted failure details in generation history", async () => {
  fetcher.mockImplementation(async (url: string) => ({
    ok: true,
    json: async () =>
      url.endsWith("/jobs")
        ? [
            {
              id: "1",
              created_at: "2026-09-14T00:00:00Z",
              status: "failed",
              request: { prompt: "Teach something", provider: "codex" },
              error: "Provider unavailable",
            },
          ]
        : url.endsWith("/settings")
          ? { provider: "demo", concurrency: 2, model: "test" }
          : [],
  }));
  render(<App />);
  fireEvent.click(screen.getByText("Generation history"));
  await screen.findAllByText("Provider unavailable");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Notifications/ }));
  expect(
    screen.getByRole("region", { name: "Notifications" }),
  ).toHaveTextContent("Provider unavailable");
  expect(
    within(document.querySelector(".history") as HTMLElement).getByText(
      "Provider unavailable",
    ),
  ).toBeInTheDocument();
});
