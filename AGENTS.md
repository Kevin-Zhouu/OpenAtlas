# Working on OpenAtlas

## Product and design intent

OpenAtlas is a local-first, open-source AI learning application. A user describes
what they want to learn; agents design and build an interactive **Notebook**, which
joins a persistent local library. A Notebook is a static website with retained
editable source and immutable published versions, not just generated prose.

Aim for the pleasure of exploring a well-designed interactive textbook or exhibit:
clear explanations, integrated illustrations, and 3d interactions that reveal how
something works. Avoid dense essays, repetitive cards, decorative controls, and
identical structures across subjects. Respect learner background, explicit requests,
and reading duration. Do not impose arbitrary counts of chapters, quizzes, or
experiments. Use substantial 3D where spatial exploration helps, and respect requests
for other representations. Creativity must remain compatible with factual accuracy.

## Current architecture and feature status

- FastAPI serves the trusted React/TypeScript frontend, APIs, and published artifacts
  through one user-facing application port (8000). No per-Notebook web servers.
- SQLite stores application state; filesystem storage retains source, artifacts,
  manifests, provenance, validation results, and private diagnostics.
- The trusted Python runner centrally orchestrates persisted jobs with bounded
  concurrency: **Plan → Build → Validate → Publish**. HTTP requests enqueue work.
- Planning is already implemented: the OpenAI Agents SDK runs in a disposable
  container and returns an editable Markdown build prompt. A separate disposable
  container runs real noninteractive Codex CLI to implement, build, and test it.
  The planner does not invoke Codex or Docker itself.
- The generation inspector queues learner steering for the next Codex turn before
  validation. Follow-up instructions persist for review and Continue. Validation can
  be stopped to retain an unvalidated draft preview; preview snapshots expose only
  dist assets with an opaque sandbox and never create a published version.
- Prompt-only runs, immutable prompt revisions, comparisons, builds from saved
  prompts, editable planner instructions/models, and stage inspection exist.
  Continue/Re-run reuse saved prompts when available; replanning is explicit.
- Standard Agent Skills are selectable generation inputs. Settings supports skill
  installation and file editing. Only selected skills and enabled core skills are
  staged; skill snapshots and provenance are retained separately from artifacts.
- Packaged golden design references are staged for both planner and builder,
  independently of skill selection. The planner's tools read text resources;
  reading notes is not evidence of viewing screenshots or researching a live site.
- Demo mode is explicit and deterministic, uses the job/publication architecture,
  and does not need inference. Never silently substitute demo for a real failure.
- Settings, provider profiles, failed-job recovery, diagnostics, and same-Wi-Fi
  phone access already exist. Preserve these workflows when adding features.

This file is orientation, not proof that an integration was tested. Inspect current
code and tests before changing behavior. Some older architecture/verification notes
describe earlier releases; do not treat their test counts or limitations as current.

## Code map

| Location | Responsibility |
| --- | --- |
| `openatlas/api.py`, `server.py` | API, trusted UI/artifact routes, server ingress |
| `openatlas/runner.py` | Trusted background orchestration and recovery |
| `openatlas/repository.py`, `migrations/` | Persistence, atomic claims, numbered SQL migrations |
| `openatlas/artifacts.py`, `reader.py` | Artifact storage/validation and sandboxed reader integration |
| `openatlas/planning.py`, `generation/planner.py` | Planner protocol and container-side SDK execution |
| `openatlas/agents.py`, `execution.py` | Codex instructions/command and disposable execution lifecycle |
| `openatlas/resources/planner-instructions.md` | Default editable planner creative instructions |
| `openatlas/resources/experience-quality.md` | Shared experience-quality guidance |
| `openatlas/skills.py`, `skill_editor.py`, `builtins/` | Standard skill discovery, authoring, built-in skills |
| `openatlas/references.py`, `resources/goldens/` | Portable reference catalogue, hashes, study evidence |
| `openatlas/credentials.py`, `subscription.py`, `phone.py` | Provider credentials, subscription integration, phone access |
| `openatlas/debug.py`, `trace_export.py` | Retained/redacted generation diagnostics |
| `frontend/src/`, `frontend/e2e/` | Trusted React UI and browser workflow tests |
| `generation/` | Generation image, planner, browser/build tooling and runtime resources |
| `tests/` | Backend, validation, planner, security, and opt-in container tests |

Paths abbreviated in a row are relative to that row's package directory.

## Boundaries to preserve

- The runner is trusted; generated code and skill contents are not. Generation
  containers must not receive the Docker socket, application database, complete
  data directory, other workspaces, or unrestricted host mounts.
