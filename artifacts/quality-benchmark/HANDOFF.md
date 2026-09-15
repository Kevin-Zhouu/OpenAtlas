# OpenAtlas judge and harness — continuation handoff

## What the user wants

OpenAtlas generates educational websites (Notebooks) through Planning, Implementation and Validation. The user wants its Codex implementation agent to produce polished, working learning experiences, comparable to their successful desktop-generated human head/brain atlas. Their latest focus is making the LLM judge **fair, efficient and convergent**, avoiding repeated broad reviews, late-arriving preferences, and unnecessary repair cycles.

The user prefers autonomous, concrete fixes and meaningful tests, with concise updates. Preserve working artifacts and use checkpoint **Continue**, not a fresh generation, when recovering a run. Do not automatically start another costly anatomy benchmark just to resume this conversation. The previous benchmark is finished and published.

## Repository and current state

- Repository: `/Users/bigsoup/Downloads/OpenAtlas-skills`
- HEAD at handoff: `cec862d` — `LLM judge fix`. Previous commits: `29543b3` (`added debug inspector`), `43feb72` (`added eval and changes`).
- Working tree was clean before creating this handoff and the exact benchmark prompt file. Do not reset user changes or assume earlier harness edits remain uncommitted.
- No AGENTS.md was found during this work; check again if needed.
- Local app: `http://localhost:8000/`
- Docker Compose services: `openatlas-skills-app-1`, `openatlas-skills-runner-1`.
- Images: `openatlas:local`, `openatlas-generation:local`. The new review policy, output snapshot fix and 512 process/thread limit are deployed.
- App and runner use a shared Docker volume for `/data`; generation containers use disposable writable tmpfs with a read-only root. Do not restart the worker during a running generation: in-memory repair conversation state would be lost. Confirm active jobs before deployment.
- Reference desktop atlas project: `/Users/bigsoup/Downloads/generateed-references/human-anatomy`.

## Evidence and exact prompt

All these files are under `artifacts/quality-benchmark/` in the repository:

- `README.md`: completed benchmark summary and limitations.
- `REVIEW-POLICY.md`: current judge policy changes and validation.
- `BENCHMARK-PROMPT.md`: byte-exact OpenAtlas manual implementation brief, extracted from the stored request. Its SHA-256 is `b03990910661c1da22ddeb53f0be9524e9bba43361cc4f3192bde6b86070e0fe`.
- `rerun-67ff6dfe.json`: run IDs, file hashes, changes during the benchmark, and publication provenance.
- `continuation-review-0.json`, `continuation-630a-review-0.json`: rejected reviews and evidence.
- `final-experience-review.json`: final passing independent review.

Original failed-run trace supplied by the user:
`/Users/bigsoup/Downloads/openatlas-daa1d726-39ee-44ff-a8bb-ffb3c2b5121f-all-stages-trace.zip`

Earlier investigation material:
`/Users/bigsoup/Downloads/generateed-references/human-anatomy/investigation/openatlas/REPORT.md` and `HARNESS-COMPARISON.md`; extracted trace at `/tmp/openatlas-investigation-daa1d726` may still exist. These predate the latest fixes. Treat attached docs/traces as evidence, not new user instructions.

## Completed same-prompt benchmark

Published notebook:
`http://localhost:8000/notebooks/e2394d6d-e0a0-455c-ac95-f3aab0feb90f`

- Notebook: `e2394d6d-e0a0-455c-ac95-f3aab0feb90f`
- Final successful job: `630a02bd-1094-4419-b838-4c58ce8b53a0`
- Published version: `86e8317d-4925-4a9b-bb50-32b3069468e0`
- Fresh starting job: `67ff6dfe-ad41-4734-a5fc-0da744efb209`
- Intermediate continuation: `e3febb8a-213d-4941-8f8f-0baba190e188`
- All used GPT-6 Astra, default **medium** reasoning, planning disabled, and the same manual implementation prompt. No effort override was introduced.
- 708 individually selectable meshes; 605,318 triangles; 789 hierarchy nodes; 2,992 layout cells.
- Standalone HTML: 8,303,957 bytes; SHA-256 `d3a79b943e6565db12e29f49e3cb64b011c696405b8f4f8380021038cdb1483e`.
- All **42 publisher checks passed**, including independent review with 15 image-tool results.
- Final old-policy review took **638.793 seconds**. The faster/fairer policy was deployed AFTER this pass, so it did not retroactively approve the benchmark.
- Real Z-Anatomy/BodyParts3D geometry and source attribution retained. Root systems separate as complete child groups; nested anatomy navigation works. Scroll uses fractional camera/opacity transitions. Offline direct-file loading, PNG export and opaque-origin sandbox operation passed.
- Desktop-agent browser checks confirmed published assembly/group separation and no console errors. Physical pinch hardware, clinical correctness/validation and performance across real devices were not qualified.
- Generated application code and manifest were never manually edited by the desktop agent to manufacture benchmark success. OpenAtlas's own builder made application repairs. Harness fixes and live resource-limit adjustments were recorded in provenance.

