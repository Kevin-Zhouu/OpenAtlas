import { PhoneAccess } from "./PhoneAccess";
import { useEffect, useState } from "react";

export type Settings = { provider: string; concurrency: number; model: string };
type CredentialStatus = { configured: boolean; source: string };
type Model = { id: string; name: string; default?: boolean };

type Props = {
  settings: Settings;
  onSaved: (settings: Settings) => void;
  onClose: () => void;
  debugMode?: boolean;
  onDebugChange?: (enabled: boolean) => void;
};

async function request<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch(`/api/${path}`, {
    method,
    ...(body === undefined
      ? {}
      : {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }),
  });
  const result = await response.json();
  if (!response.ok)
    throw new Error(
      typeof result.detail === "string"
        ? result.detail
        : "Could not save settings. Please check your input.",
    );
  return result;
}

export function SettingsDialog({
  settings,
  onSaved,
  onClose,
  debugMode,
  onDebugChange,
}: Props) {
  const [draft, setDraft] = useState(settings);
  const [key, setKey] = useState("");
  const [status, setStatus] = useState<CredentialStatus | null>(null);
  const [models, setModels] = useState<Model[]>([
    { id: "gpt-6-astra", name: "GPT-6 Astra", default: true },
  ]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([
      request<CredentialStatus>("credentials"),
      request<Model[]>("models"),
    ])
      .then(([credentials, choices]) => {
        if (active) {
          setStatus(credentials);
          setModels(choices);
        }
      })
      .catch(() => {
        if (active) setError("Could not load settings. Close and try again.");
      });
    return () => {
      active = false;
    };
  }, []);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (key.trim()) {
        setStatus(
          await request<CredentialStatus>("credentials", "PUT", {
            api_key: key.trim(),
          }),
        );
        setKey("");
      }
      onSaved(await request<Settings>("settings", "PUT", draft));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save settings.");
    } finally {
      setBusy(false);
    }
  }

  async function removeKey() {
    setBusy(true);
    setError("");
    try {
      setStatus(await request<CredentialStatus>("credentials", "DELETE"));
      setKey("");
    } catch {
      setError("Could not remove the saved key. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop">
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
      >
        <div className="section-heading">
          <h2 id="settings-title">Settings</h2>
          <button
            className="quiet"
            aria-label="Close settings"
            disabled={busy}
            onClick={onClose}
          >
            ✕
          </button>
        </div>
        <p className="hint">A few essentials for your local learning space.</p>
        <PhoneAccess />
        {error && (
          <p role="alert" className="settings-error">
            {error}
          </p>
        )}
        {onDebugChange && (
          <label className="debug-toggle">
            <input
              type="checkbox"
              checked={!!debugMode}
              onChange={(e) => onDebugChange(e.target.checked)}
            />{" "}
            Debug mode · inspect generation activity
          </label>
        )}
        <form onSubmit={save}>
          <label>
            Generation provider
            <select
              value={draft.provider}
              onChange={(e) => setDraft({ ...draft, provider: e.target.value })}
            >
              <option value="demo">Demo · authored lesson, no inference</option>
              <option value="codex">
                Codex · real AI generation in Docker
              </option>
            </select>
          </label>
          <label>
            OpenAI API key
            <input
              type="password"
              autoComplete="new-password"
              spellCheck={false}
              autoCapitalize="none"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder={
                status?.configured
                  ? "Leave blank to keep the configured key"
                  : "sk-…"
              }
              maxLength={512}
            />
          </label>
          <div className="credential-status" role="status">
            {status === null
              ? "Checking key status…"
              : status.configured
                ? status.source === "saved"
                  ? "API key saved locally"
                  : "API key configured by the host"
                : "No API key configured"}
            {status?.source === "saved" && (
              <button
                type="button"
                className="quiet"
                disabled={busy}
                onClick={removeKey}
              >
                Remove saved key
              </button>
            )}
          </div>
          <p className="hint">
            Your key stays on this OpenAtlas host, separate from your Notebooks.
            A saved key replaces the host-configured key for new generations.
          </p>
          <label>
            Codex model
            <select
              value={draft.model}
              onChange={(e) => setDraft({ ...draft, model: e.target.value })}
            >
              {models.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.name}
                  {model.default ? " (default)" : ""}
                </option>
              ))}
              {!models.some((model) => model.id === draft.model) && (
                <option value={draft.model}>
                  {draft.model} (saved selection)
                </option>
              )}
            </select>
          </label>
          <p className="hint">
            GPT-6 Astra is the default. Available models depend on your OpenAI
            account. Demo mode uses no API key or model inference.
          </p>
          <label>
            Concurrent generations
            <input
              type="number"
              min={1}
              max={8}
              required
              value={draft.concurrency}
              onChange={(e) =>
                setDraft({ ...draft, concurrency: Number(e.target.value) })
              }
            />
          </label>
          <button className="primary" disabled={busy}>
            {busy ? "Saving…" : "Save settings"}
          </button>
        </form>
      </section>
    </div>
  );
}
