import pytest
from fastapi.testclient import TestClient

from openatlas.agents import CodexAdapter
from openatlas.api import create_app
from openatlas.repository import Repository


def test_reading_duration_defaults_bounds_and_job_snapshot(tmp_path):
    client = TestClient(create_app(Repository(tmp_path)), base_url="http://localhost")
    assert (
        client.post("/api/jobs", json={"prompt": "Teach me memory"}).json()["request"][
            "reading_minutes"
        ]
        == 20
    )
    for minutes in (5, 50):
        assert (
            client.post(
                "/api/jobs",
                json={"prompt": "Teach me memory", "reading_minutes": minutes},
            ).json()["request"]["reading_minutes"]
            == minutes
        )
    for invalid in (0, 4, 51, True, 7.5, "50"):
        assert (
            client.post(
                "/api/jobs",
                json={"prompt": "Teach me memory", "reading_minutes": invalid},
            ).status_code
            == 422
        )


@pytest.mark.parametrize("minutes", [5, 20, 50])
def test_agent_receives_duration_and_design_contract(minutes):
    request = {"prompt": "Teach me caching", "skills": [], "reading_minutes": minutes}
    prompt = CodexAdapter().prompt(request)
    assert f"approximately {minutes} minutes" in prompt
    assert f"target_reading_minutes={minutes}" in prompt
    assert "Contents button" in prompt and "4.5:1" in prompt
    assert "1 and 30 publication checks" in prompt


def test_skill_free_generation_and_revision_inheritance(tmp_path):
    repo = Repository(tmp_path)
    client = TestClient(create_app(repo), base_url="http://localhost")
    job = client.post("/api/jobs", json={"prompt": "Teach inference", "skills_enabled": False, "skills": ["missing:skill"]}).json()
    assert job["request"]["skills"] == []
    assert job["request"]["skills_enabled"] is False
    claimed = repo.claim(2)
    from openatlas.repository import uid
    repo.publish(claimed, uid(), {"title": "Inference", "entrypoint": "index.html"})
    revised = client.post(f'/api/notebooks/{job["notebook_id"]}/revisions', json={"prompt": "Explain more"}).json()
    assert revised["request"]["skills"] == []
    assert revised["request"]["skills_enabled"] is False
    default = client.post("/api/jobs", json={"prompt": "Teach memory"}).json()
    assert default["request"]["skills"][0]["id"] == "builtin:openatlas-core"
