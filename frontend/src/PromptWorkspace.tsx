import { useEffect, useState } from "react";
type Revision = {
  id: string;
  content: string;
  created_at: string;
  parent_id?: string;
};
type Attempt = {
  id: string;
  status: string;
  error?: string;
  created_at: string;
  revisions: Revision[];
};
export function PromptWorkspace({ jobId }: { jobId: string }) {
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [selected, setSelected] = useState("");
  const [draft, setDraft] = useState("");
  const [compare, setCompare] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  async function call(path: string, body?: unknown) {
    const response = await fetch(
      "/api/" + path,
      body === undefined
        ? {}
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          },
    );
    const value = await response.json();
    if (!response.ok) throw new Error(value.detail || "Request failed");
    return value;
  }
  useEffect(() => {
    let stopped = false;
    async function load() {
      try {
        const rows = await call(`jobs/${jobId}/plans`);
        if (!stopped) setAttempts(rows);
      } catch (error) {
        if (!stopped) setMessage(String(error));
      }
    }
    void load();
    const timer = setInterval(load, 2000);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [jobId]);
  const revisions = attempts.flatMap((a) => a.revisions);
  const revision = revisions.find((r) => r.id === selected);
  async function action(kind: string) {
    setBusy(true);
    setMessage("");
    try {
      if (kind === "copy") {
        await navigator.clipboard.writeText(draft);
        setMessage("Copied");
      }
      if (kind === "edit") {
        const saved = await call(`prompts/${selected}/edit`, {
          content: draft,
        });
        setAttempts(await call(`jobs/${jobId}/plans`));
        setSelected(saved.id);
        setDraft(saved.content);
        setMessage("Saved as a new revision");
      }
      if (kind === "build") {
        const job = await call(`prompts/${selected}/build`, {});
        setMessage(`Build queued · ${job.id.slice(0, 8)}. Follow it in Jobs.`);
      }
      if (kind === "regenerate") {
        await call(`jobs/${jobId}/replan`, {});
        setMessage(
          "New planning attempt queued. Earlier candidates are retained.",
        );
      }
    } catch (error) {
      setMessage(String(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="generation-details">
      <h3>Notebook prompts</h3>
      <p>
        Select a candidate to inspect, edit, compare, or build. Saving creates a
        new revision.
      </p>
      {attempts.map((a) => (
        <p key={a.id}>
          Planning · {new Date(a.created_at).toLocaleString()} · {a.status}
          {a.error && ` · ${a.error}`}
        </p>
      ))}
      <button
        className="quiet"
        disabled={busy}
        onClick={() => action("regenerate")}
      >
        Regenerate prompt only
      </button>
      <label>
        Prompt revision
        <select
          value={selected}
          onChange={(e) => {
            setSelected(e.target.value);
            setDraft(
              revisions.find((r) => r.id === e.target.value)?.content || "",
            );
          }}
        >
          <option value="">Choose a saved prompt</option>
          {revisions.map((r, i) => (
            <option key={r.id} value={r.id}>
              {i + 1} · {r.parent_id ? "Edited" : "Generated"} ·{" "}
              {new Date(r.created_at).toLocaleString()}
            </option>
          ))}
        </select>
      </label>
      {revision && (
        <>
          <textarea
            aria-label="Editable build prompt"
            className="code-editor debug-prompt"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <div className="prompt-actions">
            <button
              className="quiet"
              disabled={busy || draft === revision.content}
              onClick={() => action("edit")}
            >
              Save new revision
            </button>
            <button
              className="quiet"
              disabled={busy}
              onClick={() => action("copy")}
            >
              Copy prompt
            </button>
            <button
              className="primary"
              disabled={busy || draft !== revision.content}
              onClick={() => action("build")}
            >
              Build from this prompt
            </button>
          </div>
          {draft !== revision.content && (
            <p>Save your edits before building.</p>
          )}
          <label>
            Compare with
            <select
              value={compare}
              onChange={(e) => setCompare(e.target.value)}
            >
              <option value="">No comparison</option>
              {revisions
                .filter((r) => r.id !== selected)
                .map((r) => (
                  <option key={r.id} value={r.id}>
                    {new Date(r.created_at).toLocaleString()} ·{" "}
                    {r.id.slice(0, 8)}
                  </option>
                ))}
            </select>
          </label>
          {compare && (
            <textarea
              aria-label="Comparison prompt"
              className="code-editor debug-prompt"
              readOnly
              value={revisions.find((r) => r.id === compare)?.content || ""}
            />
          )}
        </>
      )}
      {message && <p role="status">{message}</p>}
    </div>
  );
}
