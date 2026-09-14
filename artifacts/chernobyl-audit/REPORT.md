# Why the two Chernobyl Atlas builds differ

Investigated 14–15 September 2026. This is a comparison of two particular runs, not a benchmark of Codex Desktop against Codex CLI. No OpenAtlas application code or settings were changed during this investigation; this directory contains the audit and copies of the evidence.

## Finding

Both runs used the model identifier `gpt-6-astra`. The main observable differences are the effective assignment, active guidance, scene decomposition, research completion, and quality criteria. There is no evidence that the CLI is inherently less capable or that a different underlying model was silently substituted.

The OpenAtlas result is a functioning, styled educational notebook. It is less detailed and less independently inspectable as a 3D exhibit. Those are specific implementation differences rather than a blanket failure of design or testing.

## Evidence examined

- The original Desktop task history and saved rollout metadata; its generated `app/scene.ts`, `app/atlas.tsx`, CSS, build/export scripts, and browser inspection history.
- Both supplied attachments. The pasted agent log starts mid-command and is incomplete.
- The live notebook and its exact published version, copied to `openatlas-version/`.
- The generation debug record, exact captured CLI invocation, effective prompt, response-model verification, publication manifest and validation results.
- Current OpenAtlas prompt assembly, execution, relay, diagnostic retention and publisher code.
- Immutable core skill snapshot with SHA `e1c1742db21ac0691aebd71e9306e5a4ad08084f7a5a179fcbcb04e4a78163ac`.

OpenAtlas notebook: `4ff70f1f-51a3-41d8-bd5c-4665b1f78f99`.
Version: `f4e554af-cb43-4a07-a469-9b14ed7dbdb9`.
Job: `f15a31c0-72b0-47a6-a0d0-4b1dea08c6fb`.

`effective-builder-prompt.txt` preserves the actual prompt, rather than reconstructing it from today's settings. `evidence-summary.json` records the relevant model, invocation and skill metadata. `job-debug.json` is the full private debug response.

## How the Desktop exhibit was made

The implementation is conventional procedural Three.js. No Blender tools, model marketplaces, image generation, imported CAD model, photogrammetry, or additional agents were used.

### Stack

- Three.js: geometry, materials, lights, camera, clipping, animation.
- OrbitControls: orbit, pan, touch controls, damping.
- React + TypeScript: UI state and scene lifecycle.
- Existing Shadcn/Base UI tabs, sliders and switches, with custom CSS; Lucide icons.
- Sites/Vinext/Vite starter and build workflow.
- esbuild and Tailwind compilation for a single HTML export containing the runtime and styles.
- Web search and opened Chornobyl NPP/IAEA public references.
- Browser screenshots and real control interactions, followed by code revisions and production/type checks.
- Sites hosting for delivery; hosting itself did not generate the geometry.

### Why the 3D reads as detailed

Repeated small geometry does much of the work: facade ribs, window bays, roof bands, lattice braces, drum end rings, turbine ribs, channel caps, and individual stacked graphite bricks. A carefully chosen plant silhouette and consistent material colors make this repetition legible.

Boxes represent buildings and bricks. Cylinders represent channels, drums and machinery. A beam helper points a thin cylinder from endpoint A to endpoint B, producing chimney braces. `CatmullRomCurve3` and `TubeGeometry` generate pipes. There are no photographic textures or custom shaders.

A dark background, subdued grid, hemisphere fill, warm directional light and cooler rim light separate overlapping forms. Both versions use ordinary standard materials and lighting; advanced shadows or physically simulated steam are not the differentiator.

### Why the controls work together

Each group stores a system ID, a layer index and an explosion vector. Every display update derives visibility from the visibility state and positions from disassembly state. This avoids burying the fuel and graphite inside one inseparable control group.

Disassembly uses a different smoothstep progress window per layer, multiplied by a three-dimensional offset and spacing. Buildings move aside, the turbine hall moves forward, and core components lift. This is staged spatial interpolation, not a physics simulation or a time-based spring animation.

Labels are anchored in world space, projected into screen space, and suppressed when too close to another label or the viewport edges. Camera fitting uses the current bounding box and aspect ratio; expansion preserves the current viewing direction. It is a practical heuristic, not a formal guarantee against every possible overlap.

Flow particles follow the same curves used to create pipes. A shared time value drives their path positions and machinery rotation. Pause stops time advancement; speed scales it; restart resets it. Material opacity, wireframe and clipping are separate properties.

## Confirmed differences

### 1. The effective requests were not identical

The Chernobyl creative brief matches the original core request, but OpenAtlas prepended `The learner requests: Tauri framework`. It also requested a 20-minute scrollable history lesson and additional lesson tests.

