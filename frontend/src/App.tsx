import { pairFromFragment } from "./pairing";
import { ReaderNavigation } from "./ReaderNavigation";
import { useEffect, useState, useRef } from "react";
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
  const [readerCollapsed, setReaderCollapsed] = useState(false);
  const readerFrame = useRef<HTMLIFrameElement>(null);
  const [readerMenuOpen, setReaderMenuOpen] = useState(false);
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setReaderMenuOpen(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);
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
      setAuth(false);
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
    async function reconnect() {
      try {
        await pairFromFragment();
        if (!active) return;
        await refresh();
        api<Skill[]>("/skills").then(setSkills).catch(handle);
        api<Settings>("/settings").then(setSettings).catch(handle);
      } catch (e) { if (active) { handle(e); setAuth(true); } }
    }
    reconnect();
    const timer = setInterval(async () => {
      try { await pairFromFragment(); if (active) await refresh(); }
      catch { if (active) setAuth(true); }
    }, 1800);
    // Safari may restore the old home page (including its modal state) from
    // the back/forward cache. Recheck the current cookie instead of keeping it.
    window.addEventListener("pageshow", reconnect);
    window.addEventListener("hashchange", reconnect);
    window.addEventListener("focus", reconnect);
    return () => {
      active = false; clearInterval(timer);
      window.removeEventListener("pageshow", reconnect);
      window.removeEventListener("hashchange", reconnect);
      window.removeEventListener("focus", reconnect);
    };
  }, []);
  const generationProvider = revising
    ? reader?.versions?.find((v) => v.id === reader?.latest_version)
        ?.provider || settings.provider
    : settings.provider;
  const [promptOnly, setPromptOnly] = useState(false);
  const [background, setBackground] = useState("");
  async function generate(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const created = await api<Job>(
        revising ? "/notebooks/" + notebookId + "/revisions" : "/jobs",
        {
          prompt,
          skills: skillsEnabled ? selected : [],
          skills_enabled: skillsEnabled,
          instructions,
          prompt_only: promptOnly && generationProvider === "codex",
          learner_background: background,
          provider: generationProvider,
          reading_minutes: readingMinutes,
        },
      );
      setDebugJob(created.id);
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
  const notebookJobs = jobs.filter((j, i) => !jobs.slice(0, i).some(previous => previous.notebook_id === j.notebook_id));
  const active = notebookJobs.filter(
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
              Turn off to exclude all skills, including OpenAtlas core and Blender, for this
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
        <label>Learner background <span>Optional</span><textarea value={background} onChange={e => setBackground(e.target.value)} rows={2}/></label>
        {generationProvider === "codex" && <label><input type="checkbox" checked={promptOnly} onChange={e => setPromptOnly(e.target.checked)}/>Generate prompt only · inspect and edit before building</label>}
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
            : "Enter a topic or question…"
        }
        rows={3}
      />
      <div className="composer-bottom">
        <span className="hint">
          {generationProvider === "demo"
            ? "Demo mode · No API key needed"
            : ""}
        </span>
        <button className="primary" disabled={busy || prompt.trim().length < 3}>
          {busy
            ? "Adding to your queue…"
            : revising
              ? "Create revision"
              : promptOnly && generationProvider === "codex" ? "Generate prompt only" : "Generate Notebook"}{" "}
          <Arrow />
        </button>
      </div>
      <details className="generation-preferences">
      <summary>Customize <span>{readingMinutes} min</span></summary>
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
      </details>
    </form>
  );
  const jobControls = <>
        <JobsDropdown
          jobs={jobs}
          onRetry={async (id, mode) => {
            await api(`/jobs/${encodeURIComponent(id)}/retry`, { mode });
            await refresh();
          }}
          onInspect={(id) => {
            setDebugJob(id);
          }}
        />
        <Notifications
          jobs={jobs}
          ready={jobsReady}
          error={error}
          onInspect={(id) => {
            setDebugJob(id);
          }}
        />
  </>;
  return (
    <>
      {reader && <>
        {readerMenuOpen && <button className="reader-shade" aria-label="Close Notebook menu" onClick={() => setReaderMenuOpen(false)} />}
        <ReaderNavigation frame={readerFrame} version={version} menuOpen={readerMenuOpen} onToggle={() => setReaderMenuOpen(!readerMenuOpen)} onCollapse={setReaderCollapsed}>{jobControls}</ReaderNavigation>
      </>}
      <header id="reader-controls" className={"topbar " + (reader ? "reader-bar " + (readerMenuOpen ? "reader-menu-open" : "") : "")}>
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
        {(!reader || readerCollapsed) && jobControls}
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
            <button className="quiet" onClick={() => { setReaderMenuOpen(false); beginRevision(); }}>
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
            ref={readerFrame}
            onLoad={() => readerFrame.current?.contentWindow?.postMessage({type: "openatlas:outline-request"}, "*")}
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
                .entrypoint || "index.html") + "?reader=1"
            }
          />
        </>
      ) : (
        <main className="home">
          <section className="intro">
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
            {revising && <p>Describe the change. Your current version stays in your library.</p>}
          </section>
          {form}
          {revising && (
            <button className="quiet" onClick={() => setRevising(false)}>
              Cancel revision
            </button>
          )}
          {!revising && (
            <>
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
                {notebooks.map((n) => (
                  <a
                    className="notebook-row"
                    href={"/notebooks/" + n.id}
                    key={n.id}
                  >
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
                    {notebookJobs.map((j) => (
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

            </>
          )}
        </main>
      )}
      {debugJob && (
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
          onClose={() => {setShowSettings(false); api<Skill[]>("/skills").then(setSkills).catch(handle);}}
          onSaved={(saved) => {
            setSettings(saved);
            setShowSettings(false);
            api<Skill[]>("/skills").then(setSkills).catch(handle);
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
            <h2>Reconnect your phone</h2>
            <p>On your computer, open Settings → Open on your phone and scan the QR code again. You don’t need to type a token.</p>
            <button type="button" className="primary" onClick={refresh}>Check connection again</button>
            <details><summary>Advanced: enter an access token</summary>
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
            </details>
          </form>
        </div>
      )}
    </>
  );
}
