import { useLayoutEffect, useMemo, useRef, useState } from "react";
import Markdown from "react-markdown";

export type ActivitySource = {
  id: string;
  agent_log: string;
  status: string;
  stage?: string;
  started_at?: string;
};
type Task = { text: string; completed: boolean };
type Change = { path: string; kind: string };
export type ActivityItem = {
  id: string;
  kind: string;
  status: "running" | "completed" | "failed";
  text: string;
  command: string;
  output: string;
  tasks: Task[];
  changes: Change[];
};
const value = (v: unknown) => (typeof v === "string" ? v : "");

// Codex emits start/update/completion for the same item. Keep one row per item
// in start order, replacing its contents as newer observations arrive.
export function parseActivity(log: string, scope: string): ActivityItem[] {
  const items = new Map<string, ActivityItem>();
  for (const line of log.split("\n")) {
    try {
      const event = JSON.parse(line);
      if (!event || typeof event !== "object") continue;
      const item = event.item || (String(event.type).startsWith("planner.") ? {
        type: "planner_activity", status: "completed",
        text: event.type === "planner.resource_read" ? `Read ${event.path} · offset ${event.offset} · ${event.characters} characters`
          : event.type === "planner.resources" ? `Available resources: ${(event.paths || []).join(", ")}`
          : event.type === "planner.started" ? `Planner started · ${event.model}` : `Planner tool event · ${event.name || event.type}`,
      } : undefined);
      if (
        !item &&
        !["error", "turn.failed", "turn.completed"].includes(event.type)
      )
        continue;
      const kind =
        value(item?.type) ||
        (event.type === "turn.completed" ? "finished" : "error");
      const text =
        value(item?.text) ||
        value(item?.message) ||
        value(event.message) ||
        value(event.error?.message) ||
        value(item?.query);
      const id =
        scope + ":" + (value(item?.id) || `${kind}:${text.slice(0, 100)}`);
      const previous = items.get(id);
      const status =
        item?.status === "failed" ||
        item?.status === "error" ||
        kind === "error" ||
        event.type === "turn.failed"
          ? "failed"
          : event.type === "item.completed" ||
              event.type === "turn.completed" ||
              item?.status === "completed"
            ? "completed"
            : "running";
      items.set(id, {
        id,
        kind,
        status,
        text: text || previous?.text || "",
        command: value(item?.command) || previous?.command || "",
        output: value(item?.aggregated_output) || previous?.output || "",
        tasks: Array.isArray(item?.items)
          ? item.items
              .filter((t: Task) => typeof t?.text === "string")
              .map((t: Task) => ({
                text: t.text,
                completed: t.completed === true,
              }))
          : previous?.tasks || [],
        changes: Array.isArray(item?.changes)
          ? item.changes
              .filter((c: Change) => typeof c?.path === "string")
              .map((c: Change) => ({ path: c.path, kind: value(c.kind) }))
          : previous?.changes || [],
      });
    } catch {
      /* The retained log can begin/end in the middle of a JSON line. */
    }
  }
  return [...items.values()].slice(-60);
}

