import io
import json
import zipfile
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from openatlas.api import create_app
from openatlas.credentials import Credentials
from openatlas.debug import DebugStore, capture
from openatlas.repository import Repository


def test_trace_download_includes_stages_and_redacts_saved_credentials(
    tmp_path, monkeypatch
):
    repo = Repository(tmp_path)
    credentials = Credentials(tmp_path)
    credentials.save("private-profile-key")
    job = repo.enqueue(
        {"prompt": "Teach circuits", "provider": "codex", "model": "test", "skills": []}
    )
    store = DebugStore(tmp_path)
    store.record(
        job["id"],
        {
            "id": "test-agent",
            "stage": "building",
            "observed_at": "now",
            "agent_log": "Only the recent tail",
            "container_log": "Bearer private-access-token",
        },
    )
    store.save_trace(
        job["id"],
        "test-agent",
        {
            "stage": "building",
            "captured_at": "now",
            "retention": "complete",
            "agent_log": "First event\nprivate-profile-key\nFinal event",
        },
    )
    client = TestClient(
        create_app(repo, credentials=credentials), base_url="http://localhost"
    )
    response = client.get(f"/api/jobs/{job['id']}/trace")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment;" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert {name.split("/")[0] for name in archive.namelist()} >= {
            "planning",
            "implementing",
            "validating",
            "publishing",
        }
        log = archive.read("implementing/test-agent.agent.log").decode()
        assert "First event" in log and "Final event" in log
        assert "private-profile-key" not in log
        assert "[redacted]" in log
        assert (
            "private-access-token"
            not in archive.read("implementing/test-agent.container.log").decode()
        )
    scoped = client.get(f"/api/jobs/{job['id']}/trace?stage=building")
    with zipfile.ZipFile(io.BytesIO(scoped.content)) as archive:
        assert not any(name.startswith("planning/") for name in archive.namelist())
    assert client.get(f"/api/jobs/{job['id']}/trace?stage=invalid").status_code == 422
    assert client.get(f"/api/jobs/{uuid4()}/trace").status_code == 404
    monkeypatch.setenv("OPENATLAS_ACCESS_TOKEN", "access-control-secret")
    protected = TestClient(create_app(repo), base_url="http://localhost")
    assert protected.get(f"/api/jobs/{job['id']}/trace").status_code == 401


def test_archival_capture_keeps_start_beyond_snapshot_tail_and_final_wins(
    tmp_path, monkeypatch
):
    job_id = str(uuid4())
    payload = (
        b"FIRST EVENT\n" + b"a long event\n" * 20000 + b"private-token\nLAST EVENT\n"
    )

    class Container:
        id = "agent-fixture"
        labels = {"openatlas.job": job_id, "openatlas.stage": "planning"}
        attrs = {
            "Config": {
                "Cmd": ["sleep", "infinity"],
                "Env": ["CODEX_API_KEY=private-token"],
            },
            "State": {"Running": True, "Status": "running"},
        }

        def reload(self):
            pass

        def top(self, **kwargs):
            return {"Processes": []}

        def logs(self, **kwargs):
            return b""

        def exec_run(self, args):
            return SimpleNamespace(
                exit_code=0, output=payload if args[0] == "head" else payload[-131072:]
            )

    store = DebugStore(tmp_path)
    capture(Container(), store, archive=True)
    snapshot = store.read(job_id)["containers"][0]
    assert "FIRST EVENT" not in snapshot["agent_log"]
    saved = store.trace(job_id, Container.id)
    assert "FIRST EVENT" in saved["agent_log"] and "LAST EVENT" in saved["agent_log"]
    assert "private-token" not in saved["agent_log"]
    assert saved["retention"] == "complete"
    assert store.trace_path(job_id, Container.id).stat().st_mode & 0o777 == 0o600
    store.save_trace(
        job_id,
        Container.id,
        {"captured_at": "9999", "final_capture": False, "agent_log": "stale"},
    )
    assert "FIRST EVENT" in store.trace(job_id, Container.id)["agent_log"]


def test_historical_tail_is_labeled_and_inherited_planning_is_included(tmp_path):
    from openatlas.trace_export import trace_archive

    earlier = {
        "job": {"id": str(uuid4()), "status": "succeeded"},
        "containers": [
            {
                "id": "planner",
                "stage": "planning",
                "agent_log": "Earlier planning output",
            }
        ],
        "events": [],
    }
    current = {
        "job": {"id": str(uuid4()), "status": "running"},
        "containers": [],
        "events": [],
    }
    with zipfile.ZipFile(
        io.BytesIO(trace_archive(tmp_path, current, earlier))
    ) as archive:
        assert archive.read("planning/planner.agent.log") == b"Earlier planning output"
        assert (
            json.loads(archive.read("planning/planner.json"))["retention"]
            == "snapshot_only"
        )
        assert (
            json.loads(archive.read("manifest.json"))["planning_source_job_id"]
            == earlier["job"]["id"]
        )


def test_capture_truncation_drops_partial_final_lines(tmp_path, monkeypatch):
    from openatlas import debug

    monkeypatch.setattr(debug, "MAX_TRACE_BYTES", 32)
    job_id = str(uuid4())
    payload = b"complete event\n" + b"private-token-crossing-limit"

    class Container:
        id = "truncated-agent"
        labels = {"openatlas.job": job_id}
        attrs = {
            "Config": {
                "Cmd": [],
                "Env": ["CODEX_API_KEY=private-token-crossing-limit"],
            },
            "State": {"Running": True},
        }

        def reload(self):
            pass

        def top(self, **kwargs):
            return {}

        def logs(self, **kwargs):
            return b""

        def exec_run(self, args):
            return SimpleNamespace(exit_code=0, output=payload)

    store = DebugStore(tmp_path)
    capture(Container(), store, archive=True)
    saved = store.trace(job_id, Container.id)
    assert saved["retention"] == "truncated"
    assert saved["agent_log"] == "complete event"
    assert saved["byte_limit"] == 32
