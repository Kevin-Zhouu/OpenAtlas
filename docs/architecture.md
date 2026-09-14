# Final architecture

```text
Browser :8000 ── FastAPI ── Repository (SQLite/WAL)
                    │            ↑ claims / progress / leases
                    │       Trusted runner (bounded thread pool)
                    │            │
                    │            ├── Demo: authored local source
                    │            └── DockerExecutor
                    │                 ├── disposable Codex workspace (no mounts)
                    │                 └── disposable trusted credential relay
                    │            │
                    │       Chromium validation (opaque-origin iframe)
                    │            │
                    └── ArtifactStore ← immutable local publication
```

The empty starting repository contained no existing AgentAdapter. `CodexAdapter` now owns the explicit skill-aware prompt and noninteractive CLI command. `DockerExecutor` owns the disposable execution lifecycle. `Runner` coordinates jobs through application-specific repository and artifact methods; it contains no SQL or Docker SDK objects. The deterministic demo creates authored files and goes through exactly the same validation, publication, metadata, progress, and reader flow. It intentionally does not run untrusted code or require Docker/inference.

`Repository` contains persistence operations, serialized requests, job leasing, and transactions. Migrations acquire an immediate SQLite transaction so simultaneous API/runner startup is safe, and foreign keys are enabled on every connection. Numbered SQL migrations are applied automatically, tracked in `schema_migrations`. IDs are UUIDs; metadata includes `workspace_id='local'`. Jobs snapshot their inputs. Revisions seed from a specific immutable source version; concurrent revisions produce independent versions and the last publication becomes latest. Versions are never overwritten. A future repository replacement (including CosmosDB) must preserve atomic claims, concurrency limits and atomic publication semantics; a connection-string swap is not sufficient. The HTTP API should continue using the repository's application operations.

`ArtifactStore` stores `library/<notebook-id>/<version-id>/{source,artifact,manifest.json,provenance.json,validation.json,preview.png}`. Files are staged and renamed before the database transaction publishes their metadata. A crash between rename and commit may leave an unreferenced directory, but never a published pointer to an unfinished directory. Such orphans are not served. No general data directory static mount exists. Future object storage can implement these small save/seed/read operations.

The trusted API serves the React bundle and metadata. `/notebooks/<id>` is the trusted reader shell; `/artifacts/<id>/<version>/<path>` serves only DB-published artifacts with path containment. The reader uses `sandbox="allow-scripts"` **without** `allow-same-origin`. Artifact responses independently enforce the sandbox via CSP, including direct navigation. Resource/connect CSP is restricted to that version's immutable directory. CORS permits opaque-origin module/asset reads. Forms, nested frames, storage, parent DOM access, and top-level navigation are not granted. The trusted app denies framing and cross-origin mutations and uses a host allowlist against DNS rebinding. No artifact messages are accepted by the trusted application.

Skills are standard read-only input snapshots. Discovery parses YAML with a safe loader; it never imports code or executes scripts. All optional skill state remains in job/version metadata. Staging copies only selected skills and core. Hash checks detect changes between selection and execution. The hash covers files and relative names, not timestamps. Unsupported links are rejected to prevent host file disclosure. Published artifacts do not reference installed skills.

The runner copies source and skills via tar streams over Docker exec into job-private tmpfs. Docker filesystem archive endpoints cannot reliably read/write tmpfs under a read-only root filesystem; this was reproduced during live testing. Exec streams preserve the read-only root boundary and an opt-in Docker regression test exercises the transfer. No host bind mounts are used. The container is non-root, read-only outside tmpfs, drops Linux capabilities, disables privilege escalation, and has bounded memory/CPU/PIDs and a deadline. The temporary environment can run builds freely because the outer Docker boundary is responsible for isolation. Its network namespace is shared only with its own trusted provider relay. The relay holds the API key and forwards only authenticated Responses requests to a fixed OpenAI URL; there are no public relay ports. A per-job relay token can spend inference quota during the job, so the generation timeout bounds lifetime, not monetary cost. Add spend limits at the provider for local deployments. Host administrators remain trusted.

The trusted validator never runs generated Python/npm/source. It intercepts browser requests, fulfills only files from that artifact, and embeds the entrypoint inside the same sandbox. Declarative interaction checks avoid executing agent-provided test scripts in the trusted runner. Checks must target visible real controls and assert visible feedback. Chromium errors, missing/external resources, phone-width overflow and broken assertions fail publication. Codex gets at most one repair attempt seeded with the collected source and validator feedback; no failed artifact is published. Rejected outputs are quarantined outside the served library for debugging. Validation is functional, not a security proof or a check of every claim; Chromium and Docker must remain patched. Future hostile multi-tenant hosting should move browser validation into an additional hardened execution boundary and restrict generation egress before deployment.

