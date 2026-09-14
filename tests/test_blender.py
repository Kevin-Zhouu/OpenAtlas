import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from openatlas.agents import BLENDER_MCP_CONFIG, CodexAdapter
from openatlas.skills import SkillCatalog


def test_blender_core_snapshot_and_codex_configuration(tmp_path):
    catalog = SkillCatalog()
    selected = catalog.resolve([])
    assert [s["id"] for s in selected] == ["builtin:openatlas-core", "builtin:blender"]
    blender = selected[1]
    assert blender["required"] and blender["version"] and len(blender["sha256"]) == 64
    catalog.snapshot(selected, tmp_path / "cache")
    catalog.stage_snapshots(selected, tmp_path / "cache", tmp_path / "skills")
    assert (tmp_path / "skills/builtin--blender/references/workflow.md").is_file()
    request = {"prompt": "Teach anatomy", "model": "fixture", "skills": selected}
    command = CodexAdapter().command(request)
    assert BLENDER_MCP_CONFIG in command
    assert "/workspace/skills/builtin--blender/SKILL.md" in command[-1]
    request["skills"] = []
    assert BLENDER_MCP_CONFIG not in CodexAdapter().command(request)
    # Historical selections do not silently acquire a different core skill.
    request["skills"] = selected[:1]
    assert BLENDER_MCP_CONFIG not in CodexAdapter().command(request)


@pytest.mark.skipif(
    os.getenv("OPENATLAS_DOCKER_TEST") != "1",
    reason="Requires Blender generation image",
)
def test_real_blender_mcp_export_and_cleanup(tmp_path):
    from openatlas.debug import DebugStore
    from openatlas.demo import generate
    from openatlas.execution import DockerExecutor

    class Credential:
        def openai_key(self):
            return "test-not-a-real-key"

    class Adapter:
        def command(self, request):
            return ["/opt/blender-mcp/bin/python", "/workspace/blender_client.py"]

    request = {"prompt": "Explain a cube", "job_id": str(uuid4()), "skills": []}
    generate(tmp_path, request, lambda _: None)
    (tmp_path / "blender_client.py").write_text(
        (Path(__file__).parent / "fixtures/blender_client.py").read_text()
    )
    (tmp_path / "blender_config.json").write_text(json.dumps(BLENDER_MCP_CONFIG))
    debug = DebugStore(tmp_path / "debug")
    DockerExecutor(Credential(), adapter=Adapter(), debug=debug).run(
        tmp_path, request, lambda _: None
    )
    assert (tmp_path / "source/model.blend").read_bytes().startswith(b"BLENDER")
    assert (tmp_path / "dist/model.glb").read_bytes().startswith(b"glTF")
    snapshots = debug.read(request["job_id"])["containers"]
    assert len(snapshots) == 2 and all(c["status"] == "removed" for c in snapshots)
