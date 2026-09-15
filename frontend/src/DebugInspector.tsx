import { useEffect, useState } from "react";
import { PromptWorkspace } from "./PromptWorkspace";
import {
  GenerationDetails,
  type GenerationMetadata,
} from "./GenerationDetails";
import { AgentActivity } from "./AgentActivity";
import { ValidationDetails, type ValidationRound } from "./ValidationDetails";

type Stage = "planning" | "building" | "validating" | "publishing";
const stages: { id: Stage; title: string; description: string }[] = [
  {
    id: "planning",
    title: "Planning",
    description: "Shape the learning experience and its creative brief.",
  },
  {
    id: "building",
    title: "Implementing",
    description: "Turn the selected brief into an interactive Notebook.",
  },
  {
    id: "validating",
    title: "Validating",
    description: "Check the Notebook and its interactions in the browser.",
  },
  {
    id: "publishing",
    title: "Publishing",
    description: "Save the finished Notebook to your library.",
  },
];
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
  validation?: ValidationRound[];
  generation?: GenerationMetadata;
  updated_at: string | null;
  containers: Container[];
  events?: { stage: string; message: string; created_at: string }[];
  related_jobs?: { id: string; status: string; created_at: string }[];
  planning_job_id?: string;
  job: {
    stage?: string;
    status: string;
    progress: string;
    error?: string;
    version_id?: string;
    request: {
      prompt?: string;
      provider: string;
      model?: string;
      planner_model?: string;
      planning_enabled?: boolean;
      prompt_only?: boolean;
      build_prompt?: string;
      prompt_revision_id?: string;
      revalidate_job?: string;
    };
  };
};
function currentStage(data: Snapshot): Stage {
  if (stages.some((s) => s.id === data.job.stage))
    return data.job.stage as Stage;
  if (data.job.status === "succeeded")
    return data.job.request.prompt_only ? "planning" : "publishing";
  const recorded = data.events
    ?.filter((e) => stages.some((s) => s.id === e.stage))
    .at(-1)?.stage;
  if (data.job.status === "failed" && recorded) return recorded as Stage;
  if (data.job.request.revalidate_job) return "validating";
  if (
    data.job.request.planning_enabled &&
    !data.job.request.build_prompt &&
    !data.containers.some((c) => c.stage === "building")
  )
    return "planning";
  return "building";
}
export function DebugInspector({
  jobId,
  onClose,
}: {
  jobId: string;
  onClose: () => void;
}) {
  const [activeJob, setActiveJob] = useState(jobId);
  const [selectedStage, setSelectedStage] = useState<Stage | null>(null);
  const [tab, setTab] = useState("activity");
  const [data, setData] = useState<Snapshot | null>(null);
  const [planning, setPlanning] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    setActiveJob(jobId);
  }, [jobId]);
  useEffect(() => {
    setData(null);
    setPlanning(null);
    setSelectedStage(null);
    setTab("activity");
    setError("");
    setPaused(false);
  }, [activeJob]);
  useEffect(() => {
    if (paused) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function read(id: string): Promise<Snapshot> {
      const response = await fetch(
        `/api/jobs/${encodeURIComponent(id)}/debug`,
        { signal: controller.signal },
      );
      if (!response.ok)
        throw new Error(
          "Could not load diagnostics. Check your connection or host access.",
        );
      return response.json();
    }
    async function poll() {
      try {
        const result = await read(activeJob);
        const previous =
          result.planning_job_id && result.planning_job_id !== activeJob
            ? await read(result.planning_job_id)
            : null;
        if (!stopped) {
          setData(result);
          setPlanning(previous);
          setError("");
        }
      } catch (e) {
        if (!stopped)
          setError(
            e instanceof Error ? e.message : "Could not load diagnostics.",
          );
      }
      if (!stopped) timer = setTimeout(poll, 2000);
    }
    void poll();
    return () => {
      stopped = true;
      controller.abort();
      clearTimeout(timer);
    };
  }, [activeJob, paused]);
  const terminal = !!data && ["succeeded", "failed"].includes(data.job.status);
  const current = data ? currentStage(data) : "planning";
  const stage = selectedStage ?? current;
  const definition = stages.find((s) => s.id === stage)!;
  const stageData = stage === "planning" && planning ? planning : data;
  const containers = (stageData?.containers || []).filter(
    (c) => (c.stage || "building") === stage,
  );
  const events = (stageData?.events || []).filter((e) => e.stage === stage);
  const hasPlan =
    !!data &&
    (!!data.job.request.planning_enabled ||
      !!data.job.request.build_prompt ||
      !!planning ||
      data.containers.some((c) => c.stage === "planning"));
  function state(id: Stage) {
    if (!data) return "pending";
    if (id === "planning" && !hasPlan) return "skipped";
    if (data.job.request.prompt_only && id !== "planning") return "pending";
    if (id === "planning" && data.job.request.build_prompt) return "complete";
    if (id === "building" && data.job.request.revalidate_job) return "skipped";
    if (data.job.status === "queued") return "pending";
    if (id === "validating" && id !== current && (data.validation?.length || data.events?.some(e => e.stage === "validating"))) {
      const latest = data.validation?.at(-1);
      if (latest) return latest.status === "passed" ? "complete" : "failed";
      return current === "building" ? "failed" : "complete";
    }
    if (id === current)
      return data.job.status === "failed"
        ? "failed"
        : terminal
          ? "complete"
          : "active";
    if (
      stages.findIndex((s) => s.id === id) <
      stages.findIndex((s) => s.id === current)
    )
      return "complete";
    return "pending";
  }
  const stageState = state(stage);
  const live = stage === current && !terminal && data?.job.status === "running";
  const metadata = stageData?.generation;
  const scopedMetadata = metadata
    ? {
        ...metadata,
        request: {
          ...metadata.request,
          model:
            stage === "planning"
              ? metadata.request.planner_model
              : metadata.request.model,
        },
        invocations: metadata.invocations.filter((i) =>
          stage === "planning"
            ? i.phase === "planning"
            : i.phase !== "planning",
        ),
        prompt: stage === "planning" ? null : metadata.prompt,
      }
    : null;
  const statusText =
    stageState === "active"
      ? "In progress"
      : stageState === "complete"
        ? "Complete"
        : stageState === "failed"
          ? "Needs attention"
          : stageState === "skipped"
            ? "Not used"
            : "Not started";
  async function cancel() {
    try {
      const response = await fetch(`/api/jobs/${activeJob}/cancel`, {
        method: "POST",
      });
      if (!response.ok) throw new Error("Cancellation failed");
    } catch (e) {
      setError(String(e));
    }
  }
  return (
    <div className="modal-backdrop">
      <section
        className="modal debug-inspector generation-inspector"
        role="dialog"
        aria-modal="true"
        aria-labelledby="debug-title"
      >
        <header className="inspector-header">
          <div className="inspector-heading">
            <div>
              <span className="inspector-eyebrow">Generation inspector</span>
              <h2 id="debug-title">
                {data?.job.request.prompt || "Your Notebook"}
              </h2>
            </div>
            <button
              className="quiet inspector-close"
              onClick={onClose}
              aria-label="Close inspector"
            >
              ✕
            </button>
          </div>
          <div className="inspector-meta">
            <span
              className={`inspector-connection ${terminal ? "is-finished" : ""}`}
            >
              <i />
              {terminal
                ? data?.job.request.prompt_only &&
                  data.job.status === "succeeded"
                  ? "Prompt ready to build"
                  : data?.job.status === "failed"
                    ? "Generation stopped"
                    : "Notebook ready"
                : data?.job.status === "queued"
                  ? "Waiting for a generation slot"
                  : paused
                    ? "Updates paused"
                    : "Live generation"}
            </span>
            {(data?.related_jobs?.length || 0) > 1 && (
              <label className="inspector-attempt">
                Attempt
                <select
                  aria-label="Generation attempt"
                  value={activeJob}
                  onChange={(e) => setActiveJob(e.target.value)}
                >
                  {data?.related_jobs?.map((j, i) => (
                    <option key={j.id} value={j.id}>
                      {i + 1} · {j.status} ·{" "}
                      {new Date(j.created_at).toLocaleString()}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
          <nav className="generation-stages" aria-label="Generation stages">
            {stages.map((s, i) => (
              <button
                key={s.id}
                type="button"
                className={`generation-stage stage-${state(s.id)} ${stage === s.id ? "is-selected" : ""}`}
                aria-pressed={stage === s.id}
                aria-current={current === s.id ? "step" : undefined}
                onClick={() => {
                  setSelectedStage(s.id);
                  setTab("activity");
                }}
              >
                <span className="stage-marker" aria-hidden="true">
                  {state(s.id) === "complete"
                    ? "✓"
                    : state(s.id) === "failed"
                      ? "!"
                      : i + 1}
                </span>
                <span className="stage-label">
                  {s.title}
                  <small>
                    {state(s.id) === "active"
                      ? "In progress"
                      : state(s.id) === "complete"
                        ? "Complete"
                        : state(s.id) === "failed"
                          ? "Needs attention"
                          : state(s.id) === "skipped"
                            ? "Not used"
                            : "Up next"}
                  </small>
                </span>
              </button>
            ))}
          </nav>
        </header>
        <div className="inspector-body">
          {error && (
            <p role="alert" className="debug-failure">
              {error}
            </p>
          )}
          {!data && !error && <p>Loading diagnostics…</p>}
          {data && (
            <>
              <div className="stage-heading">
                <div>
                  <h3>
                    {definition.title}
                    <span className={`stage-status status-${stageState}`}>
                      {statusText}
                    </span>
                  </h3>
                  <p>{definition.description}</p>
                </div>
                {!terminal && (
                  <button className="quiet" onClick={() => setPaused(!paused)}>
                    {paused ? "Resume live updates" : "Pause live updates"}
                  </button>
                )}
              </div>
              <div className="trace-downloads" aria-label="Download generation traces">
                <a className="quiet" href={`/api/jobs/${encodeURIComponent(activeJob)}/trace?stage=${stage}`} download>Download {definition.title.toLowerCase()} trace</a>
                <a className="quiet" href={`/api/jobs/${encodeURIComponent(activeJob)}/trace`} download>Download all stage traces</a>
              </div>
              <nav
                className="stage-tabs"
                aria-label={`${definition.title} views`}
              >
                <button
                  aria-pressed={tab === "activity"}
                  onClick={() => setTab("activity")}
                >
                  Activity & logs
                </button>
                <button
                  aria-pressed={tab === "details"}
                  onClick={() => setTab("details")}
                >
                  Generation details
                </button>
                {stage === "planning" && hasPlan && (
                  <button
                    aria-pressed={tab === "prompt"}
                    onClick={() => setTab("prompt")}
                  >
                    Build prompt
                    {data.job.request.build_prompt && (
                      <span className="tab-dot" />
                    )}
                  </button>
                )}
              </nav>
              {stage === current && data.job.error && (
                <p className="debug-failure" role="alert">
                  {data.job.error}
                </p>
              )}
              {tab === "prompt" && stage === "planning" && (
                <PromptWorkspace
                  key={activeJob}
                  jobId={activeJob}
                  selectedRevision={data.job.request.prompt_revision_id}
                  onJobQueued={(id) => setActiveJob(id)}
                />
              )}
              {tab === "details" && (
                <>
                  {(stage === "planning" || stage === "building") &&
                  scopedMetadata ? (
                    <GenerationDetails
                      key={`${activeJob}-${stage}`}
                      data={scopedMetadata}
                      stage={stage}
                    />
                  ) : (
                    <div className="stage-system-details">
                      <dl>
                        <dt>Execution</dt>
                        <dd>OpenAtlas background runner</dd>
                        <dt>Stage</dt>
                        <dd>
                          {definition.title} · {statusText}
                        </dd>
                      </dl>
                      <p>
                        {stage === "validating"
                          ? "The browser validator checks the static artifact, resource loading, sandbox compatibility, and declared interactions. Failed checks can send the Notebook back for repair."
                          : stage === "publishing"
                            ? "The publisher retains editable source, packaged static files, version metadata, and the selected prompt revision in your local library."
                            : "Historical agent instructions are not available for this attempt."}
                      </p>
                      {data.job.version_id && stage === "publishing" && (
                        <p>
                          Published version <code>{data.job.version_id}</code>
                        </p>
                      )}
                    </div>
                  )}
                </>
              )}
              {tab === "activity" && (
                <>
                  {stage === "validating" && !!data.validation?.length ? (
                    <ValidationDetails rounds={data.validation} />
                  ) : containers.some((c) => c.role === "agent") ? (
                    <AgentActivity
                      sources={containers.filter((c) => c.role === "agent")}
                      running={!!live}
                      paused={paused}
                      progress={data.job.progress}
                    />
                  ) : (
                    <div className="stage-empty">
                      <span
                        className={`stage-empty-icon status-${stageState}`}
                        aria-hidden="true"
                      >
                        {stageState === "complete"
                          ? "✓"
                          : stageState === "failed"
                            ? "!"
                            : "◷"}
                      </span>
                      <h4>
                        {stageState === "pending"
                          ? `${definition.title} hasn’t started yet`
                          : stageState === "skipped"
                            ? "This attempt did not use a planner"
                            : stageState === "complete"
                              ? `${definition.title} complete`
                              : live
                                ? data.job.progress
                                : "No retained activity for this stage"}
                      </h4>
                      <p>
                        {data.job.request.provider === "demo"
                          ? "Demo generation uses no Codex container."
                          : stageState === "pending"
                            ? data.job.request.prompt_only
                              ? "Review the build prompt, then choose Build from this prompt to continue here."
                              : "Activity will appear here when this stage begins."
                            : stage === "planning" &&
                                data.job.request.build_prompt
                              ? "Your creative brief is saved. Open Build prompt to review it or prepare another version."
                              : "This stage runs in the OpenAtlas background runner. Available events appear below."}
                      </p>
                      {stage === "planning" &&
                        data.job.request.build_prompt && (
                          <button
                            className="primary"
                            onClick={() => setTab("prompt")}
                          >
                            Review build prompt
                          </button>
                        )}
                    </div>
                  )}
                  {events.length > 0 && (
                    <ol
                      className="stage-event-log"
                      aria-label={`${definition.title} events`}
                    >
                      {events.map((e, i) => (
                        <li key={i}>
                          <time>
                            {new Date(e.created_at).toLocaleTimeString()}
                          </time>
                          <span>{e.message}</span>
                        </li>
                      ))}
                    </ol>
                  )}
                  {containers.length > 0 && (
                    <details className="stage-container-details">
                      <summary>
                        Container details & raw logs{" "}
                        <span>{containers.length}</span>
                      </summary>
                      {containers.map((c) => (
                        <section className="debug-container" key={c.id}>
                          <h4>
                            {c.role === "agent"
                              ? stage === "planning"
                                ? "Planner agent"
                                : "Codex agent"
                              : "Credential relay"}
                            <span className="tag">{c.status}</span>
                          </h4>
                          <dl>
                            <dt>Container</dt>
                            <dd>{c.id}</dd>
                            <dt>Image</dt>
                            <dd>{c.image}</dd>
                            <dt>Resources</dt>
                            <dd>
                              {c.cpu_limit} CPUs ·{" "}
                              {Math.round(c.memory_limit / 1024 / 1024)} MB ·{" "}
                              {c.read_only ? "Read-only root" : "Writable root"}
                            </dd>
                          </dl>
                          {c.role === "agent" && (
                            <details>
                              <summary>Raw agent event log</summary>
                              <pre>{c.agent_log || "No output recorded."}</pre>
                            </details>
                          )}
                          <details>
                            <summary>Container logs</summary>
                            <pre>
                              {c.container_log || "No output recorded."}
                            </pre>
                          </details>
                          <details>
                            <summary>Processes</summary>
                            <pre>
                              {c.processes
                                ?.map((p) => p.join("  "))
                                .join("\n") || "No process snapshot available."}
                            </pre>
                          </details>
                        </section>
                      ))}
                    </details>
                  )}
                </>
              )}
            </>
          )}
        </div>
        <footer className="inspector-footer">
          <span>
            {terminal ? "Retained snapshot" : "Updates every 2 seconds"} ·
            credentials redacted
          </span>
          {data && !terminal ? (
            <button className="quiet" onClick={cancel}>
              Cancel generation
            </button>
          ) : (
            <button className="quiet" onClick={onClose}>
              Done
            </button>
          )}
        </footer>
      </section>
    </div>
  );
}
