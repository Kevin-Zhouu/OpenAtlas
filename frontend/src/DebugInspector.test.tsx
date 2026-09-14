import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { DebugInspector } from "./DebugInspector";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("shows agent actions and renders untrusted output as text", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        job: {
          status: "running",
          progress: "Building",
          request: { provider: "codex", model: "gpt-6-astra" },
        },
        updated_at: new Date().toISOString(),
        containers: [
          {
            id: "abc",
            role: "agent",
            status: "running",
            processes: [["1", "codex"]],
            agent_log: JSON.stringify({
              type: "item.started",
              item: {
                type: "command_execution",
                command: "<script>alert(1)</script>",
                status: "in_progress",
              },
            }),
          },
        ],
      }),
    }),
  );
  render(<DebugInspector jobId="test" onClose={() => {}} />);
  expect(
    (await screen.findAllByText("<script>alert(1)</script>"))[0],
  ).toBeInTheDocument();
  expect(document.querySelector("script")).toBeNull();
  expect(screen.getByText("Codex agent")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Pause live updates" }),
  ).toBeInTheDocument();
});
it("explains demo jobs have no container", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        job: {
          status: "succeeded",
          progress: "Done",
          request: { provider: "demo" },
        },
        containers: [],
        updated_at: null,
      }),
    }),
  );
  render(<DebugInspector jobId="demo" onClose={() => {}} />);
  expect(
    await screen.findByText(/Demo generation uses no Codex container/),
  ).toBeInTheDocument();
  expect(screen.getByText("Retained snapshot")).toBeInTheDocument();
});
it("shows connection failures", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
  render(<DebugInspector jobId="test" onClose={() => {}} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Could not load diagnostics",
  );
});
