import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from openatlas.api import create_app
from openatlas.repository import Repository


def test_timeout_settings_persist_validate_and_apply_to_retries(tmp_path):
    repo = Repository(tmp_path)
    client = TestClient(create_app(repo), base_url="http://localhost")
    settings = client.get("/api/settings").json()
    assert settings["generation_timeout_minutes"] == 120
    settings["generation_timeout_minutes"] = 240
    assert client.put("/api/settings", json=settings).status_code == 200
    assert Repository(tmp_path).settings()["generation_timeout_minutes"] == 240
    job = client.post(
        "/api/jobs",
        json={
            "prompt": "Explain a motor",
            "provider": "codex",
            "skills_enabled": False,
        },
    ).json()
    assert job["request"]["generation_timeout_minutes"] == 240
    settings["generation_timeout_minutes"] = 360
    client.put("/api/settings", json=settings)
    assert repo.job(job["id"])["request"]["generation_timeout_minutes"] == 240
    repo.claim(2)
    repo.fail(job["id"], "time limit")
    retry = client.post(f"/api/jobs/{job['id']}/retry", json={"mode": "rerun"}).json()
    assert retry["request"]["generation_timeout_minutes"] == 360
    del settings["generation_timeout_minutes"]
    client.put("/api/settings", json=settings)
    assert repo.settings()["generation_timeout_minutes"] == 360
    for value in (0, -1, 1441, 1.5, True, "120"):
        assert (
            client.put(
                "/api/settings", json={**settings, "generation_timeout_minutes": value}
            ).status_code
            == 422
        )


@pytest.mark.skipif(
    os.getenv("OPENATLAS_DOCKER_TEST") != "1", reason="Requires generation image"
)
def test_configured_limit_overrides_short_host_limit_and_timeout_is_actionable(
    tmp_path, monkeypatch
):
    from openatlas import config
    from openatlas.debug import DebugStore
    from openatlas.execution import DockerExecutor

    class Credential:
        def connection(self):
            return {"api_key": "test-unused", "base_url": "https://api.openai.com/v1"}

    class Adapter:
        def command(self, request):
            return [
                "python3",
                "-c",
                'import time,pathlib;time.sleep(3);pathlib.Path("/workspace/plan.md").write_text("Build an interactive motor lesson with labeled rotor and stator parts, and controls demonstrating ion flow.")',
            ]

    monkeypatch.setattr(config, "TIMEOUT", 1)
    debug = DebugStore(tmp_path / "debug-data")
    executor = DockerExecutor(Credential(), adapter=Adapter(), debug=debug)
    request = {
        "job_id": str(uuid4()),
        "execution_stage": "planning",
        "generation_timeout_minutes": 1,
    }
    assert "interactive motor" in executor.run(tmp_path, request, lambda _: None)
    assert debug.invocations(request["job_id"])[0]["execution"]["timeout_seconds"] == 60
    request = {"job_id": str(uuid4()), "execution_stage": "planning"}
    with pytest.raises(ValueError, match="Increase Generation time limit in Settings"):
        executor.run(tmp_path, request, lambda _: None)
