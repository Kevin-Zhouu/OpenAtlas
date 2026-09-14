import { PromptWorkspace } from "./PromptWorkspace";
import { GenerationDetails, type GenerationMetadata } from "./GenerationDetails";
import { useEffect, useState } from "react";
import { AgentActivity, ActivitySpinner } from "./AgentActivity";

type Container = {
  id: string;
  role: string;
  stage?: string;
  image: string;
  status: string;
  started_at: string;
  observed_at: string;
  memory_limit: number;
  cpu_limit: number;
  read_only: boolean;
  processes: string[][];
  agent_log: string;
  container_log: string;
};
type Snapshot = {
  generation?: GenerationMetadata;
  updated_at: string | null;
  containers: Container[];
  job: {
    stage?: string;
    status: string;
    progress: string;
    error?: string;
    request: { provider: string; model?: string };
  };
};
export function DebugInspector({
  jobId,
  onClose,
}: {
  jobId: string;
  onClose: () => void;
}) {
  const [tab, setTab] = useState("activity");
  const [data, setData] = useState<Snapshot | null>(null),
    [error, setError] = useState(""),
    [paused, setPaused] = useState(false);
  useEffect(() => {
    setData(null);
    setError("");
  }, [jobId]);
  useEffect(() => {
    if (paused) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function poll() {
      try {
        const response = await fetch(
          `/api/jobs/${encodeURIComponent(jobId)}/debug`,
          { signal: controller.signal },
        );
        if (!response.ok)
          throw new Error(
            "Could not load diagnostics. Check your connection or host access.",
          );
        const result = await response.json();
        if (!stopped) {
          setData(result);
          setError("");
        }
      } catch (e) {
        if (!stopped)
          setError(
            e instanceof Error ? e.message : "Could not load diagnostics.",
          );
      }
      if (!stopped && !paused) timer = setTimeout(poll, 2000);
    }
    void poll();
    return () => {
      stopped = true;
      controller.abort();
      clearTimeout(timer);
    };
  }, [jobId, paused]);
  const terminal = data && ["succeeded", "failed"].includes(data.job.status);
  return (
    <div className="modal-backdrop">
      <section
        className="modal debug-inspector"
        role="dialog"
        aria-modal="true"
        aria-labelledby="debug-title"
      >
        <div className="section-heading">
          <h2 id="debug-title">Generation inspector</h2>
          <button
            className="quiet"
            onClick={onClose}
            aria-label="Close inspector"
          >
            ✕
          </button>
        </div>
        <div className="debug-toolbar">
          <span className={`debug-connection ${paused ? "is-paused" : ""}`}>
            <i />
            {terminal
              ? "Retained snapshot"
              : paused
                ? "Updates paused"
                : "Live activity"}
          </span>
          <code className="debug-id" title={jobId}>
            {jobId.slice(0, 8)}
          </code>
          <button className="quiet" onClick={() => setPaused(!paused)}>
            {paused ? "Resume live updates" : "Pause live updates"}
          </button>
        </div>
        {data && !terminal && <button className="quiet" onClick={async () => { try { const response = await fetch(`/api/jobs/${jobId}/cancel`, {method: 'POST'}); if (!response.ok) throw new Error('Cancellation failed'); } catch (error) { setError(String(error)); } }}>Cancel generation</button>}
        <nav className="settings-tabs" aria-label="Inspector views"><button aria-pressed={tab === "activity"} onClick={()=>setTab("activity")}>Activity & logs</button><button aria-pressed={tab === "details"} onClick={()=>setTab("details")}>Generation details</button><button aria-pressed={tab === "prompts"} onClick={()=>setTab("prompts")}>Prompts</button></nav>
        {tab === "details" && data?.generation && <GenerationDetails key={jobId} data={data.generation}/>}
        {tab === "prompts" && <PromptWorkspace jobId={jobId}/>}
        {error && <p role="alert">{error}</p>}
        {!data && !error && <p>Loading diagnostics…</p>}
        {data && tab === "activity" && (
          <>
            <div className="debug-job-summary">
              <span className={`debug-job-state state-${data.job.status}`}>
                {data.job.status === "running" && !paused && (
                  <ActivitySpinner label="Job running" />
                )}
                {data.job.stage || data.job.status}
              </span>
              <span>
                {data.job.request.provider} · {data.job.request.model}
              </span>
            </div>
            {data.job.error && (
              <p className="debug-failure" role="alert">
                {data.job.error}
              </p>
            )}
            {data.containers.some((c) => c.role === "agent") ? (
              <AgentActivity
                sources={data.containers.filter((c) => c.role === "agent")}
                running={!terminal && data.job.status === "running"}
                paused={paused}
                progress={data.job.progress}
              />
            ) : (
              <p>{data.job.progress}</p>
            )}
            <div className="debug-capture-note">
              {data.updated_at &&
                `Captured ${new Date(data.updated_at).toLocaleTimeString()} · `}
              Recent output retained · known credentials redacted
            </div>
            {!data.containers.length && (
              <p>
                {data.job.request.provider === "demo"
                  ? "Demo generation uses no Codex container. Job progress is shown above."
                  : "No container diagnostics captured yet. Queued jobs and older completed generations may have no snapshot."}
              </p>
            )}
            {data.containers.length > 0 && (
              <details className="debug-diagnostics">
                <summary>
                  Container details & raw logs{" "}
                  <span>{data.containers.length} containers</span>
                </summary>
                <p className="hint">
                  Read-only diagnostics. Newest 128 KB of agent output per
                  container; logs may include your prompt and generated source.
                </p>
                {data.containers.map((c) => (
                  <section className="debug-container" key={c.id}>
                    <h3>
                      <span className="tag">{c.stage === "planning" ? "Planner" : "Builder"}</span>{" "}{c.role === "agent" ? (c.stage === "planning" ? "Agents SDK" : "Codex agent") : "Credential relay"}{" "}
                      <span className="tag">{c.status}</span>
                    </h3>
                    <dl>
                      <dt>Container</dt>
                      <dd className="debug-id">{c.id}</dd>
                      <dt>Image</dt>
                      <dd>{c.image}</dd>
                      <dt>Limits</dt>
                      <dd>
                        {c.cpu_limit} CPUs ·{" "}
                        {Math.round(c.memory_limit / 1024 / 1024)} MB memory
                      </dd>
                      <dt>Filesystem</dt>
                      <dd>
                        {c.read_only ? "Read-only root" : "Writable root"}
                      </dd>
                      <dt>Started</dt>
                      <dd>{new Date(c.started_at).toLocaleString()}</dd>
                    </dl>
                    {c.role === "agent" && (
                      <details>
                        <summary>Raw Codex event log</summary>
                        <pre>{c.agent_log || "Waiting for Codex output…"}</pre>
                      </details>
                    )}
                    <details>
                      <summary>Processes (PID / executable)</summary>
                      <pre>
                        {c.processes.map((p) => p.join("  ")).join("\n") ||
                          "No process snapshot available."}
                      </pre>
                    </details>
                    <details>
                      <summary>Container logs</summary>
                      <pre>
                        {c.container_log ||
                          "No container stdout/stderr. Codex activity is in the agent log above."}
                      </pre>
                    </details>
                  </section>
                ))}
              </details>
            )}
          </>
        )}
      </section>
    </div>
  );
}
