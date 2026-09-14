---
name: blender
description: Create, inspect and export 3D educational assets using the container-local Blender and Blender MCP. Apply when spatial relationships, cutaways, disassembly, anatomy, machinery or rendered illustrations help teach the requested topic.
metadata:
  version: "1.0.0"
---

# Blender for learning Notebooks

Blender is available as a core tool, not a required visual format. Respect explicit requests for 3D; otherwise choose it when spatial exploration explains the subject better than a diagram. Do not add 3D merely because this skill is present.

During planning, describe what learners should inspect or manipulate and what that reveals. Assign modeling, research and verification to the builder; the planner does not run Blender. Identify simplifications and reference requirements without claiming research you did not perform.

During implementation, read [the workflow](references/workflow.md). Use the `blender` MCP tools to inspect the scene, execute small modeling steps, and inspect results. The generation container includes Blender, the matching Blender MCP addon/server, and a private virtual display. No desktop Blender connection or installation is needed.

Keep editable `.blend` files and reproducible scripts in `/workspace/source`. Export lightweight GLB models, textures or rendered images for the static Notebook, using locally bundled browser dependencies. Blender is an authoring tool; the published Notebook must work without Blender or an MCP server.

Prioritize readable silhouettes, meaningful component names and relationships. Inspect camera framing, geometry, material contrast and labels. Test the exported asset in the actual browser at desktop and phone widths, including keyboard operation, reduced motion and a useful non-WebGL fallback. Model disassembly, visibility and section controls only when they support the lesson. Explain educational approximations and verify factual details; record sources and asset licenses.
