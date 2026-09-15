import sqlite3
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from openatlas.api import create_app
from openatlas.debug import DebugStore
from openatlas.deletion import purge
from openatlas.repository import Repository

SECRET = "SENSITIVE_NOTEBOOK_SENTINEL_a97c411"


def fixture(tmp_path):
    repo = Repository(tmp_path)
    job = repo.enqueue({"prompt": SECRET, "provider": "demo", "skills": []})
    second = repo.enqueue(
        {"prompt": SECRET, "provider": "demo", "skills": []}, job["notebook_id"]
    )
    other = repo.enqueue(
        {"prompt": "Keep unrelated work", "provider": "demo", "skills": []}
    )
    db = DebugStore(tmp_path)
    for item in (job, second):
        ident = item["id"]
        for folder in (
            "checkpoints",
            "failed",
            "previews",
            "validation",
            "debug/traces",
        ):
            target = tmp_path / folder / ident
            target.mkdir(parents=True)
            (target / "sensitive.txt").write_text(SECRET)
        workspace = tmp_path / "workspaces" / (ident + "-orphan")
        workspace.mkdir(parents=True)
        (workspace / "private.txt").write_text(SECRET)
        db.record(ident, {"id": "container", "observed_at": "now", "agent_log": SECRET})
        db.record_invocation(ident, ["codex", SECRET], item["request"])
    library = tmp_path / "library" / job["notebook_id"]
    library.mkdir(parents=True)
    (library / "sensitive.txt").write_text(SECRET)
    with sqlite3.connect(repo.data / "openatlas.sqlite3") as conn:
        attempt, revision = str(uuid4()), str(uuid4())
        conn.execute(
            "INSERT INTO planning_attempts(id,job_id,inputs,status,created_at,output) VALUES (?,?,?,?,?,?)",
            (attempt, job["id"], SECRET, "succeeded", "now", SECRET),
        )
        conn.execute(
            "INSERT INTO prompt_revisions VALUES (?,?,?,?,?)",
            (revision, attempt, None, SECRET, "now"),
        )
        conn.execute(
            "INSERT INTO job_events(job_id,stage,message,created_at) VALUES (?,?,?,?)",
            (job["id"], "building", SECRET, "now"),
        )
        conn.execute(
            "INSERT INTO steering_messages VALUES (?,?,?,?,?)",
            (str(uuid4()), job["id"], SECRET, "queued", "now"),
        )
        conn.execute(
            "INSERT INTO versions VALUES (?,?,?,?,?,?,?)",
            (
                str(uuid4()),
                job["notebook_id"],
                "now",
                SECRET,
                SECRET,
                "demo",
                job["id"],
            ),
        )
    return repo, job, second, other


def test_delete_removes_all_copies_and_sqlite_bytes_but_preserves_other_work(tmp_path):
    repo, job, second, other = fixture(tmp_path)
    client = TestClient(create_app(repo), base_url="http://localhost")
    response = client.delete("/api/jobs/" + job["id"])
    assert response.status_code == 202
    assert repo.job(second["id"])["status"] == "deleting"
    assert client.get("/api/jobs/" + job["id"] + "/debug").status_code == 410
    assert client.get("/api/notebooks/" + job["notebook_id"]).status_code == 410
    assert (
        client.get(
            "/artifacts/" + job["notebook_id"] + "/version/index.html"
        ).status_code
        == 410
    )
    assert all(
        j["notebook_id"] != job["notebook_id"] for j in client.get("/api/jobs").json()
    )
    with pytest.raises(ValueError, match="deleted"):
        repo.enqueue({"prompt": SECRET}, job["notebook_id"])
    purge(repo, job["notebook_id"])
    assert repo.job(job["id"]) is None and repo.job(second["id"]) is None
    assert repo.job(other["id"])["request"]["prompt"] == "Keep unrelated work"
    assert client.get("/api/deletions").json() == []
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert SECRET.encode() not in path.read_bytes(), path
    # A delayed observer capture must not recreate deleted logs.
    store = DebugStore(tmp_path)
    store.record(job["id"], {"id": "late", "observed_at": "later", "agent_log": SECRET})
    store.save_trace(job["id"], "late", {"agent_log": SECRET})
    store.record_invocation(job["id"], ["codex", SECRET], {})
    assert not store.path(job["id"]).exists()
    assert not store.trace_path(job["id"], "late").exists()


def test_container_removal_failure_leaves_retryable_deletion(tmp_path):
    repo, job, _, _ = fixture(tmp_path)
    repo.request_deletion(job["notebook_id"])

    class Container:
        def remove(self, force):
            raise RuntimeError("Docker unavailable")

    class Containers:
        def list(self, **kwargs):
            return [Container()]

    with pytest.raises(RuntimeError):
        purge(repo, job["notebook_id"], Containers())
    assert repo.deleting(job["notebook_id"])
    assert repo.job(job["id"])["status"] == "deleting"
    purge(repo, job["notebook_id"])
    assert not repo.deleting(job["notebook_id"])


def test_delete_is_protected_from_cross_origin_requests(tmp_path):
    repo, job, _, _ = fixture(tmp_path)
    client = TestClient(create_app(repo), base_url="http://localhost")
    assert (
        client.delete(
            "/api/notebooks/" + job["notebook_id"],
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    assert not repo.deleting(job["notebook_id"])


def test_runner_drains_a_late_writer_before_permanent_cleanup(tmp_path, monkeypatch):
    import threading

    from openatlas.demo import generate
    from openatlas.runner import Runner

    repo = Repository(tmp_path)
    job = repo.enqueue(
        {"prompt": SECRET, "provider": "codex", "skills": [], "planning_enabled": False}
    )
    entered, release, cleaned = threading.Event(), threading.Event(), threading.Event()
    paths = []

    class Agent:
        def run(self, workspace, request, progress):
            paths.append(workspace)
            entered.set()
            assert release.wait(5)
            generate(workspace, request, progress)
            (workspace / "source" / "late-private.txt").write_text(SECRET)

    runner = Runner(repo, executor=Agent())
    monkeypatch.setattr("openatlas.runner.observe", lambda *args: None)
    monkeypatch.setattr("openatlas.runner.SubscriptionWorker.run", lambda *args: None)
    monkeypatch.setattr(runner, "cleanup_expired", lambda: None)

    def cleanup():
        assert release.is_set()
        assert not paths[0].exists()
        purge(repo, job["notebook_id"])
        cleaned.set()
        runner.stop.set()

    monkeypatch.setattr(runner, "process_deletions", cleanup)
    worker = threading.Thread(target=runner.run)
    worker.start()
    try:
        assert entered.wait(5)
        repo.request_deletion(job["notebook_id"])
        assert not cleaned.wait(0.1)
        release.set()
        assert cleaned.wait(5)
        assert repo.job(job["id"]) is None
        assert not list((tmp_path / "workspaces").iterdir())
    finally:
        release.set()
        runner.stop.set()
        worker.join(5)
