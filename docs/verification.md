# Verification record

Tested on 14 September 2026 (Australia/Melbourne). This is a record of executed checks, not a list of assumed capabilities.

## Environment

- macOS Apple Silicon; native Python 3.9.6, Node 24.14.1.
- Colima Linux ARM64 engine, Docker server 29.5.2; Compose 5.5.1.
- Application image: Python 3.12, locked Python dependencies, Chromium installed by Playwright 1.60.0.
- Generation image: Node 22, Codex CLI 0.114.0, Playwright 1.58.2 / Chromium.
- Trusted UI: React 19 + TypeScript + Vite; browser E2E uses Playwright 1.58.2.

## Automated results

| Check actually run | Final result |
| --- | --- |
| Native `OPENATLAS_DOCKER_TEST=1 python -m pytest -q` with Colima Docker socket | **15 passed**; includes a real disposable Docker source-edit/build/transfer/isolation/cleanup test without inference |
| Backend suite inside the Linux application image, network disabled, test source mounted read-only | **14 passed, 1 skipped**; Docker-in-Docker test intentionally skipped because this test container has no Docker socket |
| `npm test` | **3 passed** |
| `npm run build` | TypeScript and Vite production build passed |
| `npm run test:e2e` against the final Compose deployment | **2 passed** |
| `ruff check openatlas tests generation` | Passed |
| Application and generation Docker image builds | Both built successfully |
| `docker compose config --quiet` | Passed |
| Project and native library scan for full OpenAI project-key patterns | Zero matching files |

The native Python 3.9 run emits urllib3's LibreSSL warning from Apple's system Python; the Linux Python 3.12 run does not. Python 3.12 is recommended for development. Node printed only a non-failing terminal color-environment warning during browser tests.

Backend coverage includes concurrent atomic claims, simultaneous migrations, persisted publication and restart, immutable revisions, inherited skills and provider, skill hashes, malformed frontmatter, removed/changed skills, symlink rejection, unsafe archives, missing HTML, broken interactions, stale leases, one bounded publication repair, no real-to-demo failure fallback, host/CSRF boundaries, optional access-token authentication, and unpublished output protection.

Browser E2E covers UI submission, persisted background completion, automatic library appearance, sandboxed reader, real visible interactions, inability to access parent DOM or localStorage from generated content, reload, revision inheritance, immutable versions, and 390-pixel mobile layout without horizontal overflow.

## Live Codex checks (paid inference was actually exercised)

A real noninteractive Codex generation produced a binary-search Notebook using `openatlas-core` and `visual-explainer`. Codex command events confirmed skill reading and project command execution. The result retained editable HTML source, a Python build script, README, and Playwright tests, alongside a built HTML artifact and manifest. The publisher ran six declared interactions in Chromium and saved desktop/phone previews.

Manual review found an off-by-one in the first quiz. A **real Codex revision**, seeded from the stored source, corrected the inclusive-bound worst-case formula to `floor(log2(n)) + 1`, added an exact-bound exploration, and improved the reading layout. Seven publication checks passed, including incorrect-answer feedback and the correct **11 comparisons for 1,024 items**. The revision inherited the same skill provenance and retained version 1. This is also evidence that browser functionality checks do not guarantee factual correctness; teaching content still benefits from review.

The locally running example is `/notebooks/8b1da0b6-6200-4d77-8228-a722cfd04156`. Its two immutable versions are `dc604613-80f0-4925-b3d4-7bba9809facd` and `c94c3df1-4fde-480b-918e-1efb33e2a073`. These are development-library records, not seed data required by the repository.

Earlier live attempts exposed Docker tmpfs archive behavior and an invalid agent entrypoint. Those attempts were marked failed and never published. The filesystem transfer now uses exec-based tar streams, with a real Docker regression test. The prompt now makes the relative entrypoint contract explicit, and one bounded in-job repair handles publisher feedback. Failed output can be quarantined privately for debugging.

