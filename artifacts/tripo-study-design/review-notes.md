# Catalog review and proposed agent design

Reviewed 14 September 2026. This is a prompt analysis with one live-demo spot check, not an evaluation of every rendered website or a controlled test of prompt effectiveness.

## Scope and evidence

The supplied [Tripo page](https://www.tripo3d.ai/3d-prompts/models/gpt-6-astra?page=2) initially advertised 216 entries; retrieved pages showed differing totals, including 214 and 222. The collection mixes websites, games, Blender assets, animations, architecture, and follow-up requests.

The [current public GitHub catalog](https://github.com/TripoGrowthLab/awesome-astra-prompts) exposes only 100 entries. I combined those with 184 entries from an [earlier public snapshot](https://github.com/TripoGrowthLab/awesome-astra-prompts/blob/8bd28c05f13ce5264018335e1fc45d478e2c46d2/docs/catalog.en.md), deduplicating by public entry ID and preferring current text. This produced 222 distinct entries for text review. This is a union of snapshots, not a verified inventory of one consistent live version. The companion inventory records provenance without redistributing full prompts.

Tripo distinguishes author-published wording from reconstructed briefs and recommended recreation prompts. Some entries depend on missing images, existing projects, prior dialogue, external assets, or downstream video tools. Consequently, the evidence supports reusable design hypotheses, not the claim that these words alone reliably produce the showcased quality.

## What transfers to educational sites

**Commit to an observable experience.** The [smartphone example](https://www.tripo3d.ai/3d-prompts/gpt-6-astra-2096685163111694556) specifies component separation, selection, and functional explanations. Its useful contribution is a concrete relationship between action and information.

**Design the camera and composition.** The [rice-field brief](https://www.tripo3d.ai/3d-prompts/gpt-6-astra-2097602565110419781) coordinates depth layers, plant variation, wind, framing, controls, and efficient rendering. This suggests specifying the opening view and changed states together, so visual richness remains readable and responsive.

**Spend detail on the subject's defining features.** The [Temple of Heaven brief](https://www.tripo3d.ai/3d-prompts/gpt-6-astra-2097323734504017936) describes roof profiles and hierarchical disassembly. For learning, equivalent specificity should protect the structure being taught: hinges should turn around their hinges; internal paths should connect; parts should return to correct positions.

**Concentrate effort.** The [robot-pet specification](https://www.tripo3d.ai/3d-prompts/gpt-6-astra-2097004192627933279) allocates effort to proportions and motion, restricts the scene, and asks for visual evidence. Its reusable lesson is a priority order and a concrete quality threshold, not its long list of personal exclusions.

**Use references where geometry carries meaning.** The [head-and-brain atlas brief](https://www.tripo3d.ai/3d-prompts/gpt-6-astra-2098105648106078541) calls for licensed anatomical meshes, hierarchy, and preservation of spatial relationships. Educational fidelity needs an explicit asset strategy.

**Make simplifications visible.** The [collider brief](https://www.tripo3d.ai/3d-prompts/gpt-6-astra-2097781208596029936) separates scientific references from illustrative geometry and synthetic events. Its [repository](https://github.com/bubblik525/collider) explicitly describes a conceptual exhibit. A beautiful visualization should make its limits understandable.

**Make variables reveal a relationship.** The [Lorenz example](https://www.tripo3d.ai/3d-prompts/interactive-lorenz-attractor-2096572156453028193) links changes in initial conditions to trajectory comparison. For an educational generator, an input, a response, and an explanation should share the same underlying model.

These are design inferences. Prompt length, enthusiastic adjectives, exact model names, or phrases demanding perfection are not demonstrated causal explanations. Some very short catalog prompts depend heavily on model priors or omitted context. Detailed prompts can also contain conflicts or impractical scope.

## Live-demo spot check

I opened the [collider exhibit](https://bubblik525.github.io/collider/) and inspected its opening view and the “Separate calorimeters” transition. The control visibly separated the model and exposed internal layers. The interface uses a dominant central model, muted materials, a systems list, a field guide, and a timeline. The expanded model crowded the heading and approached the scene boundaries in the inspected viewport. This establishes that one interaction works and illustrates why changed-state visual checks matter; it does not verify all controls, performance, scientific accuracy, or learning outcomes.

## Recommended agent workflow

Topic → bounded learning outcomes → factual model → representation choice → interaction contracts → art direction → Codex build brief → browser and correctness review.

Start with one prompt-writing agent whose output passes to the website builder. Keep its content model and design decisions inspectable. A separate evaluator can be introduced when there are enough generated examples to identify recurrent failures; several agents are not a prerequisite.

For each learning interaction, preserve this mapping:

**Objective → action → state change → visible evidence → explanation → acceptance test.**

Use a small repertoire: assemblies, processes, parameter experiments, spatial worlds, and rule-based challenges. Select by the structure of the knowledge. Retrieve a few exemplars with similar interactions rather than inserting the entire catalog into every generation request. Keep source confidence and dependencies alongside each exemplar. Exclude incomplete follow-ups from standalone prompt exemplars.

The generator should add learning outcomes, misconception checks, predictions, explanatory feedback, and a transfer task. Those are proposed educational design requirements; the catalog does not establish their learning efficacy. Keep visual appeal, functional correctness, subject accuracy, and learning outcomes as separate evaluation dimensions.

OpenAI's [Codex prompting guidance](https://learn.chatgpt.com/docs/prompting) likewise recommends stating desired behavior, preserving constraints, and identifying verification. The accompanying generator prompt implements this as a concrete build contract.

## Evaluate before scaling

Compare a plain topic-only prompt against generated briefs across a small, diverse set: a mechanical assembly, a biological process, a mathematical relationship, a historical/geographic topic, and an abstract topic where 3D is less useful. Keep the builder, tools, asset access, and work budget constant. Repeat builds to observe variability rather than attributing a lucky result to the prompt.

Rate the outputs separately for factual correctness, meaningful interaction, visual clarity in multiple states, functional completion, accessibility, and rendering performance. Require subject-specific correctness checks to pass before visual polish can qualify a build as successful. Test learning with prediction and transfer questions; use learner testing before claiming improved learning or retention.

The first useful milestone is a reliable topic-to-brief generator and several evaluated builds. Fine-tuning on a mixed showcase catalog would be premature without verified prompt/output pairs and evidence of what needs improvement.
