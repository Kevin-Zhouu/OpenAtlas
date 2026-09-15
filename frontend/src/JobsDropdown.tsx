import { useRef, useState } from "react";
import { stageNames, type ResumeStage } from './ResumeActions';
type Job = {
  id: string;
  notebook_id?: string;
  status: string;
  stage?: string;
  can_continue?: boolean;
  stopped_stage?: string;
  resume_stages?: ResumeStage[];
  resume_stage?: ResumeStage | null;
  progress: string;
  error?: string;
  created_at: string;
  request: {
    prompt: string;
    provider: string;
    retry_of?: string;
    continue_job?: string;
    revalidate_job?: string;
    resume_stage?: ResumeStage;
  };
};
export function JobsDropdown({
  jobs,
  onInspect,
  onRetry,
  onDelete,
  onResume,
}: {
  jobs: Job[];
  onDelete?: (id: string, title: string) => void;
  onInspect: (id: string) => void;
  onRetry?: (id: string, mode: "continue" | "rerun") => Promise<void>;
  onResume?: (id: string) => Promise<void>;
}) {
  const [pending, setPending] = useState<string | null>(null);
  const [retryError, setRetryError] = useState("");
  async function retry(id: string, mode: "resume" | "rerun") {
    if (pending || (mode === "resume" ? !onResume : !onRetry)) return;
    setPending(id);
    setRetryError("");
    try {
      if (mode === "resume") await onResume!(id);
      else await onRetry!(id, "rerun");
      setFilter("queued");
    } catch (error) {
      setRetryError(
        error instanceof Error
          ? error.message
          : "Could not retry. Please try again.",
      );
    } finally {
      setPending(null);
    }
  }
  const [filter, setFilter] = useState("all");
  const dropdown = useRef<HTMLDetailsElement>(null);
  const active = jobs.filter((j) =>
    ["queued", "running"].includes(j.status),
  ).length;
  const failed = jobs.filter((j) => j.status === "failed").length;
  const candidates = jobs.filter(
    (j) => filter === "all" || j.status === filter,
  );
  const shown = candidates.filter(
    (j, i) =>
      !candidates
        .slice(0, i)
        .some(
          (previous) =>
            (previous.notebook_id || previous.id) === (j.notebook_id || j.id),
        ),
  );
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
        {retryError && (
          <p role="alert" className="jobs-error">
            {retryError}
          </p>
        )}
        <ul>
          {shown.map((j) => (
            <li key={j.id}>
              <strong>{j.request.prompt}</strong>
              <p>
                <span className="job-stage-label">{j.status === 'failed' && j.stopped_stage ? `Stopped during ${stageNames[j.stopped_stage as ResumeStage] || j.stopped_stage}` : j.stage || j.status}</span> ·{" "}
                {j.request.provider} · {new Date(j.created_at).toLocaleString()}
              </p>
              <p className={j.error ? "jobs-error" : ""}>
                {j.error || j.progress}
              </p>
              {j.request.retry_of && (
                <p className="hint">
                  {j.request.resume_stage ? `Resumed from ${stageNames[j.request.resume_stage]}` : j.request.continue_job
                    ? "Continued from saved work"
                    : "Fresh re-run of a failed job"}
                </p>
              )}
              {j.status === "failed" && (onResume || onRetry) && <>
                <div className="job-retry-actions">
                  {onResume && <button className="quiet" disabled={!!pending || !j.resume_stage}
                    title={j.resume_stage ? `Resume ${stageNames[j.resume_stage]} using saved work` : 'Saved input for the stopped stage is unavailable'}
                    onClick={() => void retry(j.id, 'resume')}>Resume</button>}
                  {onRetry && <button className="quiet" disabled={!!pending}
                    onClick={() => void retry(j.id, 'rerun')}>Re-run</button>}
                  {pending === j.id && <span role="status">Queueing…</span>}
                </div>
                <p className="hint">{j.resume_stage
                  ? `Resumes ${stageNames[j.resume_stage]} from saved work. Re-run starts over.`
                  : 'Saved input for the stopped stage is unavailable. Inspect the attempt or start over.'}</p>
              </>}
              {onDelete && <button className="quiet delete-link" onClick={() => { dropdown.current?.removeAttribute('open'); onDelete(j.id,j.request.prompt); }}>Delete permanently</button>}
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
                {j.status === "failed" ? "Inspect generation" : "Inspect job"}
              </button>
            </li>
          ))}
        </ul>
      </section>
    </details>
  );
}