- Keep credentials behind the existing credential/relay boundary. Never print or
  commit keys, auth files, `.env` values, private profile files, or unredacted Docker
  environment/inspection output. Never bake credentials into generated source/images.
- Serve only validated, database-published artifacts with path containment. A
  successful Notebook requires a renderable HTML entrypoint and browser validation
  of declared interactions. Never execute generated build/test scripts on the trusted
  host/runner as a shortcut; use the generation sandbox.
- Keep the reader iframe opaque with `sandbox="allow-scripts"` and no
  `allow-same-origin`. Preserve artifact CSP and trusted UI protections. The limited
  reader navigation bridge validates the sending iframe and bounded messages; do
  not turn it into arbitrary parent access or app command execution.
- Preserve immutable Notebook versions, prompts, provenance, and failed-job history.
  Revisions/continuations seed saved work; they do not overwrite published versions.
- Keep editable creative prompts separate from fixed runtime/security contracts.
  Preserve customized settings when updating defaults and historical job snapshots.
- Discovery/editor code may read skill files, but must not execute their scripts on
  the host. Published artifacts must work after original skills are removed.
- Keep portable application-specific boundaries around repository, artifact store,
  credentials, and execution. Future hosted accounts, CosmosDB, object storage, or
  remote runners are extension directions, not implemented backends. Do not add
  Redis, Kubernetes, cloud services, or generic frameworks without a concrete need.

## Development and verification

Use Python 3.12 recommended (3.9+ supported), Node 22+, and Docker for real generation.
See `README.md` for complete installation and platform-specific setup.

```sh
# Default local app and runner; persistent Compose library, explicit demo provider
docker compose up --build -d
# Build/rebuild the image used by new real generation containers
docker compose --profile build build generation-image

# Native setup, after creating/activating .venv
python -m pip install -r requirements.lock
python -m pip install -e '.[test]' --no-deps
python -m playwright install chromium
npm ci --prefix frontend
npm run build --prefix frontend
# Separate terminals, with the same environment
python -m uvicorn openatlas.api:app --host 127.0.0.1 --port 8000
python -m openatlas.runner

# Tests/build checks; use the activated virtual environment
python -m pytest -q
npm test --prefix frontend
npm run build --prefix frontend
# Requires a running test application; can create jobs/change settings
npm run test:e2e --prefix frontend
# Opt-in real Docker regression, built generation image required; no paid inference
OPENATLAS_DOCKER_TEST=1 python -m pytest tests/test_docker.py -q
```

The last environment-variable syntax is for POSIX shells; use PowerShell's `$env:`
equivalent on Windows. Native Colima users must set `DOCKER_HOST` to their actual
socket for the Python Docker SDK. Do not hard-code a developer's home directory.
Browser E2E accepts `OPENATLAS_TEST_URL`. Prefer an isolated test library for tests
that mutate application state. Native data defaults to `.data/`; Compose uses its
named `library` volume. Never run `docker compose down -v` against a user's library.

Rebuild the frontend to update the FastAPI-served UI. Rebuild application/generation
images when their respective code changes. Check for active jobs before restarting
the runner; avoid interrupting paid generations for unrelated UI changes. Preserve
existing launch/LAN overrides rather than replacing a configured deployment blindly.

Run checks appropriate to the change. For UI changes, inspect the running browser
at desktop and phone widths and exercise the affected controls. Compilation alone
does not verify appearance. Report tests actually executed and external prerequisites
that prevented verification; deterministic fixtures do not establish live model quality.

## Further context

- `README.md`: current setup, settings, planning, skills, retries, and operations.
- `docs/architecture.md`: storage/execution boundaries and architectural history.
- `docs/notebook-design.md`: teaching and Notebook design context.
- `docs/graphics-evaluation.md`: topic-transfer cases and visual/interaction review.
- `docs/lan-access.md`, `docs/remote-access.md`: desktop and phone ingress setup.
- `docs/verification.md`: historical executed checks, not a current test certificate.

The portable golden subset lives in `openatlas/resources/goldens/`; do not require
the original author's absolute dataset path. Respect evidence types and licensing.
Evaluate prompt specificity separately from built visual/functional quality, and
do not equate provisional reference scores with measured learning outcomes.

Keep this file updated when architecture or developer workflows change. Put detailed
feature proposals in `docs/` and clearly label planned versus implemented behavior.
Preserve unrelated working-tree changes and inspect current integration documentation
or CLI help before implementing unfamiliar provider/agent behavior.
