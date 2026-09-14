import { useState } from "react";
export type GenerationMetadata = {
  request: Record<string, unknown>;
  job: Record<string, unknown>;
  prompt: string | null;
  prompt_source: string;
  skills: {
    id: string;
    name: string;
    version?: string;
    sha256?: string;
    sandbox_path: string;
  }[];
  invocations: {
    captured_at: string;
    phase: string;
    prompt: string | null;
    command: string[];
    model?: string;
    validation_feedback?: string;
  }[];
};
export function GenerationDetails({
  data,
  stage,
}: {
  data: GenerationMetadata;
  stage?: "planning" | "building";
}) {
  const [attempt, setAttempt] = useState(0);
  const invocation = data.invocations[attempt];
  const prompt = invocation?.prompt ?? data.prompt;
  return (
    <div className="generation-details">
      <dl className="generation-facts">
        {[
          "provider",
          "model",
          "reading_minutes",
          "skills_enabled",
          "base_version",
          "continue_job",
          "retry_of",
          "revalidate_job",
        ]
          .filter(
            (k) => data.request[k] !== undefined && data.request[k] !== null,
          )
          .map((k) => (
            <div key={k}>
              <dt>
                {(
                  {
                    reading_minutes: "Reading minutes",
                    skills_enabled: "Skills enabled",
                    base_version: "Revision of",
                    continue_job: "Continued from",
                    retry_of: "Retry of",
                    revalidate_job: "Revalidation of",
                  } as Record<string, string>
                )[k] ?? k}
              </dt>
              <dd>{String(data.request[k])}</dd>
            </div>
          ))}
      </dl>
      <h3>Learning request</h3>
      <p className="generation-input">{String(data.request.prompt ?? "")}</p>
      <h3>Additional instructions</h3>
      <p className="generation-input">
        {String(data.request.instructions || "None")}
      </p>
      <h3>
        Skills passed to generation{" "}
        <span className="hint">{data.skills.length}</span>
      </h3>
      {data.skills.length ? (
        data.skills.map((s) => (
          <details className="generation-skill" key={s.id}>
            <summary>
              {s.name}{" "}
              <span className="hint">
                {s.version ? `v${s.version}` : "No declared version"}
              </span>
            </summary>
            <dl>
              <dt>Identifier</dt>
              <dd>{s.id}</dd>
              <dt>Sandbox path</dt>
              <dd>
                <code>{s.sandbox_path}</code>
              </dd>
              <dt>Content fingerprint</dt>
              <dd>
                <code>{s.sha256 || "Unavailable"}</code>
              </dd>
            </dl>
          </details>
        ))
      ) : (
        <p className="hint">No skills were selected.</p>
      )}
      <h3>
        {stage === "planning"
          ? "Planner instructions"
          : stage === "building"
            ? "Implementation instructions"
            : "Instructions supplied to each agent"}
      </h3>
      {data.invocations.length > 0 ? (
        <>
          <label>
            Agent invocation
            <select
              value={attempt}
              onChange={(e) => setAttempt(Number(e.target.value))}
            >
              {data.invocations.map((x, i) => (
                <option key={i} value={i}>
                  {i + 1} · {x.phase} ·{" "}
                  {new Date(x.captured_at).toLocaleString()}
                </option>
              ))}
            </select>
          </label>
          <p className="hint">
            Captured immediately before invocation. Known credentials are
            redacted.
          </p>
        </>
      ) : (
        <p className="hint">
          {data.prompt_source === "not_applicable"
            ? "No agent invocation was recorded for this stage."
            : "Reconstructed from saved job inputs and the current adapter. No invocation has been captured for this job. The exact historical prompt, if any, may differ."}
        </p>
      )}
      {prompt && (
        <textarea
          aria-label={
            stage === "planning"
              ? "Full planner instructions"
              : "Full Codex prompt"
          }
          className="code-editor debug-prompt"
          readOnly
          value={prompt}
          spellCheck={false}
        />
      )}
      {invocation && (
        <details>
          <summary>Execution arguments</summary>
          <pre>
            {JSON.stringify(
              invocation.command.slice(0, stage === "planning" ? 3 : -1),
              null,
              2,
            )}
          </pre>
          <p className="hint">
            Captured for this invocation. Credential values and environment
            variables are not included.
          </p>
        </details>
      )}
      <details>
        <summary>All saved generation metadata</summary>
        <pre>
          {JSON.stringify(
            {
              job: data.job,
              request: data.request,
              skills: data.skills,
              invocations: data.invocations,
            },
            null,
            2,
          )}
        </pre>
      </details>
    </div>
  );
}
