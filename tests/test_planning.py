"""Durable orchestration tests; inference is substituted, never billed by tests."""

import pytest
from fastapi.testclient import TestClient

from openatlas.agents import CodexAdapter
from openatlas.api import create_app
from openatlas.planning import DEFAULT_PLANNER_INSTRUCTIONS, validate_prompt
from openatlas.repository import Repository
from openatlas.runner import Runner
from openatlas.skills import SkillCatalog

BRIEF = "Build a token journey: the learner changes the input text and watches token boundaries, scheduling and streamed output. Preserve the requested 3D GPU view."


class Planner:
    calls = 0

    def run(self, workspace, request, progress):
        self.calls += 1
        assert request["execution_stage"] == "planning"
        progress("Reading selected skills")
        return BRIEF


@pytest.fixture
def system(tmp_path):
    repo = Repository(tmp_path / "data")
    catalog = SkillCatalog(tmp_path / "skills")
    client = TestClient(create_app(repo, catalog), base_url="http://localhost")
    planner = Planner()
    runner = Runner(repo, catalog=catalog, planner=planner)
    return repo, catalog, client, planner, runner


def test_prompt_only_edit_build_reuse_and_restart(system):
    repo, _, client, planner, runner = system
    job = client.post(
        "/api/jobs",
        json={
            "prompt": "LLM inference in 3D",
            "provider": "codex",
            "prompt_only": True,
            "learner_background": "Python programmer",
        },
    ).json()
    runner.process(repo.claim(1))
    saved = repo.job(job["id"])
    assert saved["status"] == "succeeded" and saved["version_id"] is None
    assert saved["request"]["build_prompt"] == BRIEF
    plans = Repository(repo.data).plan_records(job["notebook_id"])
    assert plans[0]["inputs"]["learner_background"] == "Python programmer"
    first = plans[0]["revisions"][0]
    edited = client.post(
        "/api/prompts/" + first["id"] + "/edit",
        json={"content": BRIEF + " Use violet for GPU work."},
    ).json()
    assert edited["parent_id"] == first["id"]
    assert repo.prompt_revision(first["id"])["content"] == BRIEF
    built = client.post("/api/prompts/" + edited["id"] + "/build").json()

    class BrokenBuilder:
        def run(self, workspace, request, progress):
            assert request["prompt_revision_id"] == edited["id"]
            assert (
                repo.job(request["job_id"])["request"]["build_prompt"]
                == edited["content"]
            )
            raise ValueError("Builder test failure")

    runner.executor = BrokenBuilder()
    runner.process(repo.claim(1))
    assert planner.calls == 1
    assert repo.job(built["id"])["status"] == "failed"
    retry = client.post(
        "/api/jobs/" + built["id"] + "/retry", json={"mode": "rerun"}
    ).json()
    assert retry["request"]["prompt_revision_id"] == edited["id"]
    runner.process(repo.claim(1))
    assert planner.calls == 1
    assert len(repo.plan_records(job["notebook_id"])[0]["revisions"]) == 2


@pytest.mark.parametrize(
    "output", ["", None, "{}", "```html\n" + "x" * 100, "<!DOCTYPE html>" + "x" * 100]
)
def test_bad_output_never_builds(system, output):
    repo, _, client, _, runner = system

    class Bad:
        def run(self, *args):
            return output

    class Never:
        def run(self, *args):
            pytest.fail("Invalid plan started builder")

    runner.planner, runner.executor = Bad(), Never()
    job = client.post(
        "/api/jobs", json={"prompt": "Anatomy", "provider": "codex"}
    ).json()
    runner.process(repo.claim(1))
    assert repo.job(job["id"])["status"] == "failed"
    attempt = repo.plan_records(job["notebook_id"])[0]
    assert attempt["status"] == "failed" and "Planning failed" in attempt["error"]
    assert attempt["revisions"] == []
    retry = client.post("/api/jobs/" + job["id"] + "/retry", json={"mode": "rerun"})
    assert retry.status_code == 202


