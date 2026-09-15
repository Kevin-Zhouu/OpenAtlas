# Graphics planning evaluation

Evaluate actual generated briefs and notebooks separately from infrastructure tests.
Use the packaged catalog and record the selected reference IDs and evidence limits.
Read relevant principles, interaction notes, provenance and evaluations; builder
review should also view available contact sheets. Do not interpret a provisional
reference score as an automatic pass or claim omitted media was inspected.

| Learner request | Expected planning outcome | Useful reference qualities |
| --- | --- | --- |
| “Chernobyl disaster”, beginner, 20 minutes | A substantial recognizable plant/reactor exhibit, independently inspectable systems, overview/interior/process views, progressive separation, connected water/steam flow and integrated historical explanation. Verify engineering and historical facts; no automatic “small cutaway” scope reduction. | Chernobyl Atlas: linked representations, consistent system colors, reversible inspection. Address its documented weak causal explanation and initial framing. |
| “How the heart pumps blood”, beginner | Spatial chambers and vessels with verified anatomy, connected directional flow and selected-component explanation; explicit schematic limitations. | Head/brain atlas and Human Atlas: hierarchy, isolation, reassembly, readable labels. Transfer mechanisms without importing brain content or implying clinical accuracy. |
| “Why bridges matter to delivery networks” | Manipulate connectivity and observe route/outcome changes. Justify a legible 2D graph or spatial map; label metaphorical representations. | Snowbound Dispatch: reversible disruption and recovery, map/outcome coupling; algorithm and live behavior remain unverified in the dataset. |
| “Explain compound interest using only 2D charts” | Preserve explicit 2D requirement. Relate time/rate controls to chart geometry and explanation. No forced 3D. | Transfer nearby control/feedback/explanation qualities only; explain why a reference or 3D geometry is irrelevant. |
| “Explore a building in 3D, then tell its story” | Recognizable structural detail, separate systems and inspection views followed by the requested story; prose does not replace the exhibit. | Temple and Chernobyl: component relationships and context, with demo-only evidence limits where applicable. |
| Approved edited brief changes topic | Build the approved topic, without merging the unrelated original topic. | Preserve relevant interaction qualities, not reference subject matter. |
| Missing catalog, missing record, or unavailable image tool | Report exactly what could not be read/viewed; specify justified fallback and verification gaps. | No invented inspection claims or unearned visual-review pass. |

For every major interaction, inspect the brief for the manipulated object, visible
change, mechanism revealed, and stable orientation cue. Require named components,
spatial relationships and acceptance criteria instead of adjectives alone. A 2D
or simpler choice must have a topic-specific educational rationale. Layout, palette
and typography should vary appropriately between topics.

For a built spatial exhibit, test actual selected parts, visibility across material
and layout changes, independent transforms, framing at full separation, orbit,
connected flows and paused motion. Capture and view the overview, focused interior,
most demanding separated/cut state and phone view. Assess silhouette, material
separation, readable annotations, occlusion, clipping, touch and non-drag controls,
keyboard focus and reduced motion. Record observed failures and repairs in
`source/DESIGN.md`, tied to the brief and adopted reference qualities.

Infrastructure coverage: `tests/test_references.py` verifies packaged archive
contents, missing/changed input reporting, real text-reader behavior and path
containment. `tests/test_planning.py` checks staging for planning and saved-brief
builds plus persistent package fingerprints. The opt-in Docker planner fixture
reads actual reference records through the Agents SDK and verifies the access
ledger. These tests do not call a paid model or evaluate rendered lesson quality.
