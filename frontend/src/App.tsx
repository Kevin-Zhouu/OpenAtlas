import { pairFromFragment } from "./pairing";
import { useEffect, useState } from "react";
import { Notifications } from "./Notifications";
import { JobsDropdown } from "./JobsDropdown";
import { DebugInspector } from "./DebugInspector";
import { SettingsDialog, type Settings } from "./SettingsDialog";

type Skill = {
  id: string;
  name: string;
  description: string;
  required: boolean;
  valid: boolean;
  error?: string;
};
type Job = {
  id: string;
  notebook_id: string;
  status: string;
  progress: string;
  error?: string;
  created_at: string;
  request: { prompt: string; provider: string; revalidate_job?: string };
};
type Notebook = {
  id: string;
  title: string;
  latest_version: string;
  created_at: string;
  provider: string;
  versions?: Version[];
};
type Version = {
  id: string;
  provider: string;
  created_at: string;
  manifest: {
    entrypoint: string;
    description: string;
    target_reading_minutes?: number;
  };
  provenance: Skill[];
};
async function api<T>(
  url: string,
  body?: unknown,
  method = "POST",
): Promise<T> {
  const response = await fetch(
    "/api" + url,
    body === undefined
      ? {}
      : {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
  if (!response.ok) {
    const data = await response.json();
    throw new Error(
      response.status === 401
        ? "AUTH"
        : typeof data.detail === "string"
          ? data.detail
          : "Please check your input and try again.",
    );
  }
  return response.json();
}
const Arrow = () => <span aria-hidden="true">↗</span>;

export function App() {
  const [debugMode, setDebugMode] = useState(
    () => localStorage.getItem("openatlas-debug") === "true",
  );
  const [debugJob, setDebugJob] = useState<string | null>(null);
  const [notebooks, setNotebooks] = useState<Notebook[]>([]),
    [jobs, setJobs] = useState<Job[]>([]),
    [skills, setSkills] = useState<Skill[]>([]),
    [settings, setSettings] = useState<Settings>({
      provider: "demo",
      concurrency: 2,
      model: "gpt-6-astra",
    });
  const [readingMinutes, setReadingMinutes] = useState(20);
  const [skillsEnabled, setSkillsEnabled] = useState(true);
  const [prompt, setPrompt] = useState(""),
    [instructions, setInstructions] = useState(""),
    [selected, setSelected] = useState<string[]>([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [showSettings, setShowSettings] = useState(false),
    [auth, setAuth] = useState(false),
    [token, setToken] = useState("");
  const [reader, setReader] = useState<Notebook | null>(null),
    [version, setVersion] = useState(""),
    [revising, setRevising] = useState(false),
    [history, setHistory] = useState(false);
  const [jobsReady, setJobsReady] = useState(false);
  const notebookId = window.location.pathname.match(
    /^\/notebooks\/([^/]+)$/,
  )?.[1];
  async function refresh() {
    try {
      const [n, j] = await Promise.all([
        api<Notebook[]>("/notebooks"),
        api<Job[]>("/jobs"),
      ]);
      setNotebooks(n);
      setJobs(j);
      setJobsReady(true);
      if (notebookId) {
        const book = await api<Notebook>("/notebooks/" + notebookId);
        setReader(book);
        setVersion((v) => v || book.latest_version);
      }
    } catch (e) {
      handle(e);
    }
  }
  function handle(e: unknown) {
    const message = e instanceof Error ? e.message : "Something went wrong";
    if (message === "AUTH") setAuth(true);
    else setError(message);
  }
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setInterval>;
    pairFromFragment().then(() => {
      if (!active) return;
      refresh();
      api<Skill[]>("/skills").then(setSkills).catch(handle);
      api<Settings>("/settings").then(setSettings).catch(handle);
      timer = setInterval(refresh, 1800);
    }).catch(e => { if (active) { handle(e); setAuth(true); } });
    return () => { active = false; clearInterval(timer); };
  }, []);
  const generationProvider = revising
    ? reader?.versions?.find((v) => v.id === reader?.latest_version)
        ?.provider || settings.provider
    : settings.provider;
  async function generate(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api(
        revising ? "/notebooks/" + notebookId + "/revisions" : "/jobs",
        {
          prompt,
          skills: skillsEnabled ? selected : [],
          skills_enabled: skillsEnabled,
          instructions,
          provider: generationProvider,
          reading_minutes: readingMinutes,
        },
      );
      setPrompt("");
      setInstructions("");
      setRevising(false);
      await refresh();
    } catch (e) {
      handle(e);
    } finally {
      setBusy(false);
    }
  }
  function beginRevision() {
    const current = reader?.versions?.find(
      (v) => v.id === reader.latest_version,
    );
    setSelected(
      current?.provenance.filter((s) => !s.required).map((s) => s.id) || [],
    );
    setSkillsEnabled(Boolean(current?.provenance.length));
    setReadingMinutes(current?.manifest.target_reading_minutes || 20);
    setRevising(true);
  }
  const active = jobs.filter(
    (j) =>
      ["queued", "running"].includes(j.status) &&
      (!notebookId || j.notebook_id === notebookId),
  );
  const options = (
    <details className="options">
      <summary>
        Generation skills{" "}
        <span>
          {!skillsEnabled
            ? "Disabled"
            : selected.length
              ? selected.length + " selected"
              : "& extra guidance"}
        </span>
        <span className="chevron">＋</span>
      </summary>
      <div className="option-body">
        <p className="hint">
          Optional guidance for how your Notebook is taught.
        </p>
        <label className="skill">
          <input
            type="checkbox"
            checked={skillsEnabled}
            onChange={(e) => setSkillsEnabled(e.target.checked)}
          />
          <span>
            <strong>Use generation skills</strong>
            <small>
              Turn off to exclude all skills, including OpenAtlas core, for this
              generation.
            </small>
          </span>
        </label>
        {skillsEnabled &&
          skills
            .filter((s) => !s.required)
            .map((s) => (
              <label className="skill" key={s.id}>
                <input
                  type="checkbox"
                  disabled={!s.valid}
                  checked={selected.includes(s.id)}
                  onChange={(e) =>
                    setSelected(
                      e.target.checked
                        ? [...selected, s.id]
                        : selected.filter((id) => id !== s.id),
                    )
                  }
                />
                <span>
                  <strong>{s.name}</strong>
                  <small>{s.valid ? s.description : s.error}</small>
                </span>
              </label>
            ))}
        {skillsEnabled &&
          selected
            .filter((id) => !skills.some((s) => s.id === id))
            .map((id) => (
              <label className="skill" key={id}>
                <input
                  type="checkbox"
                  checked
                  onChange={() => setSelected(selected.filter((s) => s !== id))}
                />
                {id} · removed; uncheck to continue
              </label>
            ))}
        <label className="instructions">
          Additional generation instructions <span>Optional</span>
          <textarea
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            placeholder="Make it more visual. Add an experiment I can play with…"
            rows={2}
          />
        </label>
      </div>
    </details>
  );
  const form = (
    <form onSubmit={generate} className="composer">
      <label className="sr-only" htmlFor="topic">
        What do you want to learn?
      </label>
      <textarea
        id="topic"
        required
        minLength={3}
        maxLength={12000}
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder={
          revising
            ? "How would you like to improve this Notebook?"
            : "A topic, a big question, or something you’ve always wondered about…"
        }
        rows={3}
      />
      <div className="composer-bottom">
        <span className="hint">
          {generationProvider === "demo"
            ? "Demo mode · No API key needed"
            : "Codex · Made for your curiosity"}
        </span>
        <button className="primary" disabled={busy || prompt.trim().length < 3}>
          {busy
            ? "Adding to your queue…"
            : revising
              ? "Create revision"
              : "Generate Notebook"}{" "}
          <Arrow />
        </button>
      </div>
      <div className="reading-duration">
        <div className="duration-heading">
          <label htmlFor="reading-minutes">Time to explore</label>
          <output htmlFor="reading-minutes">{readingMinutes} min</output>
        </div>
        <input
          id="reading-minutes"
          type="range"
          min="5"
          max="50"
          step="5"
          value={readingMinutes}
          aria-valuetext={`${readingMinutes} minutes`}
          onChange={(e) => setReadingMinutes(Number(e.target.value))}
        />
        <div className="duration-scale">
          <span>5 min · Quick idea</span>
          <span>50 min · Deep exploration</span>
        </div>
        <p className="hint">
          {generationProvider === "demo"
            ? "Demo has a fixed lesson; this target is used for AI-generated Notebooks."
            : "Approximate reading + interaction time. Longer sessions explore more foundations, examples, and practice."}
        </p>
      </div>
      {options}
    </form>
  );
  return (
    <>
      <header className={"topbar " + (reader ? "reader-bar" : "")}>
        <a className="brand" href="/">
          <svg
            width="28"
            height="28"
            viewBox="0 0 28 28"
            fill="none"
            aria-hidden="true"
          >
            <path
              d="M4 6c4-1 7 0 10 3 3-3 6-4 10-3v16c-4-1-7 0-10 2-3-2-6-3-10-2V6Z"
              stroke="currentColor"
              strokeWidth="1.6"
            />
            <path
              d="M14 9v15M8 11l3 1M8 15l3 1M18 12l3-1M18 16l3-1"
              stroke="currentColor"
              strokeWidth="1.4"
            />
          </svg>
          OpenAtlas
        </a>
        <JobsDropdown
          jobs={jobs}
          onInspect={(id) => {
            setDebugMode(true);
            localStorage.setItem("openatlas-debug", "true");
            setDebugJob(id);
          }}
        />
        <Notifications
          jobs={jobs}
          ready={jobsReady}
          error={error}
          onInspect={(id) => {
            setDebugMode(true);
            localStorage.setItem("openatlas-debug", "true");
            setDebugJob(id);
          }}
        />
        {reader ? (
          <div className="reader-tools">
            <select
              aria-label="Notebook version"
              value={version}
              onChange={(e) => setVersion(e.target.value)}
            >
              {reader.versions?.map((v, i) => (
                <option key={v.id} value={v.id}>
                  Version {(reader.versions?.length || 0) - i}
                  {v.provider === "demo" ? " · Demo" : ""}
                </option>
              ))}
            </select>
            <button className="quiet" onClick={beginRevision}>
              Revise Notebook
            </button>
          </div>
        ) : (
          <button
            className="quiet settings-button"
            onClick={() => setShowSettings(true)}
            aria-label="Settings"
          >
            <span aria-hidden="true">⚙</span>{" "}
            <span className="settings-label">Settings</span>
          </button>
        )}
      </header>
      {reader && !revising ? (
        <>
          <div className="reader-title">
            <a href="/">← Your library</a>
            <span>{reader.title}</span>
          </div>
          {active.map((j) => (
            <div className="reader-progress" key={j.id}>
              {j.progress}
            </div>
          ))}
          <iframe
            key={version}
            className="notebook-frame"
            title="Notebook content"
            sandbox="allow-scripts"
            src={
              "/artifacts/" +
              reader.id +
              "/" +
              version +
              "/" +
              (reader.versions?.find((v) => v.id === version)?.manifest
                .entrypoint || "index.html")
            }
          />
        </>
      ) : (
        <main className="home">
          <section className="intro">
            <div className="eyebrow">A PERSONAL LIBRARY FOR A CURIOUS MIND</div>
            <h1>
              {revising ? (
                "A new way to see it."
              ) : (
                <>
                  What do you
                  <br className="mobile-break" /> want to learn?
                </>
              )}
            </h1>
            <p>
              {revising
                ? "Describe the change. Your current version stays in your library."
                : "Follow your curiosity. Turn any question into a Notebook you can explore."}
            </p>
          </section>
          {form}
          {revising && (
            <button className="quiet" onClick={() => setRevising(false)}>
              Cancel revision
            </button>
          )}
          {!revising && (
            <>
              <div className="suggestions">
                <span>Start somewhere</span>
                {[
                  "How does a language model remember?",
                  "The hidden life of trees",
                  "Why do planets orbit?",
                ].map((t) => (
                  <button key={t} onClick={() => setPrompt(t)}>
                    {t} <Arrow />
                  </button>
                ))}
              </div>
              <section className="library">
                <div className="section-heading">
                  <h2>
                    Your Notebooks{" "}
                    <span>{notebooks.length.toString().padStart(2, "0")}</span>
                  </h2>
                  <button
                    className="quiet"
                    onClick={() => setHistory(!history)}
                  >
                    {history ? "Hide history" : "Generation history"}
                  </button>
                </div>
                {active.map((j) => (
                  <div className="job" key={j.id}>
                    <div className="spinner" />
                    <div>
                      <strong>{j.request.prompt}</strong>
                      <p aria-live="polite">{j.progress}</p>
                      {debugMode && (
                        <button
                          className="quiet"
                          onClick={() => setDebugJob(j.id)}
                        >
                          Inspect generation
                        </button>
                      )}
                    </div>
                    <span className="tag">
                      {j.request.provider === "demo" ? "DEMO" : "CREATING"}
                    </span>
                  </div>
                ))}
                {notebooks.map((n, i) => (
                  <a
                    className="notebook-row"
                    href={"/notebooks/" + n.id}
                    key={n.id}
                  >
                    <span className="book-number">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <div>
                      <h3>{n.title}</h3>
                      <span>
                        {new Date(n.created_at).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric",
                        })}{" "}
                        <b>·</b>{" "}
                        {n.provider === "demo"
                          ? "Demo Notebook"
                          : "Interactive Notebook"}
                      </span>
                    </div>
                    <span className="row-arrow">↗</span>
                  </a>
                ))}
                {!notebooks.length && !active.length && (
                  <div className="empty">
                    <svg
                      width="50"
                      height="50"
                      viewBox="0 0 50 50"
                      fill="none"
                      aria-hidden="true"
                    >
                      <path
                        d="M11 12h13c4 0 7 3 7 6v23c-2-3-5-4-9-4H11V12Z M31 18c0-4 4-7 9-7v26c-4 0-7 1-9 4"
                        stroke="currentColor"
                        strokeWidth="1.2"
                      />
                      <path
                        d="M17 20h8M17 25h8M17 30h5"
                        stroke="currentColor"
                      />
                    </svg>
                    <h3>A little curiosity goes a long way.</h3>
                    <p>
                      Your first Notebook begins with a question above.
                      <br />
                      It will be saved here, ready whenever you are.
                    </p>
                  </div>
                )}
                {history && (
                  <div className="history">
                    {jobs.length === 0 && <p>No generation jobs yet.</p>}
                    {jobs.map((j) => (
                      <div key={j.id}>
                        <strong>{j.request.prompt}</strong>
                        <span className="tag">{j.status}</span>
                        <p>{j.error || j.progress}</p>
                        {debugMode && (
                          <button
                            className="quiet"
                            onClick={() => setDebugJob(j.id)}
                          >
                            Inspect generation
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </section>
              <footer className="footer">
                <span>
                  <i /> Local-first. Yours to keep.
                </span>
                <span>Built for understanding, not just answers.</span>
              </footer>
            </>
          )}
        </main>
      )}
      {debugMode && (
        <section className="debug-launcher">
          <span className="tag">Debug mode</span>
          <label>
            Inspect a generation
            <select
              aria-label="Inspect a generation"
              value=""
              onChange={(e) => setDebugJob(e.target.value)}
            >
              <option value="">Choose a generation…</option>
              {jobs.map((j) => (
                <option value={j.id} key={j.id}>
                  {j.status} · {j.request.prompt}
                </option>
              ))}
            </select>
          </label>
          <button
            className="quiet"
            onClick={() => {
              setDebugMode(false);
              localStorage.setItem("openatlas-debug", "false");
            }}
          >
            Turn off debug mode
          </button>
        </section>
      )}
      {debugMode && debugJob && (
        <DebugInspector jobId={debugJob} onClose={() => setDebugJob(null)} />
      )}
      {showSettings && (
        <SettingsDialog
          settings={settings}
          debugMode={debugMode}
          onDebugChange={(enabled) => {
            setDebugMode(enabled);
            localStorage.setItem("openatlas-debug", String(enabled));
          }}
          onClose={() => setShowSettings(false)}
          onSaved={(saved) => {
            setSettings(saved);
            setShowSettings(false);
          }}
        />
      )}
      {auth && (
        <div className="modal-backdrop">
          <form
            className="modal"
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await api("/session", { token });
                setAuth(false);
                window.location.reload();
              } catch (e) {
                handle(e);
              }
            }}
          >
            <h2>Open your library</h2>
            <label>
              Host access token
              <input
                type="password"
                required
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
            </label>
            <button className="primary">Continue</button>
          </form>
        </div>
      )}
    </>
  );
}
