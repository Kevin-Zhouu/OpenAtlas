import { useRef, useState } from "react";
type Job = {
  id: string;
  status: string;
  can_continue?: boolean;
  progress: string;
  error?: string;
  created_at: string;
  request: { prompt: string; provider: string; retry_of?: string; continue_job?: string; revalidate_job?: string };
};
export function JobsDropdown({
  jobs,
  onInspect,
  onRetry,
}: {
  jobs: Job[];
  onInspect: (id: string) => void;
  onRetry?: (id: string, mode: "continue" | "rerun") => Promise<void>;
}) {
  const [pending, setPending] = useState<string | null>(null);
  const [retryError, setRetryError] = useState("");
  async function retry(id: string, mode: "continue" | "rerun") {
    if (!onRetry || pending) return;
    setPending(id); setRetryError("");
    try { await onRetry(id, mode); setFilter("queued"); }
    catch (error) { setRetryError(error instanceof Error ? error.message : "Could not retry. Please try again."); }
    finally { setPending(null); }
  }
  const [filter, setFilter] = useState("all");
  const dropdown = useRef<HTMLDetailsElement>(null);
  const active = jobs.filter((j) =>
    ["queued", "running"].includes(j.status),
  ).length;
  const failed = jobs.filter((j) => j.status === "failed").length;
  const shown = jobs.filter((j) => filter === "all" || j.status === filter);
  return (
    <details className="jobs-dropdown" ref={dropdown}>
      <summary aria-label="Jobs">
        Jobs {active > 0 && <span className="tag">{active} active</span>}
        {failed > 0 && (
          <span className="jobs-failed-count">{failed} failed</span>
        )}{" "}
        <span aria-hidden="true">⌄</span>
      </summary>
      <section className="jobs-popover" aria-label="Generation jobs">
        <div className="section-heading">
          <h2>Generation jobs</h2>
          <button
            className="quiet"
            aria-label="Close jobs"
            onClick={() => dropdown.current?.removeAttribute("open")}
          >
            ✕
          </button>
        </div>
        <label>
          Show jobs
          <select
            aria-label="Filter jobs"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">All jobs</option>
            <option value="running">Running</option>
            <option value="queued">Queued</option>
            <option value="failed">Failed</option>
            <option value="succeeded">Completed</option>
          </select>
        </label>
        {shown.length === 0 && (
          <p>No {filter === "all" ? "" : filter + " "}jobs.</p>
        )}
        {retryError && <p role="alert" className="jobs-error">{retryError}</p>}
        <ul>
          {shown.map((j) => (
            <li key={j.id}>
              <strong>{j.request.prompt}</strong>
              <p>
                <span className="tag">{j.status}</span> · {j.request.provider} ·{" "}
                {new Date(j.created_at).toLocaleString()}
              </p>
              <p className={j.error ? "jobs-error" : ""}>
                {j.error || j.progress}
              </p>
              {j.request.retry_of && <p className="hint">{j.request.continue_job ? "Continued from saved work" : "Fresh re-run of a failed job"}</p>}
              {j.status === "failed" && onRetry && <>
                <div className="job-retry-actions">
                  <button className="quiet" disabled={!!pending || !j.can_continue} onClick={() => retry(j.id, "continue")} title={j.can_continue ? "Resume the saved source in a new agent session" : "No saved workspace is available for this attempt"}>Continue</button>
                  <button className="quiet" disabled={!!pending} onClick={() => retry(j.id, "rerun")}>Re-run</button>
                  {pending === j.id && <span role="status">Queueing…</span>}
                </div>
                <p className="hint">{j.can_continue ? "Continue keeps saved work. Re-run starts over." : "No saved work remains; Re-run starts a fresh attempt."} {j.request.provider === "codex" && "Uses your current API credits."}</p>
              </>}
              {j.request.revalidate_job && (
                <p className="hint">
                  Recheck of a retained Notebook · no new inference
                </p>
              )}
              <button
                className="quiet"
                onClick={() => {
                  dropdown.current?.removeAttribute("open");
                  onInspect(j.id);
                }}
              >
                {j.status === "failed" ? "Debug failed job" : "Inspect job"}
              </button>
            </li>
          ))}
        </ul>
      </section>
    </details>
  );
}