def test_configuration_snapshots_and_regeneration(system):
    repo, _, client, _, runner = system
    job = client.post(
        "/api/jobs",
        json={
            "prompt": "Reactor steam circuit",
            "provider": "codex",
            "prompt_only": True,
        },
    ).json()
    old = job["request"]["planner_instructions"]
    client.put(
        "/api/settings",
        json={
            "planner_instructions": "Design a historical exhibit",
            "planner_model": "gpt-test",
        },
    )
    runner.process(repo.claim(1))
    assert (
        repo.plan_records(job["notebook_id"])[0]["inputs"]["planner_instructions"]
        == old
    )
    new = client.post("/api/jobs/" + job["id"] + "/replan").json()
    assert new["request"]["planner_model"] == "gpt-test"
    runner.process(repo.claim(1))
    assert len(repo.plan_records(job["notebook_id"])) == 2
    assert (
        client.get("/api/prompt").json()["planner_default"]
        == DEFAULT_PLANNER_INSTRUCTIONS
    )


def test_skill_snapshot_survives_catalog_change(system, tmp_path):
    repo, catalog, client, _, runner = system
    skill = catalog.directory / "custom"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: custom\ndescription: Original guidance\n---\nRead notes.md"
    )
    (skill / "notes.md").write_text("Original support")
    job = client.post(
        "/api/jobs",
        json={
            "prompt": "Anatomy",
            "provider": "codex",
            "skills": ["local:custom"],
            "prompt_only": True,
        },
    ).json()
    (skill / "notes.md").write_text("Changed support")
    catalog.stage_snapshots(
        job["request"]["skills"], repo.data / "skill-inputs", tmp_path / "staged"
    )
    assert (
        tmp_path / "staged/local--custom/notes.md"
    ).read_text() == "Original support"
    runner.process(repo.claim(1))
    assert repo.job(job["id"])["status"] == "succeeded"


def test_interrupted_plan_and_cancel(system):
    repo, _, client, _, _ = system
    job = client.post(
        "/api/jobs", json={"prompt": "Anatomy", "provider": "codex"}
    ).json()
    repo.claim(1)
    repo.start_plan(job["id"], job["request"])
    with repo.engine.begin() as c:
        c.exec_driver_sql("UPDATE jobs SET lease_until=0")
    repo.claim(1)
    assert repo.plan_records(job["notebook_id"])[0]["status"] == "failed"
    job2 = client.post("/api/jobs", json={"prompt": "Anatomy"}).json()
    assert (
        client.post("/api/jobs/" + job2["id"] + "/cancel").json()["status"] == "failed"
    )
    assert repo.claim(1) is None


def test_creative_prompt_does_not_append_legacy_teaching():
    assembled = CodexAdapter().prompt(
        {
            "prompt": "Anatomy in 3D",
            "skills": [],
            "build_prompt": BRIEF,
            "teaching_prompt": "LEGACY LAYOUT",
        }
    )
    assert BRIEF in assembled and "LEGACY LAYOUT" not in assembled
    assert (
        "sandbox=allow-scripts" in assembled and "/workspace/manifest.json" in assembled
    )
    assert validate_prompt(BRIEF) == BRIEF


def test_planner_command_preserves_inputs_and_enforces_skill_reads():
    import json

    from openatlas.planning import PlannerAdapter

    request = {
        "prompt": "Explore anatomy in 3D",
        "planner_model": "chosen-model",
        "planner_instructions": "Design an anatomy exhibit.",
        "skills": [],
        "learner_background": "Beginner",
        "reading_minutes": 30,
        "instructions": "Include spatial relationships",
    }
    command = PlannerAdapter().command(request)
    assert command[2] == "chosen-model"
    assert request["planner_instructions"] in command[3]
    assert "Read all selected SKILL.md" in command[3]
    inputs = json.loads(command[-1])
    assert inputs["prompt"] == request["prompt"]
    assert inputs["learner_background"] == "Beginner"
    assert inputs["reading_minutes"] == 30
    assert inputs["instructions"] == request["instructions"]
