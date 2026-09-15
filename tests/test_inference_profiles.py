import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from openatlas.api import create_app
from openatlas.credentials import DEFAULT_BASE_URL, Credentials
from openatlas.repository import Repository


@pytest.fixture
def client(tmp_path, monkeypatch):
    for key in (
        "OPENAI_API_KEY",
        "OPENATLAS_OPENAI_KEY_FILE",
        "OPENATLAS_API_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    return TestClient(create_app(Repository(tmp_path)), base_url="http://localhost")


def add(
    client,
    name="Gateway",
    key="third-party-token-A",
    url="https://provider.example/gateway/v2/",
):
    response = client.post(
        "/api/inference-profiles",
        json={
            "name": name,
            "base_url": url,
            "api_key": key,
            "activate": True,
        },
    )
    assert response.status_code == 201, response.text
    assert key not in response.text
    return response.json()["active_id"]


def test_profiles_switch_persist_and_never_return_keys(client, tmp_path):
    first = add(client)
    second = add(client, "Second key, same URL", "vendor-token-B")
    metadata = client.get("/api/inference-profiles").json()
    assert metadata["active_id"] == second
    assert len(metadata["profiles"]) == 3  # two saved plus host
    assert metadata["profiles"][0]["base_url"] == "https://provider.example/gateway/v2"
    assert (
        client.put(
            "/api/inference-profile-selection", json={"profile_id": first}
        ).status_code
        == 200
    )
    credentials = Credentials(tmp_path)
    assert credentials.connection() == {
        "api_key": "third-party-token-A",
        "base_url": "https://provider.example/gateway/v2",
    }
    assert credentials.profiles()["active_id"] == first
    assert credentials.profiles_path.stat().st_mode & 0o777 == 0o600
    assert credentials.directory.stat().st_mode & 0o777 == 0o700
    for route in ("/api/inference-profiles", "/api/credentials", "/api/settings"):
        text = client.get(route).text
        assert "third-party-token-A" not in text and "vendor-token-B" not in text
    assert client.get("/private/inference-profiles.json").status_code == 404
    database = (tmp_path / "openatlas.sqlite3").read_bytes()
    assert b"third-party-token-A" not in database and b"vendor-token-B" not in database
    # Simulate an app restart and switch back to the second stored key.
    restarted = TestClient(
        create_app(Repository(tmp_path)), base_url="http://localhost"
    )
    assert (
        restarted.put(
            "/api/inference-profile-selection", json={"profile_id": second}
        ).status_code
        == 200
    )
    assert Credentials(tmp_path).connection()["api_key"] == "vendor-token-B"


def test_edit_blank_key_preserves_key_and_delete_is_scoped(
    client, tmp_path, monkeypatch
):
    monkeypatch.setenv("OPENAI_API_KEY", "host-token")
    first = add(client)
    second = add(client, "Backup", "other-token")
    response = client.put(
        f"/api/inference-profiles/{first}",
        json={
            "name": "Renamed",
            "base_url": "http://host.docker.internal:1234/v1",
            "api_key": "",
        },
    )
    assert response.status_code == 200
    assert response.json()["active_id"] == second
    client.put("/api/inference-profile-selection", json={"profile_id": first})
    assert Credentials(tmp_path).connection() == {
        "api_key": "third-party-token-A",
        "base_url": "http://host.docker.internal:1234/v1",
    }
    # Removing an inactive profile does not change the active connection.
    assert (
        client.delete(f"/api/inference-profiles/{second}").json()["active_id"] == first
    )
    assert (
        client.delete(f"/api/inference-profiles/{first}").json()["active_id"] == "host"
    )
    assert Credentials(tmp_path).openai_key() == "host-token"
    assert client.delete("/api/inference-profiles/host").status_code == 422
    assert (
        client.put(
            "/api/inference-profile-selection", json={"profile_id": "missing"}
        ).status_code
        == 422
    )


def test_legacy_migration_preserves_existing_key_and_host_fallback(
    client, tmp_path, monkeypatch
):
    credentials = Credentials(tmp_path)
    credentials.directory.mkdir()
    credentials.path.write_text("sk-existing-key")
    monkeypatch.setenv("OPENAI_API_KEY", "host-token")
    assert credentials.profiles()["active_id"] == "openai"
    assert credentials.openai_key() == "sk-existing-key"
    added = add(client)
    assert not credentials.path.exists()
    client.put("/api/inference-profile-selection", json={"profile_id": "openai"})
    assert Credentials(tmp_path).openai_key() == "sk-existing-key"
    assert any(p["id"] == added for p in credentials.profiles()["profiles"])
    client.put("/api/inference-profile-selection", json={"profile_id": "host"})
    assert credentials.connection() == {
        "api_key": "host-token",
        "base_url": DEFAULT_BASE_URL,
    }


@pytest.mark.parametrize(
    "url",
    [
        "",
        "provider.example/v1",
        "file:///etc/passwd",
        "ftp://provider.example",
        "https://user:private-token@provider.example/v1",
        "https://provider.example/v1?key=private-token",
        "https://provider.example/v1#private-token",
        "https://provider.example:99999/v1",
        "https://provider.example/v1/\nheader",
        "https://provider.example/v1/responses",
        "https://provider.example/v1/chat/completions",
        "http://[broken/v1",
    ],
)
def test_invalid_url_is_rejected_without_echoing_input(client, url):
    response = client.post(
        "/api/inference-profiles",
        json={
            "name": "Gateway",
            "api_key": "third-party-token",
            "base_url": url,
        },
    )
    assert response.status_code == 422
    assert (
        "private-token" not in response.text
        and "third-party-token" not in response.text
    )
    assert len(client.get("/api/inference-profiles").json()["profiles"]) == 1


def test_profile_validation_and_origin_boundary(client):
    missing_url = client.post("/api/inference-profiles", json={
        "name": "Gateway", "api_key": "private-token-do-not-echo",
    })
    assert missing_url.status_code == 422
    assert "private-token-do-not-echo" not in missing_url.text
    for key in ("", "has spaces", "has\nnewline", "非ASCII", "x" * 4097):
        response = client.post(
            "/api/inference-profiles",
            json={
                "name": "Gateway",
                "api_key": key,
                "base_url": DEFAULT_BASE_URL,
            },
        )
        assert response.status_code == 422
    profile_id = add(client)
    for method, route, body in [
        (
            "POST",
            "/api/inference-profiles",
            {"name": "Evil", "base_url": DEFAULT_BASE_URL, "api_key": "evil"},
        ),
        ("PUT", "/api/inference-profile-selection", {"profile_id": "host"}),
        (
            "PUT",
            f"/api/inference-profiles/{profile_id}",
            {"name": "Evil", "base_url": DEFAULT_BASE_URL},
        ),
        ("DELETE", f"/api/inference-profiles/{profile_id}", None),
    ]:
        assert (
            client.request(
                method, route, json=body, headers={"Origin": "https://evil.example"}
            ).status_code
            == 403
        )


def test_custom_model_names_are_accepted_and_snapshotted(client):
    response = client.put(
        "/api/settings",
        json={
            "provider": "codex",
            "model": "vendor/coding-model:latest",
            "planner_model": "vendor/planning-model:v2",
            "concurrency": 1,
        },
    )
    assert response.status_code == 200
    job = client.post(
        "/api/jobs",
        json={"prompt": "Explain a flagellar motor", "skills_enabled": False},
    ).json()
    assert job["request"]["model"] == "vendor/coding-model:latest"
    assert job["request"]["planner_model"] == "vendor/planning-model:v2"
    assert "api_key" not in job["request"]


def test_simultaneous_saves_do_not_lose_profiles(tmp_path):
    def save(index):
        Credentials(tmp_path).save_profile(
            str(index), DEFAULT_BASE_URL, f"token-{index}"
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(save, range(16)))
    assert len(Credentials(tmp_path).profiles()["profiles"]) == 17


def test_running_job_keeps_connection_when_active_profile_changes(
    client, tmp_path, monkeypatch
):
    from openatlas.demo import generate
    from openatlas.execution import DockerExecutor
    from openatlas.runner import Runner

    first = add(client)
    second = add(client, "Second", "second-token", "https://second.example/v1")
    credentials = Credentials(tmp_path)
    credentials.activate(first)
    connections = []

    class Planner(DockerExecutor):
        def run(self, workspace, request, progress, connection=None):
            connections.append(connection)
            credentials.activate(second)
            assert "api_key" not in request
            return "Build a flagellar motor lesson with an interactive rotor and readable labels."

    class Builder(DockerExecutor):
        def run(self, workspace, request, progress, connection=None):
            connections.append(connection)
            assert "api_key" not in request
            generate(workspace, request, progress)

    def fixture_validation(root):
        (root / "validation.json").write_text('{"fixture": true}')
        return json.loads((root / "manifest.json").read_text())

    monkeypatch.setattr("openatlas.runner.validate", fixture_validation)
    repo = Repository(tmp_path)
    runner = Runner(repo, planner=Planner(credentials), executor=Builder(credentials))
    for _ in range(2):
        job = client.post(
            "/api/jobs",
            json={
                "prompt": "Explain a flagellar motor",
                "provider": "codex",
                "skills_enabled": False,
            },
        ).json()
        runner.process(repo.claim(2))
        assert repo.job(job["id"])["status"] == "succeeded"
    assert (
        connections[:2]
        == [
            {
                "api_key": "third-party-token-A",
                "base_url": "https://provider.example/gateway/v2",
            },
        ]
        * 2
    )
    assert (
        connections[2:]
        == [
            {"api_key": "second-token", "base_url": "https://second.example/v1"},
        ]
        * 2
    )
