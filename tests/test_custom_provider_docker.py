"""Real SDK and installed Codex CLI against a local provider; no paid inference."""

import json
import os
import time
from pathlib import Path
from uuid import uuid4

import pytest

from openatlas.agents import CodexAdapter
from openatlas.credentials import Credentials
from openatlas.debug import DebugStore
from openatlas.execution import DockerExecutor
from openatlas.planning import PlannerAdapter


@pytest.mark.skipif(
    os.getenv("OPENATLAS_DOCKER_TEST") != "1", reason="Requires generation image"
)
def test_saved_profiles_route_real_sdk_and_codex_cli(tmp_path):
    import docker

    client = docker.from_env()
    upstream = None
    try:
        upstream = client.containers.run(
            "openatlas-generation:local",
            [
                "python3",
                "-c",
                (Path(__file__).parent / "fixtures/custom_provider.py").read_text(),
            ],
            detach=True,
            network_mode="bridge",
            read_only=True,
        )
        upstream.reload()
        host = (
            "http://"
            + upstream.attrs["NetworkSettings"]["Networks"]["bridge"]["IPAddress"]
            + ":9010"
        )
        inspect = [
            "python3",
            "-c",
            "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:9010/requests').read().decode())",
        ]
        for _ in range(30):
            if upstream.exec_run(inspect).exit_code == 0:
                break
            time.sleep(0.1)
        else:
            pytest.fail("Fixture provider did not start")
        credentials = Credentials(tmp_path / "private-data")
        state = credentials.save_profile(
            "Provider A", host + "/provider-a/v2", "provider-A-token", activate=True
        )
        first = state["active_id"]
        state = credentials.save_profile(
            "Provider B", host + "/provider-b/v1", "provider-B-token", activate=True
        )
        second = state["active_id"]
        credentials.activate(first)
        debug = DebugStore(tmp_path / "diagnostics")
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        plan_request = {
            "job_id": str(uuid4()),
            "execution_stage": "planning",
            "planner_model": "vendor/planner:v2",
            "planner_instructions": "Write a brief for the requested lesson.",
            "prompt": "Explain a flagellar motor",
            "skills": [],
        }
        planner = DockerExecutor(credentials, adapter=PlannerAdapter(), debug=debug)
        assert "flagellar motor" in planner.run(workspace, plan_request, lambda _: None)

        # Re-open storage as another worker would, switch profiles, then run the
        # installed CLI and assert that it actually consumes a successful stream.
        Credentials(credentials.directory.parent).activate(second)
        codex = CodexAdapter()
        codex.prompt = lambda request: (
            "Explain a flagellar motor briefly. Do not use tools."
        )
        command = codex.command({"model": "vendor/codex:latest"})
        (workspace / "cli_test.py").write_text(
            "import subprocess, pathlib\n"
            f"result = subprocess.run({command!r}, capture_output=True, text=True, timeout=45)\n"
            "assert result.returncode == 0, result.stdout + result.stderr\n"
            'assert "flagellar motor" in result.stdout, result.stdout\n'
            'pathlib.Path("/workspace/plan.md").write_text("The real Codex CLI successfully received the fixture flagellar motor response.")\n'
        )

        class Adapter:
            def command(self, request):
                return ["python3", "/workspace/cli_test.py"]

        cli_request = dict(
            plan_request, job_id=str(uuid4()), model="vendor/codex:latest"
        )
        assert "successfully received" in DockerExecutor(
            credentials, adapter=Adapter(), debug=debug
        ).run(workspace, cli_request, lambda _: None)
        observed = json.loads(upstream.exec_run(inspect).output)
        assert observed == [
            {
                "path": "/provider-a/v2/responses",
                "authorization": "Bearer provider-A-token",
                "model": "vendor/planner:v2",
                "stream": True,
            },
            {
                "path": "/provider-b/v1/responses",
                "authorization": "Bearer provider-B-token",
                "model": "vendor/codex:latest",
                "stream": True,
            },
        ]
        for request in (plan_request, cli_request):
            captured = json.dumps(debug.read(request["job_id"])) + json.dumps(
                debug.invocations(request["job_id"])
            )
            assert (
                "provider-A-token" not in captured
                and "provider-B-token" not in captured
            )
        assert (
            Credentials(credentials.directory.parent).profiles()["active_id"] == second
        )
    finally:
        if upstream is not None:
            upstream.remove(force=True)
        client.close()
