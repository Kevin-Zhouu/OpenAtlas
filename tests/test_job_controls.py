import json

import pytest
from fastapi.testclient import TestClient

from openatlas.api import create_app
from openatlas.artifacts import ArtifactStore
from openatlas.demo import generate
from openatlas.quality import review_prompt
from openatlas.repository import Repository
from openatlas.runner import Runner


def setup(tmp_path):
    repo = Repository(tmp_path / "data")
    store = ArtifactStore(repo.data)
    client = TestClient(create_app(repo, store=store), base_url="http://localhost")
    job = client.post(
        "/api/jobs",
        json={
            "prompt": "Explain caching",
            "provider": "codex",
            "skills_enabled": False,
        },
    ).json()
    repo.claim(2)
    repo.stage(job["id"], "building")
    return repo, store, client, job


def test_steering_closes_atomically_before_validation(tmp_path):
    repo, store, client, job = setup(tmp_path)
    endpoint = f"/api/jobs/{job['id']}/steer"
    assert client.post(endpoint, json={"message": "  "}).status_code == 409
    assert (
        client.post(endpoint, json={"message": "Make labels larger"}).status_code == 202
    )
    assert (
        client.post(endpoint, json={"message": "Keep the orbit controls"}).status_code
        == 202
    )
    assert [m["message"] for m in repo.take_steering_or_validate(job["id"])] == [
        "Make labels larger",
        "Keep the orbit controls",
    ]
    repo.finish_steering(job["id"], "applied")
    assert repo.take_steering_or_validate(job["id"]) == []
    assert client.post(endpoint, json={"message": "Too late"}).status_code == 409
    assert [
        m["status"]
        for m in client.get(f"/api/jobs/{job['id']}/controls").json()["messages"]
    ] == ["applied", "applied"]


def test_preview_is_dist_only_immutable_sandboxed_and_never_published(tmp_path):
    repo, store, client, job = setup(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    generate(workspace, job["request"], lambda _: None)
    (workspace / "source/private.txt").write_text("not public")
    store.snapshot_preview(job["id"], workspace)
    info = store.preview_info(job["id"])
    base = f"/previews/{job['id']}/{info['revision']}"
    response = client.get(base + "/index.html")
    assert response.status_code == 200
    assert "sandbox allow-scripts" in response.headers["content-security-policy"]
    assert base + "/" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"
    assert client.get(base + "/source/private.txt").status_code == 404
    assert (
        store.preview_file(job["id"], info["revision"], "../../source/private.txt")
        is None
    )
    old = response.text
    (workspace / "dist/index.html").write_text("new draft")
    store.snapshot_preview(job["id"], workspace)
    assert client.get(base + "/index.html").text == old
    assert client.post(f"/api/jobs/{job['id']}/skip-validation").status_code == 409
    repo.take_steering_or_validate(job["id"])
    assert client.post(f"/api/jobs/{job['id']}/skip-validation").status_code == 200
    assert repo.job(job["id"])["version_id"] is None
    assert repo.job(job["id"])["status"] == "failed"
    assert client.get(base + "/index.html").status_code == 200
    assert client.post(f"/api/jobs/{job['id']}/skip-validation").status_code == 409


def test_preview_discovery_requires_auth_and_assets_use_scoped_capability(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OPENATLAS_ACCESS_TOKEN", "test-only-token")
    monkeypatch.setenv("OPENATLAS_DESKTOP_PORT", "8000")
    monkeypatch.setenv("OPENATLAS_ALLOWED_HOSTS", "localhost,192.168.1.9")
    monkeypatch.setenv("OPENATLAS_LAN_URL", "http://192.168.1.9:8000")
    repo = Repository(tmp_path)
    store = ArtifactStore(tmp_path)
    app = create_app(repo, store=store)
    desktop = TestClient(app, base_url="http://localhost:8000")
    desktop.put("/api/phone", json={"enabled": True})
    job = repo.enqueue({"prompt": "test", "provider": "demo", "skills": []})
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    generate(workspace, job["request"], lambda _: None)
    store.snapshot_preview(job["id"], workspace)
    info = store.preview_info(job["id"])
    path = f"/previews/{job['id']}/{info['revision']}/index.html"
    assert (
        desktop.get(
            path, headers={"Origin": "null", "Sec-Fetch-Site": "cross-site"}
        ).status_code
        == 200
    )
    assert desktop.get("/api/jobs", headers={"Origin": "null"}).status_code == 403
    remote = TestClient(app, base_url="http://192.168.1.9:8001")
    assert remote.get(f"/api/jobs/{job['id']}/controls").status_code == 401
    assert remote.get(path).status_code == 200
    assert (
        remote.get(
            path.replace(info["revision"], "00000000-0000-0000-0000-000000000000")
        ).status_code
        == 404
    )


def test_runner_applies_messages_before_validating(tmp_path, monkeypatch):
    repo, store, client, job = setup(tmp_path)
    request = dict(job["request"], planning_enabled=False)
    job["request"] = request
    calls = []

    class Agent:
        def run(self, workspace, request, progress):
            calls.append(request)
            if request.get("execution_stage") == "reviewing":
                return {"verdict": "pass", "summary": "Fixture review"}
            generate(workspace, request, progress)
            if not request.get("steering_message"):
                repo.queue_steering(job["id"], "Make labels larger")
            else:
                assert request["steering_message"] == "Make labels larger"
                (workspace / "dist/index.html").write_text("larger labels")

    def validate(workspace):
        assert repo.steering(job["id"])[0]["status"] == "applied"
        assert (workspace / "dist/index.html").read_text() == "larger labels"
        return json.loads((workspace / "manifest.json").read_text())

    monkeypatch.setattr("openatlas.runner.validate", validate)
    Runner(repo, store, executor=Agent()).process(job)
    assert repo.job(job["id"])["status"] == "succeeded"
    assert len(calls) == 3
    assert "Make labels larger" in review_prompt(calls[-1])
    assert repo.job(job["id"])["request"]["steering_message"] == "Make labels larger"


def test_skip_during_validation_does_not_repair_or_publish(tmp_path, monkeypatch):
    repo, store, client, job = setup(tmp_path)
    job["request"]["planning_enabled"] = False

    class Agent:
        def run(self, workspace, request, progress):
            assert request.get("execution_stage") != "reviewing"
            generate(workspace, request, progress)

    def validate(workspace):
        from openatlas.validation_report import current_report

        repo.skip_validation(job["id"])
        report = current_report()
        report.add("next", "Next", "Never run")
        with report.check("next"):
            pytest.fail("Skipped validation continued")

    monkeypatch.setattr("openatlas.runner.validate", validate)
    Runner(repo, store, executor=Agent()).process(job)
    result = repo.job(job["id"])
    assert result["status"] == "failed" and result["version_id"] is None
    assert "skipped" in result["error"]
    assert store.checkpoint_path(job["id"])
    assert store.preview_info(job["id"])
