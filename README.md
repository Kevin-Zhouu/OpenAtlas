# OpenAtlas

A local-first, open-source learning application. Ask a question, generate an interactive **Notebook**, and keep its source and immutable published versions in your own library. Deep green, quiet typography, one application port.

## Quick start: Docker Compose

Install Docker Desktop (macOS/Windows, using Linux containers) or Docker Engine with Compose (Linux). From this directory:

```sh
docker compose up --build -d
```

Open **http://localhost:8000**. The default is **Demo**: an explicitly labelled, authored caching lesson with interactive controls. Any prompt works, but demo content does not adapt to the topic. No API key or generation image is needed for demo mode. The app and one trusted runner share a named volume; stopping/restarting Compose preserves Notebooks and job history. `docker compose down -v` deletes that volume: do not use it if you want to keep your library.

On Homebrew installations where the plugin isn't linked, use `docker-compose` in place of `docker compose`. For Colima, start `colima start --cpu 4 --memory 6`. Compose mounts the daemon-side `/var/run/docker.sock`; keep that default. The native runner uses the host-forwarded socket path as documented below.

## Private VPS installation (preview)

For a dedicated Linux VPS, see the [guided private VPS installer](docs/vps-installation.md)
and [security review](docs/security-review.md). It adds `openatlas start`,
`shutdown`, `doctor`, token rotation, and optional boot startup using private
Tailscale HTTPS. This is a preview deployment flow, not approval for direct public
Internet exposure with only a secret URL.

## Real Codex generation

```sh
docker compose --profile build build generation-image
cp .env.example .env
```

Open **Settings** in the web UI, choose **Codex** as the generation provider, and select **Add a new provider…** under **API provider profile**. Enter a name, API base URL, and API key. For OpenAI, use `https://api.openai.com/v1`. Enter a supported Codex model ID or choose a suggestion; set the planner model in the **Planner** tab. **GPT-6 Astra** (`gpt-6-astra`) is the default. Save settings, enter a learning request, and press **Generate Notebook**. Model availability depends on the selected API provider; saving a profile validates its format, not account access. Demo mode never uses inference.

Settings remembers named provider profiles, including multiple keys for the same API URL. Select a saved profile and **Save settings** to switch; the other profiles and keys remain available. Leave the password field blank when editing to keep that profile's saved key. **Delete provider profile** removes only that profile; deleting the active one restores **Host configuration**. Keys are never returned to the browser. Profiles persist across restarts in `private/inference-profiles.json` inside the data volume, outside SQLite and Notebook artifacts. Existing `private/openai-key` installations appear as an OpenAI profile and migrate on the first edit. The file uses restricted permissions, not encryption; protect the host and volume backups.

Third-party providers must support the **Responses API**, streaming, tool calls, and Bearer API-key authentication. Enter the base path (for example, `https://api.example.com/gateway/v1`), without `/responses`, credentials, query parameters, or a fragment. Chat Completions-only endpoints are not supported. HTTP endpoints are accepted for local/LAN servers; use HTTPS for remote providers. With Docker Desktop, a server on this computer is reachable as `http://host.docker.internal:PORT/v1`, not `localhost` (the server must listen on an interface Docker can reach). Profile switching applies when the next job starts, including retries. Each running job keeps one key/URL pair through planning, building and repairs. Models remain separate settings, so update both model IDs when the new provider uses different names.

Codex CLI is pinned in `generation/Dockerfile`. It runs `codex exec` non-interactively inside a fresh non-root Docker container, with approval bypass only because Docker is the external sandbox. It can edit source, build, run Chromium/Playwright, and repair failures. It is instructed explicitly to read the selected skills. This is not a single model response saved as HTML. A failed publication check gives Codex up to two repair attempts using the existing source, original implementation conversation, and concrete validation feedback. Final generation errors are persisted and displayed in **Generation history**; real failures never fall back to demo.

### Use a ChatGPT subscription

In **Settings → Inference authentication**, choose **ChatGPT subscription**, then **Sign in with ChatGPT**. Open the official sign-in link, enter the one-time code, and finish signing in. You may need to enable device-code login in ChatGPT's security settings. OpenAtlas shows the signed-in account automatically. **Save settings** to use this mode for new jobs; retries and builds from saved plans also use the currently selected mode.

Subscription mode uses Codex's managed ChatGPT login and your plan's Codex allowance. It is not general OpenAI API credit. The Agents SDK planner retains its resource tools and validation, with a custom model adapter that asks the signed-in Codex CLI for structured tool requests and final text. The builder uses the same login directly. API-key mode continues to use the standard Responses client. No paid API fallback occurs when subscription login fails or usage is exhausted.