The supplied credential was entered into a private terminal prompt and held in process memory for testing. It was not written into source, `.env`, SQLite, generated files, or images. The test process was stopped and all job containers were removed. The running Compose setup is left in **Demo** mode without a saved API key; configure your own runner credential before using Codex there.

## Compose, persistence, and visual checks

- Started both final services through Compose, with only `127.0.0.1:8000` published.
- Copied the stopped native development library into the initially empty persistent Compose volume, preserving the real example.
- Submitted two demo jobs to the live API and observed **both persisted states as running simultaneously**, then both succeeded.
- Ran browser E2E against the Compose deployment.
- Executed `docker compose restart` and verified the real Notebook, both immutable versions, both concurrent jobs, served HTML, and retained source remained accessible.
- Verified no labelled generation containers remained after completion.
- Inspected actual app and Notebook screenshots and accessibility trees in the browser, including phone-width layout. Exercised the real step-through simulation manually.

## Not verified / remaining limits

- Native Windows execution and native Linux development were not run. Linux container execution was tested; Windows dependency markers are included. Docker Desktop on those hosts is documented but was not available for a host-specific test.
- Phone layout was tested with a browser viewport, not a physical phone over LAN.
- No exhaustive factual, accessibility, visual-quality, or interaction-coverage guarantee is claimed. The manifest is agent-authored and checks only declared behavior.
- No cloud deployment, CosmosDB backend, multi-user authorization, accounts, sync, cancellation UI, spend quotas, or hardened multi-tenant execution network was implemented. The repository, artifact-store, credentials, and execution boundaries are the intended extension points.
- Generation egress remains available for model calls and build dependencies. Local Docker/application administrators are trusted. The local HTTP/access-token model is not suitable for public Internet deployment.

## Settings update — 14 September 2026

Implemented write-only API-key save/replace/remove in web Settings, persistent private credential storage shared by API and runner, and a curated model dropdown defaulting to GPT-6 Astra. Migration 002 upgrades the old default. Verified 18 backend tests passed (the opt-in Docker test skipped in that run), then explicitly ran the Docker roundtrip test: 1 passed. Six frontend unit tests passed, and the TypeScript/Vite production build and Ruff checks passed. Visually inspected the running Compose Settings form. The browser mobile check exposed a long historical error-path overflow; added error text wrapping. No paid GPT-6 Astra inference was run for this settings update; provider account availability remains a live integration check.

After rebuilding and restarting Compose with the wrapping fix, all 3 Playwright browser tests passed, including generation/publication/revision, mobile composition, and mobile Settings. Existing provider settings are restored after the workflow test.

## Generation debug inspector — 14 September 2026

Added a browser-local debug toggle, per-job inspector, two-second UI polling, three-second trusted runner observation, safe container/process metadata, recent Codex event rendering, separate raw agent/container logs, pause/resume, and private bounded retained snapshots. Inspected the actual running Astra/vLLM generation in the browser without interrupting its existing worker. For this live upgrade, the observer was started inside the existing trusted runner; fresh runner starts automatically launch it. The current worker was intentionally kept alive to preserve its in-flight generation.

Executed the full backend suite: 20 passed, 1 optional Docker skip. Executed the opt-in Docker roundtrip separately: 1 passed, including final diagnostic snapshots for both removed containers. Executed frontend unit tests: 9 passed. Executed browser workflow tests: 4 passed, including mobile debug persistence/inspection. Production TypeScript/Vite build and Ruff checks passed. Logs are bounded rolling snapshots, not a complete historical transcript; previously completed jobs cannot recover already-deleted container logs.

## Expandable feedback fix, recovery, and Jobs dropdown — 14 September 2026

Reproduced the vLLM publication failure at `#kv-math-toggle`: the control was visible but `#kv-math-content` was correctly hidden before clicking. Changed validation to require feedback visibility after interaction; added tests for revealed, newly inserted and unchanged feedback, hidden controls, and hidden feedback. Added explicit 1–30 manifest-check guidance and actionable check errors. Added queued validation-only recovery with no inference, preserving original failure history, Notebook identity, and skill provenance.

