"""Opt-in real Docker boundary test; no inference or real API key is used."""

import os
import shutil
from uuid import uuid4

import pytest

from openatlas.artifacts import validate
from openatlas.debug import DebugStore
from openatlas.demo import generate
from openatlas.execution import DockerExecutor
from openatlas.skills import SkillCatalog


@pytest.mark.skipif(
    os.getenv("OPENATLAS_DOCKER_TEST") != "1",
    reason="Set OPENATLAS_DOCKER_TEST=1 with the generation image built",
)
def test_disposable_docker_roundtrip(tmp_path):
    import docker

    class FakeCredential:
        def openai_key(self):
            return "test-credential-not-for-inference"

    class FileEditingAgent:
        def command(self, request):
            return [
                "python3",
                "-c",
                "import os, pathlib, subprocess; assert os.getuid()!=0; assert 'OPENAI_API_KEY' not in os.environ; assert not pathlib.Path('/var/run/docker.sock').exists(); p=pathlib.Path('/workspace/source/index.html'); p.write_text(p.read_text().replace('Remember the work.','Remember the previous work.')); subprocess.run(['python3','source/build.py'],check=True)",
            ]

    request = {
        "prompt": "Container roundtrip",
        "job_id": str(uuid4()),
        "skills": SkillCatalog().resolve(["builtin:visual-explainer"]),
    }
    generate(tmp_path, request, lambda _: None)
    shutil.rmtree(tmp_path / "dist")
    (tmp_path / "dist").mkdir()
    SkillCatalog().stage(request["skills"], tmp_path / "skills")
    debug = DebugStore(tmp_path / "diagnostics")
    DockerExecutor(FakeCredential(), adapter=FileEditingAgent(), debug=debug).run(
        tmp_path, request, lambda _: None
    )
    assert "Remember the previous work." in (tmp_path / "source/index.html").read_text()
    assert "Remember the previous work." in (tmp_path / "dist/index.html").read_text()
    assert validate(tmp_path)["title"]
    client = docker.from_env()
    assert (
        client.containers.list(all=True, filters={"label": "openatlas.job=docker-test"})
        == []
    )
    client.close()

    snapshots = debug.read(request["job_id"])["containers"]
    assert len(snapshots) == 2
    assert {s["role"] for s in snapshots} == {"agent", "relay"}
    assert all(s["status"] == "removed" for s in snapshots)