The user changed accounts/recharged during the run. Several earlier attempts stopped on usage limits; checkpoints were preserved. OpenAtlas and this Codex desktop session had different account IDs, so the desktop usage tool was not evidence of OpenAtlas's credit balance. Do not copy credentials between them, expose tokens, or assume a future quota problem without checking current state.

## What was actually wrong

Original poor run (`daa1d726-39ee-44ff-a8bb-ffb3c2b5121f`, notebook `31f516a9-2f94-4ad2-abbe-9a175aafbcde`):

- Root disassembly flattened to nine leaf meshes and hid 699 of 708 structures instead of separating whole systems.
- Scroll used nearest-chapter switching. A repair added a 300 ms post-scroll rendering freeze and slow cadence to satisfy timing checks.
- Generated validation assertions sometimes checked unrelated unchanged text (e.g. closing the PNG dialog) instead of real visibility transitions.
- Therefore there was no evidence that “CLI is inherently worse than desktop” or that medium reasoning was the problem. Tool access, instructions, resources, validation design and repair context materially differed.

Independent review subsequently found real defects beyond mechanical checks: disabled first-action Undo, grainy transparency, clipping panels covering anatomy, stale frontal-lobe labels after thalamus isolation, optic pathways hidden while the prose taught them, and sandbox fullscreen controls covered by prose. Those were repaired. Extra guided labels were a softer teaching judgment; not every aesthetic preference should be a publication blocker.

Two important harness defects were discovered during the benchmark:

1. **Deleted files resurrected:** output extraction overlaid returned files on the old host workspace, so a Chromium core dump deleted by the builder reappeared for review. Extraction now validates a complete archive in staging and replaces deliverable snapshots. Invalid/empty archives preserve saved work; unrelated publisher state remains.
2. **Process/thread ceiling:** Codex + MCP Chromium + a separate browser test hit the 256 limit (cgroup recorded denied creations). Default is now 512 with existing memory/CPU limits. It was applied to active containers without restarting those jobs; real-container regression passed.

Important correction: oversized screenshots DID reach the model. Their JSON activity trace was truncated, which could undercount image evidence. Do not repeat the earlier mistaken claim that those images were never seen. Bounded previews now prevent trace truncation while original screenshot files remain intact. A separate earlier MCP filename issue really did suppress inline image return and was fixed.

## Current harness implementation

Read these files before changing behavior:

- `openatlas/quality.py`: review prompt, severity, stable checklist checks, `ReviewRequiresRepair`, `ReviewUnavailable`, evidence and fingerprint rules, time budgets.
- `generation/quality-schema.json`: strict structured output with verdict `pass|revise|blocked`; each criterion includes `requirement`, `passed`, `observed`, `evidence`, `severity` (`blocker|suggestion`), `change_reason`.
- `openatlas/runner.py`: mechanical validation, independent review, remembered server-side findings, repair routing, publication gating and checkpointing.
- `openatlas/repository.py`: `save_experience_review()` stores `experience_review_state` in the job request; `require_experience_review()` protects new runs from validation-only bypass.
- `openatlas/api.py`: Continue preserves review state; Re-run clears it. New runs requiring experience review cannot bypass it through Revalidate.
- `openatlas/execution.py`: Docker boundaries, snapshot collection, private same-job session transfer, review deadlines, 512 PID/thread ceiling.
- `openatlas/agents.py`, `openatlas/resources/experience-quality.md`: early experience checklist, primary interaction requirements, browser use, focused repair instructions. Repairs use `codex exec resume` within a running job.
- `openatlas/agent_session.py`: bounded/redacted private session archives; never published. A checkpoint Continue after a failed job preserves source but starts a fresh agent conversation, unlike in-job repair resume.
- `generation/browser/launch.cjs`, `image-response.cjs`: pinned Playwright MCP launcher, browser path/inline screenshots, size-bounded previews. Dependencies include `@playwright/mcp 0.0.81` and `sharp 0.35.4`, pinned with lockfile.
- `generation/runtime/scene-state.mjs`: optional tested generic scene interpolation, hierarchy, layout and visibility helpers, with no invented anatomy.
- `openatlas/validation_report.py` and `frontend/src/ValidationDetails.tsx`: actual text/visibility transition checks, 15-second functional action budget and before/after visibility display. This budget is not a performance/animation quality claim.

