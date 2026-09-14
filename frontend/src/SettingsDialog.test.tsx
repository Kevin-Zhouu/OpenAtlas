import {
  render,
  screen,
  fireEvent,
  waitFor,
  cleanup,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { SettingsDialog } from "./SettingsDialog";
const fetcher = vi.fn();
const settings = { provider: "demo", model: "gpt-6-astra", concurrency: 2 };
beforeEach(() => {
  vi.stubGlobal("fetch", fetcher);
  fetcher.mockImplementation(async (url: string, options?: RequestInit) => ({
    ok: true,
    json: async () =>
      url.endsWith("/phone") ? { enabled: false, url: "", pairing_url: "" } : url.endsWith("/models")
        ? [
            { id: "gpt-6-astra", name: "GPT-6 Astra", default: true },
            { id: "gpt-5.6-sol", name: "GPT-5.6 Sol" },
          ]
        : url.endsWith("/credentials")
          ? {
              configured: options?.method !== "DELETE",
              source: options?.method === "DELETE" ? "none" : "saved",
            }
          : JSON.parse(options?.body as string),
  }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  fetcher.mockReset();
});
it("keeps stored keys hidden and saves credentials separately from selected model", async () => {
  const saved = vi.fn();
  render(
    <SettingsDialog settings={settings} onSaved={saved} onClose={vi.fn()} />,
  );
  await screen.findByText("API key saved locally");
  expect(screen.getByLabelText("OpenAI API key")).toHaveAttribute(
    "type",
    "password",
  );
  expect(screen.getByLabelText("OpenAI API key")).toHaveValue("");
  expect(screen.getByLabelText("Codex model")).toHaveValue("gpt-6-astra");
  fireEvent.change(screen.getByLabelText("Codex model"), {
    target: { value: "gpt-5.6-sol" },
  });
  fireEvent.change(screen.getByLabelText("OpenAI API key"), {
    target: { value: "sk-test-only-credential" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
  await waitFor(() =>
    expect(saved).toHaveBeenCalledWith({ ...settings, model: "gpt-5.6-sol" }),
  );
  expect(fetcher).toHaveBeenCalledWith(
    "/api/credentials",
    expect.objectContaining({
      method: "PUT",
      body: JSON.stringify({ api_key: "sk-test-only-credential" }),
    }),
  );
  expect(fetcher).toHaveBeenCalledWith(
    "/api/settings",
    expect.objectContaining({
      body: JSON.stringify({ ...settings, model: "gpt-5.6-sol" }),
    }),
  );
});
it("removes a saved key without revealing it", async () => {
  render(
    <SettingsDialog settings={settings} onSaved={vi.fn()} onClose={vi.fn()} />,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "Remove saved key" }),
  );
  expect(await screen.findByText("No API key configured")).toBeInTheDocument();
});
it("keeps the dialog open and shows credential errors", async () => {
  const saved = vi.fn();
  render(
    <SettingsDialog settings={settings} onSaved={saved} onClose={vi.fn()} />,
  );
  await screen.findByText("API key saved locally");
  fetcher.mockResolvedValueOnce({
    ok: false,
    json: async () => ({
      detail: "Enter a valid OpenAI API key beginning with sk-.",
    }),
  });
  fireEvent.change(screen.getByLabelText("OpenAI API key"), {
    target: { value: "invalid" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Enter a valid OpenAI API key",
  );
  expect(saved).not.toHaveBeenCalled();
});
