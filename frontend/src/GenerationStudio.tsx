import { useEffect, useState } from "react";

export async function studioRequest<T>(
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
        : "Could not save. Check your input.",
    );
  return result;
}

export function PromptEditor({
  value,
  onChange,
}: {
  value?: string | null;
  onChange: (value: string | null) => void;
}) {
  const [defaultPrompt, setDefault] = useState("");
  const [preview, setPreview] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    studioRequest<{ default: string }>("prompt")
      .then((r) => setDefault(r.default))
      .catch((e) => setError(e.message));
  }, []);
  return (
    <div className="studio-panel">
      <p className="hint">
        Shape how Codex teaches and designs your Notebooks. Changes apply to new
        generations after you save settings. Use {"{{reading_minutes}}"} for the
        selected duration.
      </p>
      <label>
        Teaching and design prompt
        <textarea
          className="code-editor prompt-editor"
          value={value ?? defaultPrompt}
          disabled={!defaultPrompt}
          onChange={(e) => {
            onChange(e.target.value);
            setPreview("");
          }}
          spellCheck={false}
          maxLength={40000}
        />
      </label>
      <div className="studio-actions">
        <button
          type="button"
          onClick={() => {
            onChange(null);
            setPreview("");
          }}
        >
          Restore default
        </button>
        <button
          type="button"
          onClick={async () => {
            try {
              setPreview(
                (
                  await studioRequest<{ prompt: string }>(
                    "prompt/preview",
                    "POST",
                    { content: value ?? defaultPrompt },
                  )
                ).prompt,
              );
              setError("");
            } catch (e) {
              setError((e as Error).message);
            }
          }}
        >
          Preview full Codex prompt
        </button>
      </div>
      <p className="hint">
        The learner’s topic, selected skills, build contract and security rules
        are added automatically. Sandbox and publication validation remain
        enforced.
      </p>
      {error && <p role="alert">{error}</p>}
      {preview && (
        <details open>
          <summary>Full prompt · sample 20-minute request</summary>
          <pre className="prompt-preview">{preview}</pre>
        </details>
      )}
    </div>
  );
}

