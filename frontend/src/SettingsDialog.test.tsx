import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { SettingsDialog } from "./SettingsDialog";
const fetcher = vi.fn();
const settings = { provider: "demo", model: "gpt-6-astra", concurrency: 2 };
const original = { id: "openai", name: "OpenAI", base_url: "https://api.openai.com/v1", configured: true, source: "saved" };
const gateway = { id: "gateway", name: "My gateway", base_url: "https://gateway.example/api/v1", configured: true, source: "saved" };
const host = { id: "host", name: "Host configuration", base_url: "https://api.openai.com/v1", configured: false, source: "none" };
let profiles: { active_id: string; profiles: typeof original[] };
beforeEach(() => {
  profiles = { active_id: "openai", profiles: [{ ...original }, { ...gateway }, { ...host }] };
  vi.stubGlobal("fetch", fetcher);
  fetcher.mockImplementation(async (url: string, options?: RequestInit) => {
    const body = options?.body ? JSON.parse(options.body as string) : undefined;
    let result: unknown;
    if (url.endsWith("/phone")) result = { enabled: false, url: "", pairing_url: "" };
    else if (url.endsWith("/models")) result = [{ id: "gpt-6-astra", name: "GPT-6 Astra", default: true }];
    else if (url.endsWith("/inference-profile-selection")) {
      profiles.active_id = body.profile_id;
      result = structuredClone(profiles);
    } else if (url.includes("/inference-profiles")) {
      const id = url.split("/")[3];
      if (options?.method === "DELETE") {
        profiles.profiles = profiles.profiles.filter((p) => p.id !== id);
        if (profiles.active_id === id) profiles.active_id = "host";
      } else if (body) {
        const saved = { id: id || "new-profile", name: body.name, base_url: body.base_url, configured: true, source: "saved" };
        if (id) profiles.profiles = profiles.profiles.map((p) => p.id === id ? saved : p);
        else profiles.profiles.push(saved);
        if (body.activate) profiles.active_id = saved.id;
      }
      result = structuredClone(profiles);
    } else result = body;
    return { ok: true, json: async () => result };
  });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); fetcher.mockReset(); });

it("keeps stored keys hidden and saves credentials separately from model settings", async () => {
  const saved = vi.fn();
  render(<SettingsDialog settings={settings} onSaved={saved} onClose={vi.fn()} />);
  await screen.findByText("API key saved locally");
  expect(screen.getByLabelText("API key")).toHaveAttribute("type", "password");
  expect(screen.getByLabelText("API key")).toHaveValue("");
  fireEvent.change(screen.getByLabelText("Codex model"), { target: { value: "vendor/coding:latest" } });
  fireEvent.change(screen.getByLabelText("API key"), { target: { value: "third-party-key" } });
  fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
  await waitFor(() => expect(saved).toHaveBeenCalledWith({ ...settings, model: "vendor/coding:latest" }));
  expect(fetcher).toHaveBeenCalledWith("/api/inference-profiles/openai", expect.objectContaining({
    method: "PUT", body: JSON.stringify({ name: "OpenAI", base_url: original.base_url, api_key: "third-party-key", activate: true }),
  }));
  expect(fetcher).toHaveBeenCalledWith("/api/settings", expect.objectContaining({
    body: JSON.stringify({ ...settings, model: "vendor/coding:latest" }),
  }));
});

it("creates a named provider and retains the earlier profiles", async () => {
  const saved = vi.fn();
  render(<SettingsDialog settings={settings} onSaved={saved} onClose={vi.fn()} />);
  await screen.findByText("API key saved locally");
  fireEvent.change(screen.getByLabelText("API provider profile"), { target: { value: "new" } });
  fireEvent.change(screen.getByLabelText("Provider name"), { target: { value: "Third party" } });
  fireEvent.change(screen.getByLabelText("API base URL"), { target: { value: "https://third.example/v1" } });
  fireEvent.change(screen.getByLabelText("API key"), { target: { value: "third-key" } });
  fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
  await waitFor(() => expect(saved).toHaveBeenCalled());
  expect(profiles.profiles).toHaveLength(4);
  expect(profiles.active_id).toBe("new-profile");
  expect(screen.getByLabelText("API key")).toHaveValue("");
  expect(screen.getByRole("option", { name: "OpenAI" })).toBeInTheDocument();
});