The output includes an entire Tauri chapter, a Tauri project map and two publication checks related to that chapter. The conflicting topic therefore demonstrably affected the deliverable. Additional history was intentionally requested, so it is not itself a bug; it did broaden the work beyond the standalone exhibit.

Fix: establish one authoritative topic when an edited build brief changes subjects. A stale original learner prompt should not remain an equal instruction. Do not remove intended lesson scope; build and evaluate the 3D surface before expanding the narrative.

### 2. Build-brief mode discards substantial design guidance

In `openatlas/agents.py:22–26`, the adapter loads `teaching_prompt`, then replaces it when `build_prompt` is present:

```python
if request.get("build_prompt"):
    teaching = "Selected creative brief:\n" + request["build_prompt"]
```

The job stores a detailed teaching prompt about visual explanation, design approach, review and readable graphics. Most of it is absent from the captured builder prompt. Stored configuration is not equivalent to effective instructions.

This may be intentional to prevent conflicting prompts, but it means changing the long teaching prompt will not improve the builder in this path. Preserve a concise, invariant quality contract separately from the editable creative brief. Avoid simply concatenating every prompt: some general advice against dashboards conflicts with an explicitly requested inspection exhibit.

Today's `READER_NAVIGATION_REQUIREMENTS` is newer than this run's captured prompt. Likewise, the run used core skill 1.1.0; today's core skill is 1.2.0 with navigation additions. Those new instructions cannot explain this older output.

### 3. Active skills differed

Only `openatlas-core` 1.1.0 was selected and staged. The presence of `frontend-design`, `3d-explorer`, or Blender files in the repository does not mean the generator received or used them. The Desktop run read the Sites building/hosting skills, including concrete design, primary-surface, component and verification guidance.

Fix: route relevant, compatible design and 3D guidance explicitly. Adapt it to OpenAtlas's artifact format. Do not transplant Sites deployment rules into the container, or add Blender merely because the result is 3D.

### 4. Scene decomposition explains much of the inspection gap

| Area | Desktop build | OpenAtlas published build |
|---|---|---|
| Plant silhouette | Paired reactor volumes with a long turbine hall and connecting mass | One compact reactor volume beside a shorter hall |
| Core | Graphite bricks, fuel channels and shielding in separate groups | Graphite columns and channel cylinders created in the same `stack` group |
| Visibility | Seven independent system IDs | Four broad groups: shell, core, pipes, machines |
| Separator drums in Power Block | Four | Two |
| Circulation pumps in Power Block | Eight | Two |
| Disassembly | Staggered progress windows, distinct X/Y/Z offsets | All layers move linearly upward from the start |
| Labels | World projection plus simple overlap and edge suppression | Projection and limited hiding; no pairwise overlap suppression |
| Opacity/cut | Adjustable sliders | Fixed transparency value and fixed section-plane checkbox |
| Camera | Explicit fit and zoom buttons, bounding-box-based expansion | Fixed initial camera and a multiplier based on explosion amount |
| Steam Circuit | Three.js explanatory circuit | Animated SVG circuit, which is a valid choice for the requested diagram |

OpenAtlas's formula is `base + ex * sp * rank * 2`, applied only to Y. That separates layers but does not choreograph a progressive reveal. Fuel remains with the graphite, so it cannot be inspected as an independently exploded layer. More prose saying “premium” does not resolve this structural choice.

### 5. Research was not equivalent

The Desktop run searched public sources and opened the plant operator's general layout and an IAEA-hosted technical archive. The retained OpenAtlas log shows a request to an outdated World Nuclear Association URL returning HTTP 404. The artifact explicitly states references could not be retrieved and geometry was not validated against plant drawings.

A 404 is evidence of that failed URL, not proof that the container had no network access. Dependency installation worked. The CLI invocation did not explicitly configure a research tool. Because initial logs are lost, other early attempts cannot be exhaustively reconstructed.

Fix: distinguish build-time research access from the offline runtime contract. Use a working search/retrieval tool or pre-stage verified reference extracts and source URLs. Keep the published notebook offline.

### 6. Testing was real, but its assertions were too indirect

The agent ran 30 interaction checks, generated screenshots, tested keyboard controls, reduced motion, overflow, and the opaque-origin iframe, and repaired several issues. It is inaccurate to say the CLI run did no testing or iteration.

However, many assertions are `click control → #status contains expected words`. Keyboard camera tests assert “rotated” or “zoom,” rather than camera movement. A canvas count asserts that a canvas exists, not that the correct model is rendered. Those tests can pass while graphite hides fuel, labels overlap, or the whole plant is visually too simple.

The Desktop run directly consumed screenshots and revised clipping geometry, visible fuel channels, camera expansion, controls and labels. The retained OpenAtlas tail shows screenshot creation but does not establish that the images were actually viewed by the model. With the log truncated, absence of a viewing event is not proof that none occurred.