The retained vLLM artifact passed all 30 checks and published through recovery job `fd436fbd-2de7-4e35-b0c2-e95209eb6ae9` at `/notebooks/8070b204-363b-40e7-abc2-b1e672f055bd`. Independently opened that published reader in Chromium and verified the KV math section changes from hidden to visible with the expected text. Its source was reused unchanged, without a new model call.

Verified the always-available Jobs dropdown visually and tested filtering failures/direct debug access on mobile. Final checks: 27 backend tests passed, 1 opt-in Docker test skipped; 10 frontend unit tests passed; all 5 Playwright workflow tests passed; production build and Ruff passed. Updated existing tests to expect the more informative ValueError and to distinguish the skills disclosure from the new Jobs disclosure. Rebuilt and restarted both Compose services; recovered Notebook survived restart.

## Global creative direction and reading-time controls — 14 September 2026

Reviewed the user-provided TACACS+ over TLS source and live reference UI, then stopped its temporary preview server. Updated the global Codex generation prompt to require a topic-specific design rationale, varied composition/illustration/interaction approaches, readable neutral text with semantic supporting colors, compact collapsed Contents navigation, and scope matched to a requested duration. The examples are inspiration rather than a course template; no reference assets are required at generation time.

Added a keyboard-accessible 5–50 minute slider (default 20), strict API bounds, persisted job targets, version metadata and revision inheritance. Demo length remains explicitly fixed. Inspected the actual running 50-minute UI. Final tests: 30 backend passed, 1 optional Docker skipped; 10 frontend passed; all 5 Playwright tests passed, including duration submission and inherited revision duration. Production build and Ruff passed. Fixed mobile header overflow with simultaneous active/failed job badges discovered during these tests.

Before the user's clarification emphasizing future Notebook generation, a focused vLLM visual revision was submitted as job `0c696dc5-e1e5-4ae4-bcca-2475d959ee03`. It was still running when the global prompt/UI work completed; no claim of that revision's final visual quality or publication is made here. The global generation changes are deployed and apply to future jobs. Creative variety and reading-time fit remain agent quality goals, not hard guarantees or model-weight fine-tuning.

## Agent activity feed redesign — 14 September 2026

Replaced the numbered event list with a chronological task/message feed, latest activity at the bottom. Item IDs merge repeated Codex starts/updates/completions; commands have expandable command/output details, file changes have compact file rows, plans have completion counts and task indicators, and messages use safe Markdown without active links, images or raw HTML. Running task/job indicators animate; paused/completed views stop them and reduced motion disables animation. Container metadata and raw logs remain in a collapsed diagnostics section.

Verified scroll-following at the bottom, reading older entries without forced movement, Jump to latest, item completion removing the spinner, pause/resume, and no text-input control. Final results: 15 frontend unit tests passed; all 6 Playwright tests passed (including a controlled live-update stream and the full generation/revision workflow); TypeScript/Vite production build passed. Inspected a real retained job in the in-app browser and reviewed desktop/mobile screenshots of the controlled running-job fixture. Production dependency audit found zero vulnerabilities. Rebuilt and restarted the app service; the runner and active generations were left uninterrupted. No backend code was changed or backend suite rerun for this UI update.

### Notification UX

Generation failures no longer create banners above the main interface. The bell
opens an inbox with failure context and an Inspect job action. Historical failures
load quietly; newly observed failures and request errors show one eight-second
popup. Repeated polling does not repeat the same failure. Read markers are stored
in this browser; job history remains persisted on the server. Request-error notices
last for the current page session. Revalidated failures leave the notification
inbox while remaining accessible in Jobs.

Notification coverage includes historical/new failures, popup expiry, repeated
request errors, read-state persistence, recovered jobs, Escape dismissal, direct
inspection, and phone layouts down to 320px.