Progress is coarse but truthful: queued, preparing, coding/building/testing, collecting, validating, saving, ready/failed. Heartbeats renew a 60-second lease. Expired running jobs fail without auto-replaying paid work; queued jobs survive restart. A labelled-container janitor removes expired generation environments after interruption. A single bounded runner process is the documented local deployment. The concurrency claim is transactional so accidental second runners cannot exceed the stored global limit.

## Integration references consulted

- [Codex non-interactive mode](https://developers.openai.com/codex/noninteractive) and installed `codex exec --help` for headless execution and external sandbox flags.
- [Agent Skills specification](https://agentskills.io/specification) for portable `SKILL.md` metadata and folder conventions.
- Docker SDK installed method documentation for archive transfer, exec creation/inspection, resource constraints, and removal.
- [Ciechanowski's visual essays](https://ciechanow.ski/) as the user-provided teaching reference. The built-in guidance adopts integrated experiments and progressive explanation, without copying site content or assets.


Settings exposes a write-only credential API: reads return only configured/source status. `Credentials` owns atomic, permission-restricted local key storage and fallback environment/file lookup. API and runner share this abstraction and the private data volume; generated environments still receive only a per-job relay token. Local key storage is not encrypted. A future hosted credential vault can replace this class without changing the generation adapter. The model dropdown comes from `/api/models`; GPT-6 Astra is the default. Migration 002 upgrades the original default while preserving other saved model choices and historical job/version snapshots. Model availability is checked by the provider during generation, with failures shown in job history.

`DebugStore` is a small private diagnostics boundary backed by atomic JSON snapshots in the data volume. A trusted runner observer samples labelled generation containers independently of request handling, allowing existing running containers to be inspected. The executor captures final snapshots before cleanup. The API reads stored snapshots after checking the job exists and never calls Docker. Snapshot writes are synchronized across threads within the single trusted runner process; one runner process per local installation remains required. Fields are explicitly selected and known credentials redacted before persistence. A browser-local debug preference reveals per-job inspection and a polling viewer; output is rendered as text, never HTML. Storage is bounded per job, with no full log archive or automatic historical retention expiry in this version.

Publication checks evaluate control visibility before the action and feedback visibility afterward. Feedback can be revealed or inserted asynchronously; it cannot pass by matching hidden text. Failures include the check index, selectors and action so agent repair receives actionable details. The generation prompt explicitly declares the 1–30 publication-check limit.

A validation-only recovery is a new persisted job with `request.revalidate_job` referencing a failed job's retained artifact. It copies that artifact into a private worker workspace and follows ordinary browser validation and immutable publication without staging skills or invoking the agent. It retains the original provenance and Notebook identifier while preserving the original failed job and diagnostics. Failed rechecks do not trigger paid repairs. The always-available Jobs dropdown provides filtering and direct debug access independently of the browser's debug-toggle setting.

Learning-duration targets are ordinary request metadata (`reading_minutes`, integer 5–50). Submission supplies a default of 20 minutes, and revisions inherit their current version's target when omitted. The runner records `target_reading_minutes` in each immutable manifest. The Codex adapter converts the target into scope and prose-planning guidance, while its global creative brief requires topic-specific narrative, composition and interactions without enforcing a shared lesson template. No new persistence backend or migration is required because these fields live in existing JSON request/manifest records.

The trusted debug frontend normalizes Codex item events by container + item ID. Repeated starts/updates/completions replace one row, preserving task-start chronology; agent runs are ordered by start time. The activity feed follows the bottom until the user scrolls away, with a jump-to-latest control. Running indicators use observed job/container state, pause with polling, and respect reduced motion. Message Markdown is rendered through React with raw HTML skipped and image/link components replaced by inert text. Commands and raw logs are always plain text. No debug input or arbitrary execution endpoint is introduced.

### Same-Wi-Fi access

The host-side `scripts/lan_access.py` writes a private Compose override with the
host's RFC1918 IPv4 address, a separate port binding and a persisted owner token.
This keeps adapter discovery and Docker configuration outside FastAPI. The API
reads `OPENATLAS_LAN_URL` and provides authenticated phone-link metadata; the
React Settings view generates the QR locally with the bundled qrcode library.
The link fragment is consumed once and exchanged for the existing HttpOnly owner
session before loading application data. No tunnel, discovery daemon, account
provider or additional runtime service is introduced. Sandbox and artifact-serving
boundaries are unchanged. This supports trusted home networks over HTTP, not
public hosting or an individual-user authorization model.