Fix: keep DOM and sandbox tests, and add scene-state assertions and explicit visual review. Check system visibility, actual transforms, projected bounds, animation time while paused, and camera movement. Review assembled, partially exploded, fully exploded at maximum spacing, and motion cutaway states. Feed the captured images back to the reviewing model; saving PNGs alone is insufficient.

A related publisher issue: screenshots are taken after all interaction checks without resetting scroll. This version's `preview.png` shows the Tauri chapter rather than the 3D exhibit. Capture deterministic preview states rather than whatever the last test leaves on screen.

## Things the evidence does not support

- **Wrong model:** relay logs report both requested and returned `gpt-6-astra`. Desktop metadata also records `gpt-6-astra`. This establishes identifiers, not identical backend snapshots or the entire effective configuration.
- **Lower reasoning definitely caused it:** Desktop recorded `medium`. OpenAtlas did not pass an explicit effort setting and the relay logs only model names. Its actual effective effort is unknown. Set it explicitly for a controlled comparison.
- **A time limit cut the run off:** it completed successfully in roughly 10½ minutes of generation, inside its configured 30-minute limit.
- **Too little output:** OpenAtlas reported about 22k output tokens. It did not fail to produce substantial code/content. Total input tokens include repeated cached context and are not unique prompt length or a quality metric.
- **Docker made the final graphics worse:** two CPU cores and 2 GiB can slow generation/testing, but the published geometry renders in the reader's browser. No evidence ties those limits to the visual simplification.
- **React or Sites automatically makes prettier 3D:** both scenes use the same fundamental Three.js primitives. Stack and bundling differences affect reliability and convenience; modeling and interaction choices determine the observed geometry.
- **Desktop used hidden 3D assets:** it did not. The procedural model is in the source.

The Desktop timestamps contain a long gap. They must not be interpreted as proof of proportionally more model reasoning or productive implementation time.

## Recommended OpenAtlas improvement order

1. Fix topic consistency and make the effective builder prompt inspectable before dispatch.
2. Separate the persistent quality/reader contract from the editable creative brief. Preserve compatible guidance in both direct and planned generation paths.
3. Pin model and effort explicitly for parity: begin the comparison with `gpt-6-astra` and `model_reasoning_effort="medium"`. Log the requested/resolved configuration where available, CLI version, tool names, skill hashes, and prompt hash without credentials.
4. Supply a tested Three.js exhibit scaffold: independent system groups, original/exploded transforms, camera fit, curve-driven flows, labels, material controls and cleanup. Generate topic geometry and teaching content on top of it. Reuse this build's architecture, after improving its shortcomings, rather than expecting each run to rediscover it.
5. Establish a component/relationship specification before writing geometry. For this exhibit, fuel, graphite and shielding must remain distinct; water and steam need separate identities; buildings need space to move aside.
6. Provide verified build-time references and a conventional ESM bundler. OpenAtlas spent a repair step downgrading Three.js because its hand-written CommonJS embedding encountered the newer CJS shim. esbuild avoids that particular packaging workaround.
7. Add deterministic scene tests and image review. Do not weaken the existing reader sandbox, external-resource checks or accessibility checks.
8. Build and review the exhibit first, then integrate the requested history lesson without changing the validated scene. A staged process can be sequential; it does not require multiple agents.
9. Run controlled comparisons with the same brief, scope, skills, references, effort and scaffold. Change one factor at a time and review several generations before attributing causality to a client or setting.

## Suggested portable quality contract

> Treat the 3D exhibit as the primary working surface. Before implementation, define the named systems, their assembly relationships, and their disassembly paths. Keep every requested inspectable system separate in the scene graph. Use a coherent subject-specific visual direction and enough geometric detail to preserve the plant's recognizable silhouette. Preserve camera orbit at every stage and fit the full exploded layout. Test actual geometry visibility and movement, not just status messages. Capture and view assembled, partial, fully exploded/max-spacing, and cutaway states; repair occlusion, overlap and clipping issues. Once the exhibit passes, integrate the requested narrative lesson. Keep all runtime dependencies bundled and maintain the reader sandbox contract.

This contract should complement the learner's request, not replace it or force every lesson into a 3D dashboard.

## Limitations of the preferred build

The Desktop result is not a perfect reference implementation. It has small secondary text, an approximate camera fit, no reduced-motion default, some switches for systems absent from a view, and illustrative machinery motion. The OpenAtlas build has useful accessibility features, material caching and offscreen animation throttling that should be preserved. Neither is an exact reactor replica or a physically validated simulation.

## Official configuration references

- [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference): explicit model effort, tool/search configuration and configuration layers.
- [Custom instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md): project guidance is part of the effective agent context, beyond the visible user prompt.
