import { PromptEditor, SkillsManager } from "./GenerationStudio";
import { PhoneAccess } from "./PhoneAccess";
import { ChatGPTSubscription } from "./ChatGPTSubscription";
import { useEffect, useState } from "react";

export type Settings = {
  inference_auth?: "api_key" | "chatgpt";
  provider: string;
  concurrency: number;
  generation_timeout_minutes?: number;
  model: string;
  planner_model?: string;
  planner_instructions?: string;
  teaching_prompt?: string | null;
};
type Profile = {
  id: string;
  name: string;
  base_url: string;
  configured: boolean;
  source: string;
};
type Profiles = { active_id: string; profiles: Profile[] };
const defaultBaseUrl = "https://api.openai.com/v1";
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
  const [skillsOpened, setSkillsOpened] = useState(false);
  const [editorDirty, setEditorDirty] = useState(false);
  const [tab, setTab] = useState("general");
  const [draft, setDraft] = useState(settings);
  const [key, setKey] = useState("");
  const [profiles, setProfiles] = useState<Profiles | null>(null);
  const [profileId, setProfileId] = useState("host");
  const [profileName, setProfileName] = useState("");
  const [baseUrl, setBaseUrl] = useState(defaultBaseUrl);
  const selectedProfile = profiles?.profiles.find((p) => p.id === profileId);

  function chooseProfile(id: string, data = profiles) {
    const profile = data?.profiles.find((p) => p.id === id);
    setProfileId(id);
    setProfileName(profile?.name || "");
    setBaseUrl(profile?.base_url || defaultBaseUrl);
    setKey("");
    setError("");
  }

  function acceptProfiles(data: Profiles) {
    setProfiles(data);
    chooseProfile(data.active_id, data);
  }
  const [models, setModels] = useState<Model[]>([
    { id: "gpt-6-astra", name: "GPT-6 Astra", default: true },
  ]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([
      request<Profiles>("inference-profiles"),
      request<Model[]>("models"),
    ])
      .then(([credentials, choices]) => {
        if (active) {
          acceptProfiles(credentials);
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
      if (!profiles) throw new Error("Provider profiles have not loaded yet.");
      if (draft.inference_auth !== "chatgpt") {
        if (profileId === "host") {
          if (profiles.active_id !== "host") {
            acceptProfiles(await request<Profiles>("inference-profile-selection", "PUT", {
              profile_id: "host",
            }));
          }
        } else {
          const changed = profileId === "new" || key.trim() ||
            profileName !== selectedProfile?.name || baseUrl !== selectedProfile?.base_url;
          if (changed) {
            acceptProfiles(await request<Profiles>(
              profileId === "new" ? "inference-profiles" : `inference-profiles/${profileId}`,
              profileId === "new" ? "POST" : "PUT",
              { name: profileName.trim(), base_url: baseUrl.trim(),
                ...(key.trim() ? { api_key: key.trim() } : {}), activate: true },
            ));
          } else if (profiles.active_id !== profileId) {
            acceptProfiles(await request<Profiles>("inference-profile-selection", "PUT", {
              profile_id: profileId,
            }));
          }
        }
      }
      onSaved(await request<Settings>("settings", "PUT", draft));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save settings.");
    } finally {
      setBusy(false);
    }
  }

  async function removeProfile() {
    setBusy(true);
    setError("");
    try {
      acceptProfiles(await request<Profiles>(`inference-profiles/${profileId}`, "DELETE"));
    } catch {
      setError("Could not delete the provider profile. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop">
      <section
        className={"modal settings-studio " + (tab !== "general" ? "wide" : "")}
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
      >
        <div className="section-heading">
          <h2 id="settings-title">Settings</h2>
          <button
            className="quiet"
            aria-label="Close settings"
            disabled={busy || editorDirty}
            onClick={onClose}
          >
            ✕
          </button>
        </div>
        <nav className="settings-tabs" aria-label="Settings sections">
          {["general", "planner", "prompt", "skills"].map((item) => (
            <button
              key={item}
              type="button"
              aria-pressed={tab === item}
              onClick={() => {
                setTab(item);
                if (item === "skills") setSkillsOpened(true);
              }}
            >
              {item === "general"
                ? "General"
                : item === "planner" ? "Planner" : item === "prompt"
                  ? "Generation prompt"
                  : "Skills"}
            </button>
          ))}
        </nav>
        {skillsOpened && (
          <div hidden={tab !== "skills"}>
            <SkillsManager onDirtyChange={setEditorDirty} />
          </div>
        )}
        {editorDirty && tab !== "skills" && (
          <p className="hint">
            Save or discard your skill file edits in Skills before closing
            settings.
          </p>
        )}
        {tab === "general" && <PhoneAccess />}
        {error && (
          <p role="alert" className="settings-error">
            {error}
          </p>
        )}
        {tab === "general" && onDebugChange && (
          <label className="debug-toggle">
            <input
              type="checkbox"
              checked={!!debugMode}
              onChange={(e) => onDebugChange(e.target.checked)}
            />{" "}
            Debug mode · inspect generation activity
          </label>
        )}
        <form
          onSubmit={save}
          style={{ display: tab === "skills" ? "none" : undefined }}
        >
          {tab === "planner" && <>
            <label>Planner model<input value={draft.planner_model || "gpt-6-astra"} onChange={e => setDraft({...draft, planner_model: e.target.value})} required /></label>
            <label>
              Planner instructions
              <textarea className="planner-instructions-editor" rows={16}
                value={draft.planner_instructions || ""}
                onChange={e => setDraft({ ...draft, planner_instructions: e.target.value })}
                aria-describedby="planner-instructions-help" />
            </label>
            <button className="quiet" type="button" onClick={async () => { try { const defaults = await request<{planner_default: string}>("prompt"); setDraft({...draft, planner_instructions: defaults.planner_default}); } catch { setError("Could not load planner defaults"); } }}>Restore default planner instructions</button>
            <p className="hint" id="planner-instructions-help">Guide how the planner writes your Notebook’s creative brief. Saved changes apply to new planning attempts.</p>
          </>}
          {tab === "prompt" && (
            <PromptEditor
              value={draft.teaching_prompt}
              onChange={(teaching_prompt) =>
                setDraft({ ...draft, teaching_prompt })
              }
            />
          )}
          <div hidden={tab !== "general"}>
            <label>
              Generation provider
              <select
                value={draft.provider}
                onChange={(e) =>
                  setDraft({ ...draft, provider: e.target.value })
                }
              >
                <option value="demo">
                  Demo · authored lesson, no inference
                </option>
                <option value="codex">
                  Codex · real AI generation in Docker
                </option>
              </select>
            </label>
            <label>
              Inference authentication
              <select value={draft.inference_auth || "api_key"} disabled={busy}
                onChange={(e) => setDraft({ ...draft, inference_auth: e.target.value as "api_key" | "chatgpt" })}>
                <option value="api_key">API key · OpenAI or custom provider</option>
                <option value="chatgpt">ChatGPT subscription · sign in</option>
              </select>
            </label>
            {draft.inference_auth === "chatgpt" ? <ChatGPTSubscription /> :
            <fieldset disabled={busy || !profiles} className="inference-profiles">
              <legend>Inference API</legend>
              <label>
                API provider profile
                <select value={profileId} onChange={(e) => chooseProfile(e.target.value)}>
                  {!profiles && <option value="host">Loading providers…</option>}
                  {profiles?.profiles.map((profile) => (
                    <option key={profile.id} value={profile.id}>
                      {profile.name}{profile.id === profiles.active_id ? " (active)" : ""}
                    </option>
                  ))}
                  <option value="new">Add a new provider…</option>
                </select>
              </label>
              {profileId !== "host" ? <>
                <label>
                  Provider name
                  <input value={profileName} maxLength={80} required={tab === "general"}
                    placeholder="e.g. My API provider"
                    onChange={(e) => setProfileName(e.target.value)} />
                </label>
                <label>
                  API base URL
                  <input type="url" value={baseUrl} maxLength={2048} required={tab === "general"}
                    spellCheck={false} autoCapitalize="none"
                    placeholder={defaultBaseUrl}
                    onChange={(e) => setBaseUrl(e.target.value)} />
                </label>
                <label>
                  API key
                  <input type="password" autoComplete="new-password" spellCheck={false}
                    autoCapitalize="none" value={key} maxLength={4096}
                    required={profileId === "new" && tab === "general"}
                    onChange={(e) => setKey(e.target.value)}
                    placeholder={selectedProfile?.configured
                      ? "Leave blank to keep this profile’s saved key" : "Enter your provider’s API key"} />
                </label>
                <div className="credential-status" role="status">
                  {selectedProfile?.configured ? "API key saved locally" : "A key is required for a new provider"}
                  {selectedProfile?.source === "saved" && (
                    <button type="button" className="quiet" onClick={removeProfile}>
                      Delete provider profile
                    </button>
                  )}
                </div>
              </> : <p role="status" className="hint">
                {selectedProfile?.configured ? "API key configured by the host" : "No host API key configured"}
                {selectedProfile && <> · {selectedProfile.base_url}</>}
              </p>}
              <p className="hint">
                Save settings to use the selected profile. Switching keeps your other saved
                providers and keys. Keys stay on this host and are never shown again.
                Deleting the active profile restores the host configuration.
              </p>
              <p className="hint">
                Use a Responses-compatible API base URL, such as https://api.example.com/v1.
                Both Codex and the planner use this provider. For a server on this computer,
                use host.docker.internal instead of localhost.
              </p>
            </fieldset>}
            <label>
              Codex model
              <input list="codex-model-options" value={draft.model} required maxLength={200}
                onChange={(e) => setDraft({ ...draft, model: e.target.value })} />
            </label>
            <datalist id="codex-model-options">
              {models.map((model) => <option key={model.id} value={model.id}>{model.name}</option>)}
            </datalist>
            <p className="hint">
              Enter a model ID supported by your provider, or choose a suggestion.
              Set the planner’s model in the Planner tab. Demo mode uses no inference.
            </p>
            <label>
              Generation time limit (minutes)
              <input type="number" min={1} max={1440} step={1} required
                value={draft.generation_timeout_minutes ?? 120}
                onChange={(e) => setDraft({ ...draft, generation_timeout_minutes: Number(e.target.value) })} />
            </label>
            <p className="hint">Applies separately to each planning, generation, or repair attempt. New jobs and retries use this limit; running attempts keep their original limit. Default: 120 minutes. Maximum: 24 hours.</p>
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
          </div>
          <button className="primary" disabled={busy || editorDirty || !profiles}>
            {busy ? "Saving…" : "Save settings"}
          </button>
        </form>
      </section>
    </div>
  );
}
