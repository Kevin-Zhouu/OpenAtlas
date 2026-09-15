import io
import tarfile
import threading
import time

import pytest
from fastapi.testclient import TestClient

from openatlas.api import create_app
from openatlas.credentials import Credentials
from openatlas.execution import extract_output
from openatlas.repository import Repository
from openatlas.subscription import SubscriptionStore, SubscriptionWorker, auth_secrets


def fake_auth(value="fixture-token"):
    return {
        "auth_mode": "chatgpt",
        "tokens": {
            "access_token": value,
            "refresh_token": "fixture-refresh",
            "id_token": "fixture-id",
            "account_id": "fixture-account",
        },
    }


def signed_in(store):
    store.start()
    epoch = store._read()["epoch"]
    store.update(
        epoch,
        status="signed_in",
        auth=fake_auth(),
        email="fixture@example.com",
        plan="pro",
    )
    return epoch


def test_login_api_is_private_and_never_exposes_tokens(tmp_path):
    repo = Repository(tmp_path)
    client = TestClient(create_app(repo), base_url="http://localhost")
    store = SubscriptionStore(tmp_path)
    assert client.get("/api/subscription").json()["status"] == "signed_out"
    assert client.post("/api/subscription/login").status_code == 503
    store.heartbeat()
    assert client.post("/api/subscription/login").status_code == 202
    epoch = store._read()["epoch"]
    assert client.post("/api/subscription/login").status_code == 202
    assert store._read()["epoch"] == epoch
    store.update(
        epoch,
        status="waiting",
        verification_url="https://auth.openai.com/codex/device",
        user_code="ABCD-1234",
    )
    assert client.get("/api/subscription").json()["user_code"] == "ABCD-1234"
    store.update(
        epoch,
        status="signed_in",
        auth=fake_auth(),
        email="fixture@example.com",
        plan="pro",
    )
    response = client.get("/api/subscription")
    assert response.json()["email"] == "fixture@example.com"
    assert response.json()["plan"] == "pro"
    assert "user_code" not in response.json()
    for secret in auth_secrets(fake_auth()):
        assert secret not in response.text
        assert secret not in client.get("/api/settings").text
    assert client.post("/api/subscription/login").status_code == 409
    assert client.get("/private/subscription.json").status_code == 404
    assert store.path.stat().st_mode & 0o777 == 0o600
    assert client.delete("/api/subscription").json()["status"] == "signed_out"
    assert "auth" not in store._read()
    assert not store.refresh(epoch, fake_auth("late-refresh"))
    assert not store.update(epoch, status="signed_in", auth=fake_auth())
    assert "auth" not in store._read()
    for verb, path in [
        ("POST", "/api/subscription/login"),
        ("DELETE", "/api/subscription"),
    ]:
        assert (
            client.request(
                verb, path, headers={"Origin": "https://evil.example"}
            ).status_code
            == 403
        )


def test_session_refresh_restart_and_no_api_fallback(tmp_path):
    store = SubscriptionStore(tmp_path)
    epoch = signed_in(store)
    assert store.refresh(epoch, fake_auth("refreshed-access"))
    assert (
        SubscriptionStore(tmp_path).session()["auth"]["tokens"]["access_token"]
        == "refreshed-access"
    )
    Credentials(tmp_path).save("fallback-api-key")
    store.sign_out()
    with pytest.raises(ValueError, match="API keys will not be used"):
        store.session()
    next_epoch = signed_in(store)
    assert next_epoch != epoch
    assert not store.refresh(epoch, fake_auth("stale-access"))
    assert store.session()["auth"]["tokens"]["access_token"] == "fixture-token"


def test_expiry_and_cancel_invalidate_pending_login(tmp_path):
    store = SubscriptionStore(tmp_path)
    store.start()
    epoch = store._read()["epoch"]
    store.update(epoch, expires_at=time.time() - 1)
    assert store.status()["status"] == "error"
    SubscriptionWorker(store).tick()
    assert store.status()["status"] == "error"
    store.start()
    assert store._read()["epoch"] != epoch
    store.sign_out()
    assert not store.update(epoch, status="signed_in", auth=fake_auth())


def test_auth_mode_saved_and_retries_use_current_mode(tmp_path):
    repo = Repository(tmp_path)
    client = TestClient(create_app(repo), base_url="http://localhost")
    job = client.post(
        "/api/jobs",
        json={
            "prompt": "Explain a motor",
            "provider": "codex",
            "skills_enabled": False,
        },
    ).json()
    assert job["request"]["inference_auth"] == "api_key"
    settings = client.get("/api/settings").json()
    settings["inference_auth"] = "chatgpt"
    assert client.put("/api/settings", json=settings).status_code == 200
    assert Repository(tmp_path).settings()["inference_auth"] == "chatgpt"
    repo.claim(2)
    repo.fail(job["id"], "old API error")
    retried = client.post(f"/api/jobs/{job['id']}/retry", json={"mode": "rerun"}).json()
    assert retried["request"]["inference_auth"] == "chatgpt"
    assert "auth" not in retried["request"]
    assert (
        client.put(
            "/api/settings", json={"provider": "codex", "inference_auth": "other"}
        ).status_code
        == 422
    )


def test_credential_containing_artifacts_are_rejected(tmp_path):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as archive:
        content = b"private subscription fixture-token"
        entry = tarfile.TarInfo("workspace/source/leaked.txt")
        entry.size = len(content)
        archive.addfile(entry, io.BytesIO(content))
    with pytest.raises(ValueError, match="private credential"):
        extract_output([data.getvalue()], tmp_path, ["fixture-token"])
    assert not (tmp_path / "source/leaked.txt").exists()


