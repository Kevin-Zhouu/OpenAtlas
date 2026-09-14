"""Real MCP protocol and Blender export probe, run inside the disposable worker."""

import asyncio
import json
import os
import subprocess
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    assert os.getuid() != 0
    assert not Path("/var/run/docker.sock").exists()
    assert os.environ["BLENDER_MCP_DISABLE_TELEMETRY"] == "1"
    config = json.loads(Path("/workspace/blender_config.json").read_text())
    parsed = subprocess.run(
        ["codex", "mcp", "list", "--json", "-c", config],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "blender" in parsed.stdout
    async with stdio_client(
        StdioServerParameters(
            command="/opt/blender-mcp/bin/python",
            args=["/opt/blender_mcp.py"],
            env=dict(os.environ),
        )
    ) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert "execute_blender_code" in {t.name for t in tools.tools}
            result = await session.call_tool(
                "get_scene_info", {"user_prompt": "Explain a cube"}
            )
            assert "Cube" in str(result), str(result)
            result = await session.call_tool(
                "execute_blender_code",
                {
                    "code": "import bpy\nbpy.data.objects['Cube'].name = 'LearningCube'\nbpy.ops.wm.save_as_mainfile(filepath='/workspace/source/model.blend')\nbpy.ops.export_scene.gltf(filepath='/workspace/dist/model.glb', export_format='GLB')",
                    "user_prompt": "Explain a cube",
                },
            )
            assert "Code executed successfully" in str(result), str(result)
            result = await session.call_tool(
                "get_object_info",
                {"object_name": "LearningCube", "user_prompt": "Explain a cube"},
            )
            assert "LearningCube" in str(result), str(result)
            screenshot = await session.call_tool(
                "get_viewport_screenshot",
                {"max_size": 320, "user_prompt": "Explain a cube"},
            )
            assert any(c.type == "image" for c in screenshot.content), str(screenshot)
            assert (
                Path("/workspace/source/model.blend")
                .read_bytes()
                .startswith(b"BLENDER")
            )
            assert Path("/workspace/dist/model.glb").read_bytes().startswith(b"glTF")
    print(
        "Blender MCP initialized, modeled, saved and exported successfully", flush=True
    )


asyncio.run(main())