it("switches saved profiles without sending a key and remembers selection on reopen", async () => {
  const saved = vi.fn();
  const view = render(<SettingsDialog settings={settings} onSaved={saved} onClose={vi.fn()} />);
  await screen.findByText("API key saved locally");
  fireEvent.change(screen.getByLabelText("API provider profile"), { target: { value: "gateway" } });
  expect(screen.getByLabelText("API base URL")).toHaveValue(gateway.base_url);
  expect(screen.getByLabelText("API key")).toHaveValue("");
  expect(profiles.active_id).toBe("openai");
  fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
  await waitFor(() => expect(saved).toHaveBeenCalled());
  expect(fetcher).toHaveBeenCalledWith("/api/inference-profile-selection", expect.objectContaining({
    method: "PUT", body: JSON.stringify({ profile_id: "gateway" }),
  }));
  expect(fetcher.mock.calls.filter(([, opts]) => opts?.method === "PUT").every(([, opts]) => !opts.body.includes("api_key"))).toBe(true);
  view.unmount();
  render(<SettingsDialog settings={settings} onSaved={saved} onClose={vi.fn()} />);
  await waitFor(() => expect(screen.getByLabelText("API provider profile")).toHaveValue("gateway"));
});

it("edits a profile URL without replacing its saved key", async () => {
  const saved = vi.fn();
  render(<SettingsDialog settings={settings} onSaved={saved} onClose={vi.fn()} />);
  await screen.findByText("API key saved locally");
  fireEvent.change(screen.getByLabelText("API base URL"), { target: { value: "https://new.example/v1" } });
  fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
  await waitFor(() => expect(saved).toHaveBeenCalled());
  expect(fetcher).toHaveBeenCalledWith("/api/inference-profiles/openai", expect.objectContaining({
    method: "PUT", body: JSON.stringify({ name: "OpenAI", base_url: "https://new.example/v1", activate: true }),
  }));
});

it("deletes only the selected profile and falls back to the host", async () => {
  render(<SettingsDialog settings={settings} onSaved={vi.fn()} onClose={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "Delete provider profile" }));
  expect(await screen.findByText(/No host API key configured/)).toBeInTheDocument();
  expect(profiles.profiles.map((p) => p.id)).toEqual(["gateway", "host"]);
});

it("keeps the dialog open with profile edits after a provider save error", async () => {
  const saved = vi.fn();
  render(<SettingsDialog settings={settings} onSaved={saved} onClose={vi.fn()} />);
  await screen.findByText("API key saved locally");
  fetcher.mockResolvedValueOnce({ ok: false, json: async () => ({ detail: "Enter an HTTP or HTTPS API base URL" }) });
  fireEvent.change(screen.getByLabelText("API base URL"), { target: { value: "ftp://invalid.example" } });
  fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Enter an HTTP or HTTPS API base URL");
  expect(screen.getByLabelText("API base URL")).toHaveValue("ftp://invalid.example");
  expect(saved).not.toHaveBeenCalled();
});

it("prevents saves when provider profiles fail to load", async () => {
  const originalFetch = fetcher.getMockImplementation()!;
  fetcher.mockImplementation((url: string, options?: RequestInit) =>
    url.endsWith("/inference-profiles") ? Promise.reject(new Error("offline")) : originalFetch(url, options));
  const saved = vi.fn();
  render(<SettingsDialog settings={settings} onSaved={saved} onClose={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load settings");
  expect(screen.getByRole("button", { name: "Save settings" })).toBeDisabled();
});