One account is shared by this library. Subscription jobs run serially so token refreshes cannot overwrite each other; API-key jobs retain the configured concurrency. **Sign out of ChatGPT** clears the local session, cancels pending sign-in, and stops active subscription inference. Saved API provider profiles are retained. The runner must be running for sign-in to work.

The private session is stored in `private/subscription.json` (mode 0600) outside SQLite and artifacts. Only the trusted runner transfers the Codex auth cache into a job container's temporary home, retains refreshed credentials, and removes the container afterward. Subscription mode therefore gives the disposable Codex container its own copy of the login cache; run only trusted jobs. Known token values are redacted from diagnostics and rejected in collected artifacts. The Settings API returns account status, never tokens. This uses the pinned Codex app-server device-login protocol; the upstream app-server interface is experimental.

References: [Codex authentication](https://learn.chatgpt.com/docs/auth) and [Codex app-server account login](https://learn.chatgpt.com/docs/app-server).

The trusted API and runner can access the provider key. A separate disposable credential relay forwards job-authorized requests to the selected provider's Responses endpoint. The generation container gets a temporary relay token, not your provider key. Neither image contains secrets. The relay is not published on a host port. Docker administrators can inspect the trusted relay environment, just as they can inspect other local secrets.

Alternatively, configure `OPENAI_API_KEY` in the private `.env` file and restart Compose, or set `OPENATLAS_OPENAI_KEY_FILE=/absolute/private/keyfile` for native API and runner processes. Never commit credentials. The **Host configuration** profile uses the private key file before the environment variable, with `OPENATLAS_API_BASE_URL` (default `https://api.openai.com/v1`) as its base URL. A selected saved profile uses its own key and URL. No key file is mounted into the generation container.

## Native development (macOS, Linux, Windows)

Use Python **3.12 recommended** (3.9+ supported), Node **22+**, and a Docker engine for real generation. Demo generation runs locally and does not require Docker.

```sh
python3 -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.lock
python -m pip install -e '.[test]' --no-deps
python -m playwright install chromium
# On Linux install browser OS dependencies too:
# python -m playwright install --with-deps chromium
cd frontend
npm ci
npm run build
cd ..
python -m uvicorn openatlas.api:app --host 127.0.0.1 --port 8000
```

In a second terminal with the same virtual environment activated:

```sh
python -m openatlas.runner
```

On Colima, set `DOCKER_HOST=unix:///absolute/path/to/.colima/default/docker.sock` for the native runner; the Docker Python SDK does not automatically use CLI contexts. Windows Docker Desktop generally exposes its standard named pipe to the SDK. `docker build -t openatlas-generation:local -f generation/Dockerfile .` builds the real generation image.

The trusted frontend is built by Vite and served by FastAPI on the same port as everything else. During development, rebuild after frontend changes. Native data defaults to `.data/`; Compose data is in its named `library` volume. Configuration is read at process startup; restart both processes after changing environment variables.

## Skills and additional guidance

Drop a standard Agent Skills folder into `skills/` (or the directory configured by `OPENATLAS_SKILLS` for native development / `OPENATLAS_SKILLS_DIR` for Compose):

```text
skills/
  anatomy-3d/
    SKILL.md
    references/
    scripts/
    assets/
```

Its `SKILL.md` begins with standard YAML frontmatter:

```yaml
---
name: anatomy-3d
description: Teach anatomy with interactive spatial explanations.
metadata:
  version: "1.0.0"
---
```

Put the skill instructions after the frontmatter. Folder and name must match, use lowercase letters/numbers/hyphens, and be at most 64 characters. Linked files, special files, and skills over 20 MB are rejected. Malformed skills appear disabled with a reason. Refresh the page after adding skills. No marketplace, remote install mechanism, or custom plugin format is involved.

Expand **Generation skills & extra guidance** under the prompt, select capabilities, and optionally add instructions such as “Make the heart rotatable and animate blood flow.” You can always generate without touching this selector. `openatlas-core` and `blender` are included whenever skills are enabled; built-in `visual-explainer` and `3d-explorer` are optional standard skills. Only core and selected folders are copied into that job. No skill script executes on the trusted host. A queued selection records a content hash; if a folder changes before execution, the job fails clearly rather than silently using different content.

Each immutable Notebook version records skill identifiers, names, optional versions, and SHA-256 hashes. **Revise Notebook** seeds a new workspace from retained source and defaults to the preceding version's selected skills and generation provider. You can change them. Removed skills must be deselected or reinstalled before revising. Already published versions have no runtime dependence on skills. The version selector keeps earlier versions readable; the stable `/notebooks/<id>` URL opens the latest version on a new visit. A reader already open on an older version stays there until the learner selects another version.

## Configuration

| Variable | Default / use |
| --- | --- |
| `OPENATLAS_DATA` | Native `.data`; Compose `/data` |
| `OPENATLAS_SKILLS` | Native `skills`; Compose `/skills` |
| `OPENATLAS_GENERATION_IMAGE` | `openatlas-generation:local` |
| `OPENATLAS_JOB_TIMEOUT` | 7200 seconds for implementation by default; reviews have separate ceilings of 8 minutes initially and 4 minutes for follow-ups |
| `OPENAI_API_KEY` | Fallback provider credential for trusted API and runner |
| `OPENATLAS_OPENAI_KEY_FILE` | Native API/runner alternative private key file |
| `OPENATLAS_ALLOWED_HOSTS` | `localhost,127.0.0.1`; comma-separated hostnames/IPs |
| `OPENATLAS_ACCESS_TOKEN` | Optional shared local UI/API access token |

Provider, model, and concurrency (1–8, default 2) are persisted in SQLite through Settings. Changing concurrency affects new claims; running jobs finish. Each job snapshots provider/model/instructions/skills at submission.

To use from another device on a **trusted local network**, configure `OPENATLAS_BIND=0.0.0.0` in Compose and add the host's LAN IP to `OPENATLAS_ALLOWED_HOSTS`. Set `OPENATLAS_ACCESS_TOKEN` to a private shared token. Native development uses `--host 0.0.0.0`. Visit `http://<host-ip>:8000`. The UI is responsive. This is not an Internet-facing multi-user service: HTTP is unencrypted, and artifact URLs are bearer-like local read links. Do not port-forward it publicly. A hosted deployment requires proper authentication, per-workspace authorization, TLS, quotas, and execution network hardening.

## Validation and tests

```sh
python -m pytest -q
cd frontend
npm test
npm run build
npx playwright install chromium
# With FastAPI and the runner running (uses the app's demo library):
npm run test:e2e
```

To also run the real Docker transfer/isolation regression (no inference), set `OPENATLAS_DOCKER_TEST=1` when running pytest; the generation image must be built. On Colima also set `DOCKER_HOST` as above.

Backend tests cover publication, concurrency, restart persistence, revisions, provenance, malformed/changed skills, path traversal, expired leases, CSRF, and failure behavior. Browser validation is real Chromium, not mocked. Frontend unit tests cover submission, optional skills/instructions, settings, and errors. End-to-end tests submit through the UI, wait for publication, test interactions and browser isolation, reload, revise, and check a phone viewport. E2E tests create labelled demo Notebooks in the running library; use a separate `OPENATLAS_DATA` directory for an isolated test run.

A successful artifact must have a built HTML entrypoint, meaningful rendered content, and passing declarative interaction checks. The validator loads it in the same opaque-origin sandbox as the reader, blocks outside requests, rejects missing resources and JavaScript errors, and exercises manifest-declared controls and visible outcomes. These are functional checks, not a proof of educational correctness or exhaustive coverage. Generated source is never executed by the trusted publisher. See [architecture](docs/architecture.md) and [verification notes](docs/verification.md).

## Local operations and limitations

- One trusted runner process handles up to eight simultaneous jobs with a thread pool. SQLite atomically enforces the configured global claim limit. No permanent worker per generation.
- Progress and job status persist. Interrupted running jobs expire their lease and fail clearly; queued jobs remain queued. Submit again after a failure. There is no cancellation UI or automatic retry of failed jobs. Publication validation permits one in-job Codex repair attempt.
- Real generation uses two disposable containers per job (agent and trusted credential relay); neither runs after publication. The runner cleans expired labelled containers after interruption when Docker becomes available.
- Built artifacts and source have a 100 MB output cap; selected skills have a 20 MB per-folder cap; generated workspaces use bounded tmpfs and containers have CPU, memory, process, and time limits.
- Docker is the execution boundary. Generated containers have no host mounts, database, Docker socket, application environment, other job workspaces, or real provider key. The runner is deliberately trusted and has Docker daemon authority. Outbound Internet access is currently available for Codex/package installation; this is not a hardened hostile multi-tenant execution service.
- Publication is local only. SQLite plus filesystem backups are sufficient; stop the runner before copying the data directory to obtain a consistent backup. The library retains source, artifacts, manifest, skill provenance, desktop/phone screenshots, and validation report for every version. Outputs rejected by publication are quarantined under `failed/<job-id>/<attempt>/` for local debugging and are never served.
- No accounts, syncing, deletion UI, full-text search, automatic skill upgrades, or cloud backends yet. CosmosDB can replace the small repository boundary later; no CosmosDB dependency is introduced now.

## License

MIT. See [LICENSE](LICENSE).

## Debug mode and live Codex activity

Open **Settings → Debug mode**. This switch takes effect immediately and is remembered in that browser. Each active job and generation-history entry has **Inspect generation**; the debug selector also opens any job, including from the Notebook reader.

The inspector refreshes every two seconds and shows persisted job progress, model/provider, recent Codex events (commands, messages, file changes and errors), raw agent output, container IDs/images/status, configured CPU/memory limits, process executable names, and container stdout/stderr. Pause updates to read a snapshot. Codex runs through Docker exec, so its actual agent output is separate from container stdout.

The trusted runner captures diagnostics every three seconds and before removing new generation containers. Diagnostics are collected even when the browser toggle is off so a finished generation can be inspected later. It retains the newest 128 KB of agent output and 32 KB of container logs per container, for at most 16 containers per job; this is a rolling snapshot, not a complete event archive. A large/truncated JSON event may appear only in the raw log. Demo jobs show job progress without containers. Jobs completed before this feature have no historical container snapshots.

Snapshots live privately under `debug/` in the data volume, survive restarts, and are never published as Notebook artifacts. Environment variables, host mounts and full process command lines are excluded. Known container credentials and common key/bearer patterns are redacted. Logs can still include prompts and generated source, so treat diagnostics as private local data. The inspector shares the application's host access-token protection. Debug mode is a display preference, not an authorization boundary; no Docker socket or arbitrary container commands are exposed to the browser/API.

The **Jobs** dropdown in the header is always available. Filter by Failed, Running, Queued, or Completed; **Debug failed job** opens the inspector directly, even when debug mode was previously off. Original failures remain in job history after recovery.

Publication checks run sequentially and support feedback that becomes visible or is created after an action. Controls must be visible before acting, feedback must be visible afterward, and explicit expected text must match. Without expected text, feedback must be newly revealed or its visible text must change. Alternatively, `expect_visible: false` directly tests closing/removing a previously visible panel, and `expect_visible: true` tests revealing one. Visibility checks must observe a real transition; already satisfied states cannot pass. Text assertions cannot target hidden outcomes. Functional actions have a 15-second budget for Docker software rendering; this does not establish animation quality, which is reviewed separately. Manifests accept 1–30 checks; additional agent tests belong in the retained source.

For a legacy failed job with retained artifacts that predates required experience review, `POST /api/jobs/<job-id>/revalidate` queues a validation-only recovery using the latest quarantined artifact. It runs the current publication checks without invoking Codex or changing the original job. A successful recheck publishes to the same Notebook URL with the original skill provenance. Failed rechecks remain unpublished and do not silently spend inference on another repair.

## Choose the depth and reading experience

The **Time to explore** slider selects an approximate **5–50 minute** reading-and-interaction target (20 minutes by default). Short requests focus on one idea; longer sessions develop foundations, worked examples, deeper explanations and practice. The target is saved with each job and Notebook version, and revisions inherit it. Demo mode retains its fixed authored lesson and labels that limitation.

Generation guidance asks for a fresh, topic-specific creative direction rather than one repeated layout. It prioritizes readable neutral text, purposeful supporting colors, story-driven illustrations and a small collapsed Contents control instead of a permanent sidebar. See [Notebook design guidance](docs/notebook-design.md) for the rationale and limitations.

The agent inspector presents activity in chronological order, with the latest tasks at the bottom. Start/update/completion events for the same Codex item appear as one evolving row. Running tasks show animated indicators; completed jobs and paused views stop them, and reduced-motion preferences are respected. The feed follows new activity while you are at the bottom. Scroll upward to read older entries and use **Jump to latest** to resume following. Commands, output and file changes have distinct layouts; container details and raw logs remain available below the feed. Agent messages support safe Markdown formatting; embedded HTML, image loading and active links are disabled. There is no chat input or command execution control.

## Access from your phone on the same Wi-Fi

After the normal Compose build/install, open **OpenAtlas.command** (macOS) or
**OpenAtlas.cmd** (Windows), or run `python3 scripts/start.py` on Linux.
The desktop UI opens at localhost without a token.

In **Settings → Open on your phone**, click **Enable phone access** and scan the QR.
Disable access or reset the link from the same panel. No signup, phone app, or
per-phone terminal setup is needed. Keep the host awake on the same trusted Wi-Fi.
See [phone access](docs/lan-access.md) for startup and network details.

Access from outside your home remains optional via [Tailscale Serve](docs/remote-access.md).

### Codex model metadata

The generation image pins Codex CLI **0.154.0**, including GPT-6 Astra metadata.
After pulling code changes, rebuild it with
`docker compose --profile build build generation-image`. New generation containers
use the rebuilt image; already-running generations keep their original CLI.
OpenAtlas always passes the selected model explicitly with `-m` and forwards it
unchanged. A “fallback metadata” warning in older jobs refers to local CLI model
capabilities, not proof that another model answered.

In job debug → relay container logs, new generations record `requested_model` and
`response_model` (when supplied in the API stream). These are model identifiers
only; prompts, answers, and credentials are not logged by this diagnostic.

### Resume a stopped stage or re-run a generation

Open **Jobs → Failed → Resume** to automatically continue from the stopped stage.
The menu shows one Resume button and explains which stage it will use.
Explicit stage choices are available inside the generation inspector:

- **Resume planning** reruns an interrupted planner using the original request.
- **Resume implementation** starts a coding session with the saved source and prompt.
- **Resume validation** checks the latest saved build without implementation or
  automatic repairs. Required independent experience review still runs and may
  use inference credits. If checks fail, the draft stays saved for inspection or
  an explicit implementation resume.
- **Resume publishing** saves an already validated artifact. This is offered only
  when trusted validation evidence matches the saved artifact and current CSP.
  Older jobs without this evidence must resume validation first.

Each action creates a new attempt on the same Notebook and preserves earlier
attempts. Checks restart from the beginning of their stage, not the interrupted
browser operation or model conversation. The stopped stage is retained across
cancellation, failure and expired generation leases.

**Continue editing** (the legacy Continue action) explicitly invokes the builder.
**Re-run** starts over with the original request and saved prompt. These use the
current credentials and may incur inference charges. An active retry blocks
duplicate submissions for the same failed attempt. Installed skills must still
match the recorded selection. Re-run of a failed revision starts from that
revision's original base.

Partial `source/`, `dist/` and manifest files are collected privately before normal
failure cleanup, including credit failures. Dependencies, agent credentials,
agent history and skill folders are excluded. Unsafe or oversized snapshots are
rejected. Checkpoints are never public artifacts. Continue is disabled when no
safe source checkpoint or retained validation output exists—especially older
failures whose containers were already deleted. Sudden host/daemon termination
can prevent the final checkpoint; continuous crash-proof saving is not implemented.

### Customize the generation prompt and skills

Open **Settings → Generation prompt** to edit the teaching and design instructions,
restore the shipped default, or preview the full Codex prompt. `{{reading_minutes}}`
is replaced with the learner's selected duration. **Save settings** applies the
change to future jobs. Each submitted job snapshots the effective teaching prompt;
retrying that job retains its original prompt. The learner request, skill selection,
build contract and sandbox/publication rules are supplied separately and remain enforced.

Open **Settings → Skills** to browse installed and built-in skills. Select a skill
and file to edit its UTF-8 text, then **Save file**. You can create a new standard
skill or add files such as `references/notes.md` and `scripts/example.py`. Unsaved
file edits must be saved or discarded before switching files or closing Settings.
Malformed SKILL.md files can be repaired here; they cannot be selected for generation.
Concurrent edits are checked before overwriting a file.

To install, upload a ZIP containing exactly one skill folder, for example
`visual-guide/SKILL.md` alongside its resources. Archives are limited to 20 MB
uncompressed and 2,000 entries. Links, special files and paths outside that folder
are rejected. Text editing is limited to 500 KB per file; binary assets may be
included in the ZIP and are listed but not text-editable. Installation never runs
skill scripts. Existing skill names are not overwritten by ZIP installation.

Local skills stay in the configured skills directory. Built-in edits are stored in
its `.builtin-overrides` subdirectory and survive image upgrades. The app needs
write access to the skills directory (the default Compose setup provides it); the
runner still mounts it read-only. Changes affect future selections. If a queued
job's selected skill changes, its fingerprint check fails rather than silently using
different instructions; submit a new generation to use the changed skill. Published
Notebook versions remain independent of installed skills.

Teaching Notebooks may bundle supporting UTF-8 source files (for example C# project
files, shell scripts and Markdown instructions) alongside their web artifact.
OpenAtlas serves these as plain text with `nosniff`; it does not execute them.
Compiled binaries remain blocked, and publication still requires a built HTML
entrypoint plus passing browser interaction checks. Failed jobs retained before
this support was added can be revalidated without model inference.

In **Generation inspector → Generation details**, inspect the saved learning request,
custom instructions, model, duration, revision/retry links, selected skill versions
and fingerprints, and complete saved job metadata. New Codex invocations capture the
assembled prompt, CLI arguments and execution context before launch; repair attempts
are listed separately. Known credentials are redacted and container environments are
never exposed. Older jobs without a capture show a clearly labeled reconstruction
using saved inputs and the current prompt adapter, not a claimed historical transcript.

Publication interaction checks support `click`, `fill`, `select`, and `range`.
Use `select` for a native dropdown and provide the option's `value`, not its label.
For compatibility with older generated manifests, `fill` on a `<select>` also
selects its option. Both paths use browser selection events and retain the same
visible-feedback assertions; missing options or broken interactions still fail.

### Topic-specific planning

New Codex generations run **Plan → Build → Validate → Publish** in the persisted
background runner. Planning uses the OpenAI Agents SDK in its own disposable
container, followed by a separate Codex container. Both use the existing
job-scoped credential relay and share the configured generation concurrency limit.
Demo generation remains an explicitly selected, inference-free provider.

Rebuild the generation image after upgrading:

```sh
docker build -f generation/Dockerfile -t openatlas-generation:local .
```

In **Settings → Planner**, choose the planner model and edit or restore its default
instructions. Builder model selection stays in General. The legacy generation
prompt is retained for historical jobs; new builds use the selected creative brief
plus OpenAtlas's fixed artifact, sandbox and validation requirements.

For experimentation, select **Generate prompt only** in the generation options.
Open **Jobs → Inspect job → Prompts** to select, edit, copy, compare or regenerate
candidates. Save edits as a new revision, then choose **Build from this prompt**.
This queues only the builder. Re-run and Continue also reuse a saved prompt when
one exists. Regeneration intentionally runs planning again with current planner
settings, retaining earlier candidates and the original inputs and skill snapshots.

Planning attempts, immutable Markdown prompt revisions, configuration, errors and
current stages are stored in SQLite. Published version manifests include
`planning_attempt_id` and `prompt_revision_id`. Private, hash-verified selected skill
snapshots live in the application's `skill-inputs` directory; they are copied only
to disposable workspaces and excluded from published source and artifacts.
The inspector retains per-stage container details, exact invocation instructions,
observable agent messages, tool/resource reads and bounded live logs. No hidden
reasoning or SDK cloud traces are requested. The planner has read-only skill and golden-reference text tools;
external research is explicitly assigned to Codex.

Cancel an active job from its inspector. Cancelled and lease-expired jobs enter a
recoverable failed state. Planning errors never trigger a demo or legacy-prompt
fallback. A builder failure leaves its selected prompt available for another build.

Planner API additions: `GET /api/jobs/{id}/plans`,
`POST /api/jobs/{id}/replan`, `POST /api/prompts/{id}/edit`,
`POST /api/prompts/{id}/build`, and `POST /api/jobs/{id}/cancel`.

The ordinary tests use planner doubles and make no paid inference calls. To test
actual Agents SDK streaming, tool dispatch, resource confinement and container
cleanup against a deterministic local HTTP provider:

```sh
OPENATLAS_DOCKER_TEST=1 .venv/bin/python -m pytest tests/test_docker.py -q
```

This verifies the real SDK execution path without claiming to evaluate live model
creativity. Evaluate topic quality separately with your configured API account;
compare requests such as LLM inference, human anatomy and Chernobyl, checking that
controls teach different mechanisms and explicit requirements survive planning.

### Blender authoring

New generations with skills enabled include both OpenAtlas core and the Blender
core skill. The planner reads the same saved skill snapshot that is later supplied
to Codex. Blender is an available authoring tool; it does not force 3D into lessons.
Disabling skills also disables the Blender MCP registration. Existing jobs keep
their saved skill selections.

The default generation image includes Debian Blender 3.4, a pinned
[Blender MCP](https://github.com/ahujasid/blender-mcp) server and matching addon
(revision `5f8ddaf6e987c4aa0c3467fcc548838b28f64477`). Codex receives a stdio MCP
configuration for scene/object inspection, Python modeling and viewport screenshots.
Each MCP session starts Blender on a private Xvfb display with CPU rendering.
No desktop session, host display, GPU, extra port or host volume is required.
Telemetry is disabled; external asset-generation services are not configured.
The planner does not start Blender. Container concurrency, limits and cleanup
continue to be managed by the trusted runner.

Keep editable `.blend` files in source and export local GLB/images for the static
website. The reader never needs Blender. The core skill includes export and browser
verification guidance. Blender startup logs are in `/tmp/blender-output.log` inside
the disposable builder. Rebuild the generation image and app after updating:

```sh
docker compose --profile build build generation-image
docker compose build app
docker compose up -d --no-build app runner
OPENATLAS_DOCKER_TEST=1 .venv/bin/python -m pytest tests/test_blender.py tests/test_docker.py
```

The Blender integration test uses the real MCP protocol to inspect and edit a
scene, save native source, and export GLB under the production container limits.
It also checks Codex accepts the MCP configuration. No inference credits are used.


### Graphics planning and golden references

The planner's [default brief instructions](openatlas/resources/planner-instructions.md)
make substantial interactive 3D the default for subjects that benefit from spatial
exploration, with an educational rationale for 2D or simpler alternatives. Explicit
learner requirements take precedence. Complexity is revealed progressively through
inspection, component separation and linked explanations.

A portable study subset of `OpenAtlas-dataset/gold_websites/goldens` is checked in at
`openatlas/resources/goldens`. Its `CATALOG.json` lists all 15 reference records,
evidence types and file hashes. It includes principles, interaction notes,
provenance, evaluations, reviews, factual caveats and available contact sheets.
It excludes source snapshots, videos and full-resolution captures. Links in the
original notes may point to omitted evidence; neither agent may claim to have
inspected that evidence. Scores include provisional demo reviews and are not
certified learning outcomes or a license to reuse artwork.

The worker verifies and stages this package into `/workspace/references/goldens`
for **both** planning and building, even with no skills selected or when building an
edited saved brief. The normal Docker input archive transfers these files; there
is no dataset host bind mount or required absolute host path. The application
Docker image and Python package include the study subset. Missing or changed files
are omitted and identified in the staged catalog and planning inputs.

The planner discovers references with `list_resources`, reads records with
`read_resource`, and must read the catalog when supplied. Its saved Markdown brief
must identify inspected records, adopted qualities, topic relevance, evidence limits
and concrete acceptance checks. OpenAtlas appends an actual text-read ledger with
paths, offsets and character counts; it does not certify the model's prose claims.
The planner cannot view images or browse live sites. The builder can inspect the
packaged contact sheets and must capture **and view** its own representative renders,
test scene outcomes, and record comparison results and gaps in `source/DESIGN.md`.
These requirements supplement, rather than replace, sandbox publication checks.

Existing settings using the previous exact stock planner instructions pick up the
new default. Customized instructions and historical planning snapshots remain intact;
use Settings → Planner → restore default to replace a customization intentionally.
Rebuild the application and generation images when deploying these changes.

See [graphics evaluation cases](docs/graphics-evaluation.md) for topic-transfer and
visual-review criteria. Infrastructure tests use fixtures, not paid inference; a
passing test suite does not certify the quality of a generated exhibit.

### Generation time limit

**Settings → Generation time limit (minutes)** controls each planning, generation, and repair attempt independently. The default is **120 minutes** (previously 30 minutes), configurable from 1 to 1440 minutes (24 hours). Saved settings persist across restarts. New jobs, retries, and builds from saved plans use the current setting; running attempts keep their original limit. After a timeout, increase the limit and use **Continue** when partial output is available, or **Re-run**. `OPENATLAS_JOB_TIMEOUT` sets the fallback in seconds when no saved setting exists; Compose passes it to both app and runner.

### Validation details

Open **Generation inspector → Validating → Activity & logs** to inspect each validation round, including rounds before a repair. Expand a check to see its expected condition, action and selectors, observed feedback, duration, and failure or browser diagnostics. Results are saved as validation runs, so completed checks remain available if a later check fails. The validator stops at the first blocking failure; remaining checks are marked **Not run**. These automated checks cover packaged files, sandboxed rendering, declared interactions, phone overflow, and browser/resource errors—not every interaction or factual claim. Older generations show the summaries that were retained at the time; individual historical results cannot be reconstructed.

### Download generation traces

In **Generation inspector**, use **Download all stage traces** for one ZIP covering the selected attempt, or the stage-specific download for Planning, Implementing, Validating, or Publishing. Exports include saved job inputs, captured prompts and invocations, timestamped stage events, validation rounds, and emitted agent logs. If a build reuses an earlier plan, that plan's retained history is included with its source job ID. ZIP contents use JSON and plain-text logs for inspection without OpenAtlas.

The runner saves running agent logs about every 30 seconds and captures them before container cleanup, independently of the live debug toggle. Each agent log is capped at 10 MiB; metadata identifies complete, in-progress, truncated, and snapshot-only history. A recent log tail is included for incomplete archives. Historical jobs can only export what was previously retained. Known credentials are redacted; authentication caches and raw Docker environment settings are never included. Downloads of live jobs are snapshots of activity captured so far.

### Experience review and continuous 3D work

Real Codex builds now receive common experience-quality guidance even when a manual build prompt replaces the teaching prompt. A pinned Playwright MCP browser returns screenshots directly to the model. Large previews are compressed to keep complete image evidence within the CLI activity-trace limit; the original screenshot files are preserved. For real-time hierarchical scenes, `/opt/openatlas-runtime/scene-state.mjs` provides tested continuous-timeline, group-coverage, layout and visibility helpers that the builder can copy into its editable source.

After mechanical browser validation, a fresh Codex reviewer inspects the built artifact against the original brief. It must provide actual image-tool evidence, overview/phone captures, per-requirement observations and normal-motion inspection where applicable. The reviewer cannot approve a modified artifact. Reports are retained in `source/review/experience-review.json` and the validation details. The first reviewer returns one consolidated audit. Findings distinguish evidenced blockers from optional suggestions; suggestions alone do not trigger repair. The server retains that checklist across repairs and Continue. Follow-up reviews reproduce blockers, inspect affected interactions, and perform a short regression sweep instead of repeating a full discovery audit. New blockers or severity changes require a grounded explanation. Reviews target about four minutes initially and two minutes on follow-up, with hard ceilings of eight and four minutes respectively; these are budgets, not latency guarantees. Up to two application repairs are allowed and resume the implementation conversation. Tool, quota, timeout or incomplete-evidence failures stop review and retain the build for Continue instead of triggering an application repair. Mechanical publication checks still rerun, and actual image/motion evidence and artifact fingerprint checks remain mandatory. Demo and legacy artifact-only revalidation retain their existing mechanical checks. New Codex runs persist a review requirement; their Revalidate endpoint and runner reject validation-only recovery. Use Continue to preserve the build and prior review checklist. Re-run starts a fresh build and review checklist.

The implementation's Codex session history is held privately in memory for the running job and transferred only between that job's disposable containers. Only bounded regular JSONL session files are accepted, known credentials are redacted, and history is discarded when the job ends. Auth/config files are never included in this transfer or published. Interrupted-job continuation still uses the existing source checkpoint workflow.

Generation tool resources default to 4 GiB memory and 4 CPU cores. The disposable, non-root workspace explicitly allows execution so native npm build helpers (such as esbuild) work; Docker otherwise defaults tmpfs to noexec. The relay and temporary home remain non-executable. Override `OPENATLAS_GENERATION_MEMORY` and `OPENATLAS_GENERATION_CPUS` in the runner environment/Compose configuration for your machine. These limits concern browser/build tools; they do not change the model's reasoning effort. Graphics still depend on the available renderer. Build the pinned browser image with `docker compose --profile build build generation-image`, then rebuild/restart the app and runner. No reasoning-effort override is introduced.

Developer checks: `python -m pytest`, `node --test generation/runtime/scene-state.test.mjs`; after `npm ci --prefix generation/browser`, run `node --test generation/browser/image-response.test.cjs`. The browser MCP smoke fixture in `tests/fixtures/browser_mcp_smoke.py` runs against the generation image without model inference. It verifies that a screenshot is returned as image content, not merely saved to a path.

Returned workspaces are collected as validated snapshots, so deleted source/build files stay deleted. Invalid archives leave saved work intact. Generation containers allow 512 processes/threads to accommodate Codex plus visual and scripted Chromium checks within the existing memory/CPU limits.

### Steering and draft previews

In **Inspect generation → Implementing**, send follow-up instructions to Codex.
Messages are retained with queued/applying/applied status and run as the next turn
in the same implementation session, before validation. The independent reviewer
also receives the updated requirements. This uses `codex exec resume`; it does not
interrupt an in-progress CLI turn ([Codex documentation](https://learn.chatgpt.com/docs/non-interactive-mode)).

In **Validating**, **Preview current build** opens the current immutable draft in
a sandboxed iframe. **Skip checks & preview** stops the remaining checks (after
the current browser operation), retains the draft, and does not publish it. Use
**Continue** from the stopped attempt to complete validation and publication.
Draft previews remain separate from the published library and expose only web assets.
Each random preview URL grants read access to that snapshot, allowing assets to
load inside an opaque frame without cookies; preview discovery requires app access.

If phone settings show no enable button or QR after restarting Compose, restore
the saved LAN configuration with `python3 scripts/lan_access.py enable`. A plain
`docker compose up` can replace the LAN configuration with localhost-only ingress.
When rebuilding an existing LAN installation, preserve its override:

```sh
docker compose -f compose.yaml -f .lan/compose.json up -d --no-build app
```

Rebuild the application image after updating this code. Restart the runner only
after active generations finish; it retains Codex sessions in memory.

### Permanent deletion

Use **Delete** beside a Notebook, or **Delete permanently** in Jobs. Confirm the
Notebook and all related attempts: versions, prompts, steering, source, previews,
failed builds, logs and diagnostics are removed together. Selecting a job has the
same Notebook-wide scope because attempts can copy earlier sensitive inputs.

Access is revoked as soon as deletion is queued. The running worker stops affected
generations and drains active writers before purging files and containers. The UI
shows deletion pending until cleanup finishes; the runner must be running. SQLite
uses secure deletion, compaction and WAL truncation. Deletion requests survive a
restart and cleanup retries after failures. Job workspaces are scoped beneath
`data/workspaces` so abandoned temporary copies can also be removed.

Installed skills, shared skill-input caches and provider settings remain separate
from Notebook content. Downloaded/exported files, other devices’ existing copies,
backups and inference-provider retention cannot be erased by this local action.
Published responses now use `no-store`; deletion asks the current browser to clear
its HTTP cache.

Activity no longer rolls over after 60 items or a 128 KiB tail. Complete retained
events stay in chronological order across polls and separate agent runs, including
validation review. Each run has a 10 MiB log bound, displayed when reached.