type Skill = {
  id: string;
  name: string;
  description: string;
  valid: boolean;
  error?: string;
};
type FileData = { content: string; revision: string };
export function SkillsManager({
  onDirtyChange,
}: { onDirtyChange?: (dirty: boolean) => void } = {}) {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [selected, setSelected] = useState("");
  const [files, setFiles] = useState<string[]>([]);
  const [path, setPath] = useState("");
  const [content, setContent] = useState("");
  const [saved, setSaved] = useState("");
  const [revision, setRevision] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [newPath, setNewPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const dirty = content !== saved;
  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);
  async function refresh() {
    setSkills(await studioRequest<Skill[]>("skills"));
  }
  useEffect(() => {
    refresh().catch((e) => setError(e.message));
  }, []);
  async function action(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function openFile(id: string, file: string) {
    setPath("");
    const result = await studioRequest<FileData>(
      `skill-files?skill_id=${encodeURIComponent(id)}&path=${encodeURIComponent(file)}`,
    );
    setPath(file);
    setContent(result.content);
    setSaved(result.content);
    setRevision(result.revision);
  }
  async function select(id: string) {
    setSelected(id);
    setPath("");
    setContent("");
    setSaved("");
    setFiles(
      (
        await studioRequest<{ files: string[] }>(
          `skill-files?skill_id=${encodeURIComponent(id)}`,
        )
      ).files,
    );
    await openFile(id, "SKILL.md");
  }
  return (
    <div className="studio-panel">
      <p className="hint">
        Portable Agent Skills. Files are saved on this host; skill scripts run
        only inside generation containers. Select capabilities separately when
        generating a Notebook.
      </p>
      <div className="studio-actions">
        <label className="upload-skill">
          Install ZIP
          <input
            aria-label="Install skill ZIP"
            type="file"
            accept=".zip"
            disabled={busy || dirty}
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file)
                void action(async () => {
                  if (file.size > 20 * 1024 * 1024)
                    throw new Error("ZIP exceeds 20 MB");
                  const response = await fetch("/api/skills/install", {
                    method: "POST",
                    headers: { "Content-Type": "application/zip" },
                    body: file,
                  });
                  const result = await response.json();
                  if (!response.ok) throw new Error(result.detail);
                  await refresh();
                  await select(result.id);
                  setNotice("Skill installed");
                });
            }}
          />
        </label>
      </div>
      <p className="hint">
        Upload a ZIP containing one skill folder with SKILL.md, references,
        scripts and assets (up to 20 MB).
      </p>
      <div className="studio-actions">
        <input
          aria-label="New skill name"
          placeholder="new-skill-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button
          type="button"
          disabled={busy || dirty || !name}
          onClick={() =>
            void action(async () => {
              const result = await studioRequest<{ id: string }>(
                "skills/create",
                "POST",
                { name },
              );
              await refresh();
              await select(result.id);
              setName("");
              setNotice("Skill created");
            })
          }
        >
          Create skill
        </button>
      </div>
      {error && (
        <p role="alert" className="settings-error">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <div className="skills-workbench">
        <nav aria-label="Installed skills">
          {skills.map((skill) => (
            <button
              type="button"
              key={skill.id}
              disabled={busy || dirty}
              className={selected === skill.id ? "selected" : ""}
              onClick={() => void action(() => select(skill.id))}
            >
              <strong>{skill.name}</strong>
              <small>
                {skill.id.startsWith("builtin:") ? "Built-in" : "Installed"}
                {!skill.valid ? " · Needs repair" : ""}
              </small>
            </button>
          ))}
        </nav>
        {selected && (
          <div className="skill-file-panel">
            <p className="hint">
              {skills.find((s) => s.id === selected)?.description}
              {skills.find((s) => s.id === selected)?.error && (
                <span role="alert">
                  {" "}
                  · {skills.find((s) => s.id === selected)?.error}
                </span>
              )}
            </p>
            <label>
              Skill file
              <select
                disabled={busy || dirty}
                value={path}
                onChange={(e) =>
                  void action(() => openFile(selected, e.target.value))
                }
              >
                <option value="" disabled>
                  Select a file
                </option>
                {files.map((file) => (
                  <option key={file}>{file}</option>
                ))}
              </select>
            </label>
            <div className="studio-actions">
              <input
                aria-label="New file path"
                placeholder="references/example.md"
                value={newPath}
                onChange={(e) => setNewPath(e.target.value)}
              />
              <button
                type="button"
                disabled={busy || dirty || !newPath}
                onClick={() => {
                  if (files.includes(newPath)) {
                    setError("File already exists. Select it above.");
                    return;
                  }
                  setPath(newPath);
                  setFiles([...files, newPath]);
                  setContent("");
                  setSaved("");
                  setRevision(null);
                  setNewPath("");
                }}
              >
                New file
              </button>
            </div>
            {path && (
              <>
                <label>
                  {path}
                  <textarea
                    aria-label="Skill file contents"
                    className="code-editor"
                    spellCheck={false}
                    value={content}
                    maxLength={500000}
                    onChange={(e) => setContent(e.target.value)}
                  />
                </label>
                <div className="studio-actions">
                  <button
                    type="button"
                    className="primary"
                    disabled={busy}
                    onClick={() =>
                      void action(async () => {
                        const result = await studioRequest<FileData>(
                          "skill-files",
                          "PUT",
                          { skill_id: selected, path, content, revision },
                        );
                        setRevision(result.revision);
                        setSaved(content);
                        await refresh();
                        setNotice(
                          "File saved. Future generations will use this version.",
                        );
                      })
                    }
                  >
                    {busy ? "Saving…" : "Save file"}
                  </button>
                  <button
                    type="button"
                    disabled={busy || !dirty}
                    onClick={() => setContent(saved)}
                  >
                    Discard edits
                  </button>
                  <span className="hint">{dirty ? "Unsaved changes" : ""}</span>
                </div>
              </>
            )}
            <p className="hint">
              Save or discard edits before switching files. Built-in edits are
              persistent local overrides. Queued jobs keep their selected skill
              fingerprint and may need resubmitting if you change those files.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
