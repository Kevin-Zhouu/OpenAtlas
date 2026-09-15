Build a complete interactive 3D atlas of the human head and brain. Deliver a working application, not a mockup. Make reasonable decisions independently, implement it, test it, and visually verify the result.

Use Three.js and real, appropriately licensed Z-Anatomy / BodyParts3D meshes. Include the skull, teeth, facial muscles, brain, eyes, cranial nerves, arteries, veins, and available supporting membranes. Preserve their original anatomical relationships. Aim for hundreds of individually selectable structures, report the actual imported count, and retain source attribution.

Create a clean, light interface with a pale grey background, white rounded panels, restrained blue-grey accents, and readable typography. Keep the model large, with a structure panel on the left, camera tools on the right, search at the top, and an explosion slider below. Use English throughout.

Make the anatomy progressively explorable:\
Head → system → region → individual named structures.\
For example: Brain → Cerebrum → Left hemisphere → Frontal lobe → individual structures.

Animate assembly and disassembly. Preserve source positions when assembled; arrange exploded groups in clearly separated layouts with readable labels. Indicate normalized scale and paginate large collections.

Include:

- Free rotation, wheel/pinch zoom, and camera presets.
- Disassembly slider
- Anatomical search, click-to-inspect, focus, isolation, and parent navigation.
- Anatomical colours, porcelain, wireframe, and transparent modes.
- Adjustable sagittal, axial, and coronal clipping planes with reverse direction. (do not make these buttons and overcomplicate the UI looking messy)
- Labels, automatic exploration, fullscreen, and PNG export.
- A guided journey from the complete head into the brain and its networks.

Keep hidden structures hidden across layout and material changes. Explain that clipping planes produce open display cuts, not medical scans. Do not invent anatomy or claim clinical validation.

Deliver a standalone HTML containing the application and processed geometry, working offline without a server. Also provide clean source files, pinned dependencies, a lockfile, portable build scripts, an English README, and required licences and attribution. Exclude credentials, local machine paths, dependencies, and unrelated files.

Test geometry integrity, hierarchy membership, visibility, undo, and layout spacing. Inspect the running application in a browser, exercise the controls, check for console errors, and fix visual overlaps before delivering.

---

Keep manual 3D controls minimal. Avoid cluttering the interface with too many buttons, sliders, or customization options. The sophistication should come from the visuals, animation, camera movement, and interaction design.

Make the page a scroll-driven 3D learning experience. As the user scrolls, progressively explain the anatomy of the head and brain, moving from the complete head into systems, regions, and individual structures.

Reuse the same master 3D model throughout. For each section, transition the camera and model to highlight, isolate, fade, clip, or separate the relevant anatomy while showing a concise explanation beside it.

Scrolling should smoothly drive these transitions so the experience feels like one continuous visual story rather than separate illustrations.

Use the 3D model as a teaching tool, not decoration. Focus on helping the learner understand where structures are, how they relate spatially, and how deeper layers connect.

Keep each section visually focused and avoid showing too much at once. The goal is to help a learner with little anatomy knowledge build a clear mental model of the human head and brain.