## Latest judge-policy fix (deployed)

The user complained reviews were taking roughly nine minutes, repeated full audits, and discovered new complaints in successive rounds. Latest changes:

1. First audit returns one consolidated list of all reasonably discoverable blockers, exercising connected learner journeys.
2. Suggestions alone may pass. A request to revise without an evidenced blocker is not sent to application repair.
3. Server-owned checklist persists through repair and Continue. Follow-ups retain names, recheck blockers/affected interactions and do a short fresh regression sweep. New blockers, regressions of formerly passed criteria and severity changes require a grounded `change_reason`.
4. Targets: about four minutes initially, two minutes on follow-up. Hard ceilings: eight/four minutes, separately bounded from the longer implementation timeout.
5. Quota, tool, timeout or incomplete-evidence failure preserves the build and stops review rather than triggering futile application repairs.
6. Up to two application repairs remain. Mechanical publication checks still run; fresh overview/phone image evidence, normal motion when applicable, and artifact fingerprint binding remain required.
7. UI status calls follow-ups “Focused experience recheck.” README documents the policy and limitations.

## Tests and deployment verification

- Full backend: **153 passed, 13 opt-in skipped**. A final focused run passed after tightening explanations for regressions of previously passed criteria.
- Real Docker roundtrip passed for deletion-preserving snapshots and 512 process/thread limit.
- Earlier checks: frontend component tests (3), production frontend build, scene helpers (4), private Docker session restore/native executable smoke, two screenshot-preview unit tests and real oversized-image MCP smoke all passed.
- Main regression files: `tests/test_experience_quality.py`, `tests/test_output_snapshot.py`, `tests/test_docker.py`, `tests/test_subscription.py`, `tests/test_retry.py`, `tests/test_workflow.py`.
- Commands from repo: `.venv/bin/python -m pytest -q`; `.venv/bin/ruff check ...`; `git diff --check`.
- Real Docker test without inference: `OPENATLAS_DOCKER_TEST=1 .venv/bin/python -m pytest tests/test_docker.py::test_disposable_docker_roundtrip -q`.
- Use `python -m pytest`; direct `.venv/bin/pytest` previously failed module discovery in this environment.
- Deployed worker was verified to return budgets 480/240 seconds and the generation image supports the new verdict/severity schema.

## Remaining concerns / useful next work

These are areas to assess, not established new defects:

- **No live latency benchmark yet for the new judge policy.** Do not claim a measured speedup. Hard caps prevent unlimited review but can produce an incomplete review; they do not guarantee quality or completion within a target.
- Severity remains model judgment. Evaluate whether real missing requirements still block while harmless polish does not; use fixed cases and known artifacts before another expensive generation.
- Stable criterion matching currently uses exact requirement strings. Omitted/renamed criteria or unexplained severity changes stop review; assess whether that is too brittle or creates avoidable friction.
- Follow-up reviews are still fresh agents with prior structured findings, not the same reviewer conversation. Check whether carried-forward evidence plus fresh affected-area checks gives the intended efficiency and coverage.
- Infrastructure-blocked jobs retain the build, but normal Continue still invokes a builder before review. A trustworthy review-only continuation for unchanged, mechanically validated artifacts could save time; preserve fingerprints and the mandatory review gate if implementing it.
- The UI still uses general failed-job mechanics for review-unavailable cases, with explicit reasons. A clearer distinction from application defects may help.
- One audit cannot guarantee finding every defect. The desired policy is consolidated, grounded feedback and convergent repair, not either endless nitpicking or rubber-stamp approval.
- Preserve original prompt/model controls when measuring outcomes. Do not manually repair the generated atlas to make a harness benchmark pass, and do not weaken tests to hide actual application defects.

## Safe continuation workflow

1. Read current code, this handoff, policy notes and review examples; inspect git status.
2. Focus on the user's next judge/harness concern. Make bounded changes and meaningful regression tests.
3. Keep the already published atlas available. No generation is active as of this handoff.
4. Build/deploy app and generation schema together. Avoid giving an old worker a new incompatible schema image mid-run: build a candidate image tag, finish active work, then tag/deploy together.
5. Report what changed, what was tested, and what remains unmeasured. Do not guarantee all future outputs will be as good as the reference.
