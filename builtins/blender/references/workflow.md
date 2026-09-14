# Container workflow

The `blender` MCP server starts a fresh Blender on a private software-rendered virtual display. Its socket binds only to 127.0.0.1 inside this generation environment. Tools include `get_scene_info`, `get_object_info`, `execute_blender_code`, `get_viewport_screenshot` and `get_addon_status`. Pass the learner's original request as `user_prompt` where supported. Telemetry is disabled. Cloud asset-generation integrations are not configured.

1. Inspect the existing scene and source before editing. A resumed build has saved files, but starts a fresh Blender process: load the saved `.blend` if relevant.
2. Use small `execute_blender_code` calls with `bpy`. Name components semantically, use consistent units and deliberate pivots for animation or disassembly. Avoid dense geometry that obscures the explanation or exceeds the container's CPU/memory limits.
3. Inspect the scene and viewport after changes. Save a native source and export web assets. For example, after creating a model:

```python
import bpy
bpy.ops.wm.save_as_mainfile(filepath='/workspace/source/model.blend')
bpy.ops.export_scene.gltf(filepath='/workspace/source/model.glb', export_format='GLB')
```

Have the reproducible build copy the GLB and referenced textures into `dist`. Keep `.blend` files out of `dist`. Use stable object names to wire browser controls. Check that the export retains hierarchy, scale and intended materials; Blender-specific shaders and modifiers may need baking or conversion.

4. Load the exported GLB with bundled Three.js or another appropriate local renderer. Teach through the controls: show what moves, changes or connects and explain why. Inspect the browser rendering, not only the Blender viewport.

For offline scripted authoring, `blender --background --factory-startup --python source/model.py` is also available. MCP itself uses a GUI event loop on the private virtual display; do not replace its process with background mode. Startup diagnostics are in `/tmp/blender-output.log`. Do not copy logs or skill resources into Notebook artifacts.
