import os

from fastapi.testclient import TestClient

from openatlas.api import create_app
from openatlas.credentials import Credentials
from openatlas.repository import Repository
from openatlas.runner import Runner


def test_credentials_are_write_only_persistent_and_shared(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENATLAS_OPENAI_KEY_FILE", raising=False)
    repo = Repository(tmp_path)
    client = TestClient(create_app(repo), base_url="http://localhost")
    key = "sk-test-only-not-a-real-credential"
    assert client.get("/api/credentials").json()["configured"] is False
    response = client.put("/api/credentials", json={"api_key": key})
    assert response.status_code == 200
    assert response.json() == {"configured": True, "source": "saved"}
    assert key not in response.text
    assert key not in client.get("/api/settings").text
    assert key not in client.get("/api/credentials").text
    assert Credentials(tmp_path).openai_key() == key
    assert Runner(repo).executor.credentials.openai_key() == key
    if os.name != "nt":
        assert Credentials(tmp_path).profiles_path.stat().st_mode & 0o777 == 0o600
    assert client.get("/private/openai-key").status_code == 404
    assert client.delete("/api/credentials").json()["configured"] is False
    assert not Credentials(tmp_path).path.exists()


def test_credentials_validation_and_origin_boundary(tmp_path):
    client = TestClient(create_app(Repository(tmp_path)), base_url="http://localhost")
    invalid = "private invalid key"
    response = client.put("/api/credentials", json={"api_key": invalid})
    assert response.status_code == 422
    assert invalid not in response.text
    for origin in ["null", "https://evil.example"]:
        assert (
            client.put(
                "/api/credentials",
                json={"api_key": "sk-test-only-credential"},
                headers={"Origin": origin},
            ).status_code
            == 403
        )
        assert (
            client.delete("/api/credentials", headers={"Origin": origin}).status_code
            == 403
        )


def test_saved_key_overrides_host_and_removal_restores_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENATLAS_OPENAI_KEY_FILE", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-environment-test")
    credentials = Credentials(tmp_path)
    credentials.save("sk-saved-first-test")
    credentials.save("sk-saved-second-test")
    assert credentials.openai_key() == "sk-saved-second-test"
    credentials.remove()
    assert credentials.openai_key() == "sk-environment-test"
    assert credentials.status()["source"] == "environment"


def test_astra_default_and_model_selection_persist(tmp_path):
    repo = Repository(tmp_path)
    client = TestClient(create_app(repo), base_url="http://localhost")
    assert client.get("/api/settings").json()["model"] == "gpt-6-astra"
    assert client.get("/api/models").json()[0] == {
        "id": "gpt-6-astra",
        "name": "GPT-6 Astra",
        "default": True,
    }
    settings = {"provider": "demo", "model": "gpt-5.6-sol", "concurrency": 2}
    assert client.put("/api/settings", json=settings).status_code == 200
    assert Repository(tmp_path).settings()["model"] == "gpt-5.6-sol"
    job = client.post("/api/jobs", json={"prompt": "Teach me binary search"}).json()
    assert job["request"]["model"] == "gpt-5.6-sol"


def test_stock_planner_upgrade_preserves_custom_and_snapshot(tmp_path):
    from pathlib import Path

    from openatlas.planning import DEFAULT_PLANNER_INSTRUCTIONS

    repo = Repository(tmp_path)
    saved = repo.settings()
    saved["planner_instructions"] = (Path(__file__).parent / "fixtures/legacy-planner-instructions.txt").read_text()
    repo.save_settings(saved)
    assert Repository(tmp_path).settings()["planner_instructions"] == DEFAULT_PLANNER_INSTRUCTIONS
    saved["planner_instructions"] = "Use a custom visual direction and respect my topic."
    repo.save_settings(saved)
    assert Repository(tmp_path).settings()["planner_instructions"] == saved["planner_instructions"]
