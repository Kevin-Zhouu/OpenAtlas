import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from openatlas.api import create_app
from openatlas.debug import DebugStore, capture
from openatlas.repository import Repository


def test_debug_capture_redacts_and_retains_only_safe_fields(tmp_path):
    job_id = str(uuid4())
    key = "sk-test-secret-do-not-expose"
    token = "private-relay-test-token"

    class Container:
        id = "a" * 64
        labels = {"openatlas.job": job_id}
        attrs = {
            "Config": {
                "Image": "test-image",
                "Cmd": ["sleep", "infinity"],
                "Env": ["OPENAI_API_KEY=" + key, "CODEX_API_KEY=" + token],
            },
            "State": {"Running": True, "Status": "running"},
            "HostConfig": {
                "Memory": 2048,
                "NanoCpus": 2000000000,
                "ReadonlyRootfs": True,
                "Binds": ["/secret:/secret"],
            },
        }

        def reload(self):
            pass

        def top(self, ps_args):
            assert ps_args == "-eo pid,comm"
            return {"Processes": [["1", "codex"]]}

        def exec_run(self, args):
            assert args == ["tail", "-c", "131072", "/tmp/codex-output.log"]
            return SimpleNamespace(exit_code=0, output=(key + "\n" + token).encode())

        def logs(self, tail):
            assert tail == 100
            return ("Bearer " + token).encode()

    store = DebugStore(tmp_path)
    capture(Container(), store)
    data = DebugStore(tmp_path).read(job_id)
    serialized = json.dumps(data)
    assert key not in serialized and token not in serialized
    assert "Env" not in serialized and "Binds" not in serialized
    assert data["containers"][0]["processes"] == [["1", "codex"]]
    assert "[redacted]" in serialized
    capture(Container(), store, removed=True)
    assert store.read(job_id)["containers"][0]["status"] == "removed"


def test_debug_snapshots_atomic_bounded_and_api_access(tmp_path, monkeypatch):
    repo = Repository(tmp_path)
    client = TestClient(create_app(repo), base_url="http://localhost")
    job = client.post("/api/jobs", json={"prompt": "Teach me caching"}).json()

    def save(i):
        DebugStore(tmp_path).record(job["id"], {"id": str(i), "observed_at": str(i)})

    with ThreadPoolExecutor(4) as pool:
        list(pool.map(save, range(20)))
    response = client.get("/api/jobs/" + job["id"] + "/debug")
    assert response.status_code == 200
    assert len(response.json()["containers"]) == 16
    assert response.json()["job"]["status"] == "queued"
    assert client.get("/api/jobs/" + str(uuid4()) + "/debug").status_code == 404
    assert client.get("/debug/" + job["id"] + ".json").status_code == 404
    monkeypatch.setenv("OPENATLAS_ACCESS_TOKEN", "host-test-token")
    protected = TestClient(create_app(repo), base_url="http://localhost")
    assert protected.get("/api/jobs/" + job["id"] + "/debug").status_code == 401
