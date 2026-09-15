import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ChatGPTSubscription } from "./ChatGPTSubscription";
const fetcher = vi.fn();
let state: Record<string, unknown>;
beforeEach(() => {
  state = { status: "signed_out", runner_available: true };
  vi.stubGlobal("fetch", fetcher);
  fetcher.mockImplementation(async (_url: string, options?: RequestInit) => {
    if (options?.method === "POST") state = { status: "waiting", runner_available: true, user_code: "ABCD-1234", verification_url: "https://auth.openai.com/codex/device" };
    if (options?.method === "DELETE") state = { status: "signed_out", runner_available: true };
    return { ok: true, json: async () => state };
  });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); fetcher.mockReset(); });
it("starts on click, shows the official link, and cancels", async () => {
  render(<ChatGPTSubscription />);
  const button = await screen.findByRole("button", { name: "Sign in with ChatGPT" });
  expect(fetcher.mock.calls.some(([, o]) => o?.method === "POST")).toBe(false);
  fireEvent.click(button);
  expect(await screen.findByText("ABCD-1234")).toBeVisible();
  expect(screen.getByRole("link", { name: /Open OpenAI sign-in/ })).toHaveAttribute("href", "https://auth.openai.com/codex/device");
  fireEvent.click(screen.getByRole("button", { name: "Cancel sign-in" }));
  await screen.findByRole("button", { name: "Sign in with ChatGPT" });
  expect(screen.queryByText("ABCD-1234")).not.toBeInTheDocument();
});
it("shows the saved account and supports signout", async () => {
  state = { status: "signed_in", runner_available: true, email: "test@example.com", plan: "pro" };
  render(<ChatGPTSubscription />);
  await screen.findByText("Signed in as test@example.com · pro");
  fireEvent.click(screen.getByRole("button", { name: "Sign out of ChatGPT" }));
  await screen.findByRole("button", { name: "Sign in with ChatGPT" });
});
it("disables sign-in without a runner", async () => {
  state = { status: "signed_out", runner_available: false };
  render(<ChatGPTSubscription />);
  expect(await screen.findByRole("button", { name: "Sign in with ChatGPT" })).toBeDisabled();
});
it("shows expired sign-in and rejects unexpected links", async () => {
  state = { status: "waiting", runner_available: true, user_code: "ABCD-1234", verification_url: "https://evil.example" };
  const view = render(<ChatGPTSubscription />);
  await screen.findByRole("button", { name: "Cancel sign-in" });
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
  view.unmount();
  state = { status: "error", runner_available: true, message: "Sign-in expired. Start sign-in again." };
  render(<ChatGPTSubscription />);
  await screen.findByText(/Sign-in expired/);
  expect(screen.getByRole("button", { name: "Sign in with ChatGPT" })).toBeEnabled();
});