export function ActivitySpinner({ label = "Running" }: { label?: string }) {
  return <span className="activity-spinner" role="img" aria-label={label} />;
}
function Item({
  item,
  live,
  paused,
}: {
  item: ActivityItem;
  live: boolean;
  paused: boolean;
}) {
  const running = live && !paused && item.status === "running";
  const status = running
    ? "Running"
    : item.status === "running"
      ? live && paused
        ? "Paused"
        : "Ended"
      : item.status === "failed"
        ? "Attention"
        : "Completed";
  const names: Record<string, string> = {
    command_execution: "Command",
    file_change: "File changes",
    agent_message: "Codex",
    planner_message: "Planner",
    planner_activity: "Planner activity",
    reasoning: "Agent update",
    todo_list: "Plan",
    web_search: "Searching the web",
    mcp_tool_call: "Tool call",
    error: "Agent notice",
    finished: "Agent finished",
  };
  const title = names[item.kind] || "Agent activity";
  const pending = item.tasks.findIndex((t) => !t.completed);
  const commandPreview = item.command.split("\n")[0].slice(0, 160);
  return (
    <article
      className={`activity-item activity-${item.kind} ${running ? "is-running" : ""} ${item.status === "failed" ? "has-error" : ""}`}
      data-activity-id={item.id}
    >
      <div className="activity-marker">
        {running ? (
          <ActivitySpinner />
        ) : (
          <span aria-hidden="true">
            {item.status === "running"
              ? paused && live
                ? "Ⅱ"
                : "–"
              : item.status === "failed"
                ? "!"
                : item.kind === "agent_message"
                  ? "✦"
                  : item.kind === "command_execution"
                    ? "›_"
                    : "✓"}
          </span>
        )}
      </div>
      <div className="activity-content">
        <div className="activity-heading">
          <strong>{title}</strong>
          <span>
            {item.tasks.length
              ? `${item.tasks.filter((task) => task.completed).length} of ${item.tasks.length} complete`
              : status}
          </span>
        </div>
        {item.text && (
          <div className="activity-message">
            <Markdown
              skipHtml
              components={{
                a: ({ children }) => (
                  <span className="activity-reference">{children}</span>
                ),
                img: ({ alt }) => <span>{alt}</span>,
              }}
            >
              {item.text}
            </Markdown>
          </div>
        )}
        {item.command && (
          <details className="activity-tool">
            <summary>
              <code>{commandPreview}</code>
              <span className="activity-expand">Details</span>
            </summary>
            <div className="activity-tool-body">
              <h5>Command</h5>
              <pre>{item.command}</pre>
              <h5>Output</h5>
              <pre>
                {item.output ||
                  (running
                    ? "Waiting for command output…"
                    : "No output captured.")}
              </pre>
            </div>
          </details>
        )}
        {!item.command && item.output && (
          <details className="activity-tool">
            <summary>Tool output</summary>
            <pre>{item.output}</pre>
          </details>
        )}
        {item.tasks.length > 0 && (
          <div className="activity-plan">
            {item.tasks.map((task, i) => (
              <div
                className={`activity-task ${task.completed ? "is-complete" : ""}`}
                key={i}
              >
                {task.completed ? (
                  <span aria-label="Completed">✓</span>
                ) : live && !paused && i === pending ? (
                  <ActivitySpinner label="Current task" />
                ) : (
                  <span className="task-pending" aria-label="Not completed" />
                )}
                <span>{task.text}</span>
              </div>
            ))}
          </div>
        )}
        {item.changes.length > 0 && (
          <div className="activity-files">
            {item.changes.map((change, i) => (
              <div key={i}>
                <span className="file-change-kind">
                  {change.kind || "changed"}
                </span>
                <code>{change.path}</code>
              </div>
            ))}
          </div>
        )}
      </div>
    </article>
  );
}
export function AgentActivity({
  sources,
  running,
  paused,
  progress,
}: {
  sources: ActivitySource[];
  running: boolean;
  paused: boolean;
  progress: string;
}) {
  const viewport = useRef<HTMLDivElement>(null),
    follow = useRef(true);
  const [following, setFollowing] = useState(true);
  const groups = useMemo(
    () =>
      [...sources]
        .sort((a, b) => (a.started_at || "").localeCompare(b.started_at || ""))
        .map((source) => ({
          source,
          items: parseActivity(source.agent_log, source.id).map(item => source.stage === "planning" && item.kind === "agent_message" ? {...item, kind: "planner_message"} : item),
        })),
    [sources],
  );
  useLayoutEffect(() => {
    if (follow.current && viewport.current)
      viewport.current.scrollTop = viewport.current.scrollHeight;
  }, [groups, progress]);
  function jump() {
    follow.current = true;
    setFollowing(true);
    if (viewport.current)
      viewport.current.scrollTop = viewport.current.scrollHeight;
  }
  return (
    <div className="activity-feed-shell">
      <div
        className="activity-feed"
        ref={viewport}
        role="log"
        aria-label="Agent activity"
        aria-live="off"
        tabIndex={0}
        onScroll={() => {
          const el = viewport.current;
          if (el) {
            follow.current =
              el.scrollHeight - el.scrollTop - el.clientHeight < 64;
            setFollowing(follow.current);
          }
        }}
      >
        <div className="activity-feed-note">
          Oldest to newest · latest activity at the bottom
        </div>
        {groups.map(({ source, items }, i) => (
          <section className="activity-attempt" key={source.id}>
            {groups.length > 1 && (
              <div className="activity-attempt-label">
                Agent run {i + 1} <code>{source.id.slice(0, 12)}</code>
              </div>
            )}
            {items.map((item) => (
              <Item
                key={item.id}
                item={item}
                live={running && source.status === "running"}
                paused={paused}
              />
            ))}
            {!items.length && (
              <p className="activity-empty">Waiting for agent events…</p>
            )}
          </section>
        ))}
        {running && (
          <div className="activity-working" role="status">
            {paused ? (
              <span className="activity-paused" aria-hidden="true">
                Ⅱ
              </span>
            ) : (
              <ActivitySpinner label="Generation running" />
            )}
            <span>
              {paused ? "Live updates paused" : progress || "Codex is working…"}
            </span>
            {!paused && (
              <span className="activity-working-dots" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
            )}
          </div>
        )}
      </div>
      {!following && (
        <button className="activity-jump" onClick={jump}>
          ↓ Jump to latest
        </button>
      )}
    </div>
  );
}