def test_subscription_jobs_serialize_and_respect_signout(tmp_path, monkeypatch):
    from openatlas.execution import DockerExecutor
    from openatlas.runner import Runner

    repo = Repository(tmp_path)
    store = SubscriptionStore(tmp_path)
    signed_in(store)
    entered, release = threading.Event(), threading.Event()
    calls = []

    class Planner(DockerExecutor):
        def run(self, root, request, progress, connection=None):
            assert connection["mode"] == "chatgpt"
            assert "api_key" not in connection
            calls.append(request["job_id"])
            entered.set()
            release.wait(5)
            return (
                "Build a motor lesson with clearly labeled rotor and stator components."
            )

    runner = Runner(repo, planner=Planner(Credentials(tmp_path)))
    request = dict(
        prompt="Explain a motor",
        provider="codex",
        inference_auth="chatgpt",
        skills=[],
        planning_enabled=True,
        prompt_only=True,
        planner_model="test",
    )
    repo.enqueue(request)
    second = repo.enqueue(request)
    jobs = [repo.claim(2), repo.claim(2)]
    threads = [threading.Thread(target=runner.process, args=(job,)) for job in jobs]
    threads[0].start()
    assert entered.wait(3)
    threads[1].start()
    time.sleep(0.1)
    assert len(calls) == 1
    store.sign_out()
    release.set()
    for thread in threads:
        thread.join(5)
    assert len(calls) == 1  # queued job never silently uses the saved API key
    assert repo.job(second["id"])["status"] == "failed"
    assert "Sign in with ChatGPT" in repo.job(second["id"])["error"]


@pytest.mark.parametrize("finish", ["complete", "cancel", "bad_url"])
def test_worker_device_login_lifecycle(tmp_path, finish):
    import json
    from types import SimpleNamespace

    store = SubscriptionStore(tmp_path)
    store.start()
    events = [
        {
            "type": "login.waiting",
            "verification_url": "https://auth.openai.com/codex/device",
            "user_code": "ABCD-1234",
        }
    ]
    removed = []
    container = SimpleNamespace(
        reload=lambda: None,
        logs=lambda **kwargs: "\n".join(json.dumps(e) for e in events).encode(),
        status="running",
        exec_run=lambda args: SimpleNamespace(
            exit_code=0, output=json.dumps(fake_auth()).encode()
        ),
        remove=lambda **kwargs: removed.append(True),
    )

    def launch(image, command, **kwargs):
        assert command == ["python3", "/opt/subscription_login.py"]
        assert "volumes" not in kwargs
        assert "CODEX_API_KEY" not in kwargs["environment"]
        assert kwargs["read_only"]
        return container

    worker = SubscriptionWorker(
        store, SimpleNamespace(containers=SimpleNamespace(run=launch))
    )
    worker.tick()
    assert store.status()["status"] == "waiting"
    assert store.status()["user_code"] == "ABCD-1234"
    if finish == "complete":
        events.append(
            {"type": "login.completed", "email": "fixture@example.com", "plan": "pro"}
        )
        worker.tick()
        assert store.session()["auth"] == fake_auth()
        assert "user_code" not in store.status()
    elif finish == "cancel":
        store.sign_out()
        events.append({"type": "login.completed"})
        worker.tick()
        assert store.status()["status"] == "signed_out"
        assert "auth" not in store._read()
    else:
        events[0]["verification_url"] = "https://evil.example/"
        with pytest.raises(ValueError, match="Unexpected device login"):
            worker.tick()
        worker.cleanup()
    assert removed == [True]


def test_executor_subscription_selection_never_falls_back(tmp_path):
    from openatlas.execution import DockerExecutor

    credentials = Credentials(tmp_path)
    credentials.save("unused-api-key")
    with pytest.raises(ValueError, match="Sign in with ChatGPT"):
        DockerExecutor(credentials).run(
            tmp_path, {"inference_auth": "chatgpt"}, lambda _: None
        )


def test_login_helper_uses_official_account_rpc(tmp_path, monkeypatch, capsys):
    import importlib.util
    import json
    from pathlib import Path
    from types import SimpleNamespace

    spec = importlib.util.spec_from_file_location(
        "subscription_login",
        Path(__file__).parents[1] / "generation/subscription_login.py",
    )
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "home"))
    stdin = io.StringIO()
    messages = [
        {"id": 1, "result": {}},
        {
            "id": 2,
            "result": {
                "loginId": "fixture-login",
                "verificationUrl": "https://auth.openai.com/codex/device",
                "userCode": "ABCD-1234",
            },
        },
        {
            "method": "account/login/completed",
            "params": {"loginId": "different-login", "success": True},
        },
        {
            "method": "account/login/completed",
            "params": {"loginId": "fixture-login", "success": True},
        },
        {
            "id": 3,
            "result": {
                "account": {
                    "type": "chatgpt",
                    "email": "fixture@example.com",
                    "planType": "pro",
                }
            },
        },
    ]
    process = SimpleNamespace(
        stdin=stdin,
        stdout=[json.dumps(m) for m in messages],
        wait=lambda **kwargs: 0,
        terminate=lambda: None,
    )
    monkeypatch.setattr(helper.subprocess, "Popen", lambda command, **kwargs: process)
    helper.main()
    requests = [json.loads(line) for line in stdin.getvalue().splitlines()]
    assert [m["method"] for m in requests] == [
        "initialize",
        "initialized",
        "account/login/start",
        "account/read",
    ]
    assert requests[2]["params"] == {"type": "chatgptDeviceCode"}
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [e["type"] for e in events] == ["login.waiting", "login.completed"]
    assert events[-1]["email"] == "fixture@example.com"
    assert events[-1]["plan"] == "pro"
