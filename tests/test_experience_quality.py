import io
import json
import tarfile
from uuid import uuid4

import pytest

from openatlas.agent_session import session_archive, thread_id
from openatlas.agents import CodexAdapter
from openatlas.quality import (
    ReviewRequiresRepair,
    ReviewUnavailable,
    artifact_fingerprint,
    validate_review,
)


def archive(name, body=b"{}", symlink=False):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as tar:
        entry = tarfile.TarInfo(name)
        if symlink:
            entry.type, entry.linkname = tarfile.SYMTYPE, "/tmp/home/.codex/auth.json"
        else:
            entry.size = len(body)
        tar.addfile(entry, None if symlink else io.BytesIO(body))
    return stream.getvalue()


def test_session_history_is_private_bounded_and_redacted():
    cleaned = session_archive(
        archive("sessions/2026/turn.jsonl", b'{"text":"private-token"}'),
        ["private-token"],
    )
    with tarfile.open(fileobj=io.BytesIO(cleaned)) as tar:
        assert tar.getnames() == ["sessions/2026/turn.jsonl"]
        assert b"private-token" not in tar.extractfile(tar.getmembers()[0]).read()
    for name, link in [
        ("auth.json", False),
        ("sessions/../auth.json", False),
        ("sessions/link.jsonl", True),
        ("/sessions/a.jsonl", False),
    ]:
        with pytest.raises(ValueError):
            session_archive(archive(name, symlink=link))


def test_resume_uses_exact_job_session_and_keeps_medium_default():
    id = str(uuid4())
    assert thread_id(json.dumps({"type": "thread.started", "thread_id": id})) == id
    with pytest.raises(ValueError):
        thread_id('{"type":"thread.started","thread_id":"--last"}')
    adapter = CodexAdapter()
    request = {
        "model": "gpt-6-astra",
        "skills": [],
        "prompt": "Anatomy",
        "build_prompt": "Continuous hierarchical 3D anatomy",
        "validation_feedback": "Quiz timeout",
        "resume_session_id": id,
    }
    command = adapter.command(request)
    assert command[:3] == ["codex", "exec", "resume"]
    assert command[-2] == id
    assert "This is a repair" in command[-1]
    assert "new Notebook" not in command[-1]
    assert "fractional timeline" in command[-1] and "child GROUPS" in command[-1]
    assert not any("model_reasoning_effort" in part for part in command)
    assert any("mcp_servers.browser=" in part for part in command)


def test_manual_brief_cannot_skip_quality_and_review_is_independent():
    adapter = CodexAdapter()
    request = {
        "model": "gpt-6-astra",
        "skills": [],
        "prompt": "Anatomy",
        "build_prompt": "MY EXACT BRIEF",
    }
    assert "MY EXACT BRIEF" in adapter.prompt(request)
    assert "EXPERIENCE QUALITY" in adapter.prompt(request)
    review = adapter.command(dict(request, execution_stage="reviewing"))
    assert review[:2] == ["codex", "exec"] and "resume" not in review
    assert "--output-schema" in review
    assert "MY EXACT BRIEF" in review[-1]
    assert "Do not modify source" in review[-1]


def good_review(tmp_path):
    base = tmp_path / "source/review"
    base.mkdir(parents=True)
    for name in ["overview.png", "phone.png"]:
        (base / name).write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    return {
        "verdict": "pass",
        "summary": "Inspected",
        "criteria": [
            {
                "requirement": "Separate systems",
                "severity": "blocker",
                "change_reason": "",
                "passed": True,
                "observed": "All eight groups separate with their members",
                "evidence": "overview.png and root slider sweep",
            }
        ],
        "screenshots": [
            {"path": "overview.png", "purpose": "overview"},
            {"path": "phone.png", "purpose": "phone"},
        ],
        "motion": {
            "applicable": True,
            "normal_motion_tested": True,
            "observations": "Intermediate transforms while scrolling",
        },
    }


@pytest.mark.parametrize(
    "defect",
    ["failed_criterion", "reduced_only", "no_image_tools", "missing_image", "escape"],
)
def test_status_pass_cannot_override_missing_experience_evidence(tmp_path, defect):
    result = good_review(tmp_path)
    calls = 2
    if defect == "failed_criterion":
        result["criteria"][0]["passed"] = False
    if defect == "reduced_only":
        result["motion"]["normal_motion_tested"] = False
    if defect == "no_image_tools":
        calls = 0
    if defect == "missing_image":
        (tmp_path / "source/review/phone.png").unlink()
    if defect == "escape":
        result["screenshots"][0]["path"] = "../../manifest.json"
    with pytest.raises(ValueError):
        validate_review(result, tmp_path, calls)


def test_review_is_bound_to_artifact_and_accepts_complete_evidence(tmp_path):
    result = good_review(tmp_path)
    assert validate_review(result, tmp_path, 2)["verdict"] == "pass"
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist/index.html").write_text("working scene")
    (tmp_path / "manifest.json").write_text("{}")
    before = artifact_fingerprint(tmp_path)
    (tmp_path / "source/review/notes.txt").write_text("review notes")
    assert artifact_fingerprint(tmp_path) == before
    (tmp_path / "dist/index.html").write_text("broken scene")
    assert artifact_fingerprint(tmp_path) != before


def test_failed_experience_review_returns_to_builder_and_cannot_publish(
    tmp_path, monkeypatch
):
    from fastapi.testclient import TestClient

    from openatlas.api import create_app
    from openatlas.demo import generate
    from openatlas.repository import Repository
    from openatlas.runner import Runner

    repo = Repository(tmp_path / "data")
    client = TestClient(create_app(repo), base_url="http://localhost")

    class Agent:
        stages = []

        def run(self, root, request, progress):
            review = request.get("execution_stage") == "reviewing"
            self.stages.append("review" if review else "build")
            if review:
                raise ReviewRequiresRepair(
                    "Experience review requires repair: scroll freezes; only nine leaf meshes separate"
                )
            if len(self.stages) > 1:
                assert "scroll freezes" in request["validation_feedback"]
                assert "Preserve the original brief" in request["validation_feedback"]
            generate(root, request, progress)

    def mechanical(root):
        return json.loads((root / "manifest.json").read_text())

    monkeypatch.setattr("openatlas.runner.validate", mechanical)
    agent = Agent()
    job = client.post(
        "/api/jobs",
        json={
            "prompt": "Head atlas",
            "build_prompt": "Continuous head atlas",
            "planning_enabled": False,
            "provider": "codex",
            "skills_enabled": False,
        },
    ).json()

    class Planner:
        def run(self, *args):
            return "Build a continuous three-dimensional head atlas with hierarchical system separation."

    Runner(repo, executor=agent, planner=Planner()).process(repo.claim(1))
    assert repo.job(job["id"])["status"] == "failed"
    assert repo.library() == []
    assert agent.stages == ["build", "review", "build", "review", "build", "review"]
    assert repo.job(job["id"])["request"]["experience_review_required"] is True
    response = client.post(f"/api/jobs/{job['id']}/revalidate")
    assert response.status_code == 409
    assert "Use Continue" in response.json()["detail"]
    # Even a directly queued recovery cannot bypass the API policy.
    recovery = repo.enqueue(
        dict(repo.job(job["id"])["request"], revalidate_job=job["id"]),
        job["notebook_id"],
    )
    Runner(repo, executor=agent, planner=Planner()).process(repo.claim(1))
    assert repo.job(recovery["id"])["status"] == "failed"
    assert "Use Continue" in repo.job(recovery["id"])["error"]
    assert len(agent.stages) == 6
    assert repo.library() == []
    report = json.loads((repo.data / "validation" / job["id"] / "2.json").read_text())
    assert report["status"] == "failed"
    assert (
        report["checks"][0]["id"] == "experience"
        and report["checks"][0]["status"] == "failed"
    )


@pytest.mark.skipif(
    __import__("os").getenv("OPENATLAS_DOCKER_TEST") != "1",
    reason="Requires generation image",
)
def test_private_session_roundtrip_between_disposable_containers(tmp_path):
    from openatlas.demo import generate
    from openatlas.execution import DockerExecutor

    class Credentials:
        def connection(self):
            return {
                "api_key": "fixture-private-token",
                "base_url": "https://api.openai.com/v1",
            }

    identifier = str(uuid4())

    class Adapter(CodexAdapter):
        def command(self, request):
            if request.get("resume_session_id"):
                assert request["resume_session_id"] == identifier
                code = "from pathlib import Path; assert 'remember design' in Path('/tmp/home/.codex/sessions/fixture.jsonl').read_text(); Path('/workspace/source/resumed.txt').write_text('same design context')"
            else:
                code = "from pathlib import Path; p=Path('/tmp/home/.codex/sessions'); p.mkdir(parents=True); (p/'fixture.jsonl').write_text('remember design')"
            return [
                "python3",
                "-c",
                "import shutil,subprocess; shutil.copy2('/bin/true','/workspace/native-helper'); subprocess.run(['/workspace/native-helper'],check=True); "
                + code
                + "; print("
                + repr(json.dumps({"type": "thread.started", "thread_id": identifier}))
                + ")",
            ]

    request = {"job_id": str(uuid4()), "prompt": "Fixture", "skills": []}
    generate(tmp_path, request, lambda _: None)
    executor = DockerExecutor(Credentials(), adapter=Adapter())
    try:
        executor.run(tmp_path, request, lambda _: None)
        executor.run(
            tmp_path,
            dict(request, validation_feedback="Inspect previous design"),
            lambda _: None,
        )
        assert (tmp_path / "source/resumed.txt").read_text() == "same design context"
        assert not (tmp_path / "sessions").exists()
    finally:
        executor.release(request["job_id"])
    assert not executor._sessions


def test_suggestions_do_not_trigger_repairs(tmp_path):
    result = good_review(tmp_path)
    result["criteria"][0].update(
        passed=False, severity="suggestion", observed="Optional extra labels"
    )
    assert validate_review(result, tmp_path, 2)["verdict"] == "pass"
    result["verdict"] = "revise"
    with pytest.raises(ReviewUnavailable, match="without an evidenced blocker"):
        validate_review(result, tmp_path, 2)


def test_followup_keeps_checklist_and_explains_new_blockers(tmp_path):
    import copy

    result = good_review(tmp_path)
    previous = copy.deepcopy(result)
    result["criteria"][0]["requirement"] = "New aesthetic preference"
    with pytest.raises(ReviewUnavailable, match="omitted previous"):
        validate_review(result, tmp_path, 2, previous)
    result = copy.deepcopy(previous)
    result["criteria"][0]["passed"] = False
    with pytest.raises(ReviewUnavailable, match="grounded explanation"):
        validate_review(result, tmp_path, 2, previous)
    result = copy.deepcopy(previous)
    new = dict(result["criteria"][0], requirement="Search regression", passed=False)
    result["criteria"].append(new)
    with pytest.raises(ReviewUnavailable, match="grounded explanation"):
        validate_review(result, tmp_path, 2, previous)
    new["change_reason"] = (
        "The repaired search now leaves the old selection label visible; exact reproduction is in evidence."
    )
    with pytest.raises(ReviewRequiresRepair, match="Search regression"):
        validate_review(result, tmp_path, 2, previous)


@pytest.mark.parametrize(
    "failure",
    [ValueError("Usage limit reached"), ReviewUnavailable("Browser unavailable")],
)
def test_review_infrastructure_failure_preserves_build_without_repair(
    tmp_path, monkeypatch, failure
):
    from fastapi.testclient import TestClient

    from openatlas.api import create_app
    from openatlas.demo import generate
    from openatlas.repository import Repository
    from openatlas.runner import Runner

    repo = Repository(tmp_path / "data")
    client = TestClient(create_app(repo), base_url="http://localhost")
    stages = []

    class Agent:
        def run(self, root, request, progress):
            stage = request.get("execution_stage", "building")
            stages.append(stage)
            if stage == "reviewing":
                raise failure
            generate(root, request, progress)

    monkeypatch.setattr(
        "openatlas.runner.validate",
        lambda root: json.loads((root / "manifest.json").read_text()),
    )
    job = repo.enqueue(
        {
            "prompt": "Atlas",
            "provider": "codex",
            "skills": [],
            "planning_enabled": False,
        }
    )
    Runner(repo, executor=Agent()).process(repo.claim(1))
    assert stages == ["building", "reviewing"]
    assert repo.job(job["id"])["status"] == "failed"
    assert not repo.library()
    assert next(j for j in client.get("/api/jobs").json() if j["id"] == job["id"])[
        "can_continue"
    ]


def test_batched_findings_persist_into_targeted_followup_and_continue(
    tmp_path, monkeypatch
):
    from fastapi.testclient import TestClient

    from openatlas.api import create_app
    from openatlas.demo import generate
    from openatlas.repository import Repository
    from openatlas.runner import Runner

    repo = Repository(tmp_path / "data")
    client = TestClient(create_app(repo), base_url="http://localhost")
    criteria = [
        {
            "requirement": name,
            "severity": "blocker",
            "change_reason": "",
            "passed": False,
            "observed": "Broken",
            "evidence": "Reproduced",
        }
        for name in ("Labels", "Fullscreen", "Optic pathway")
    ]
    stages = []

    class Agent:
        def run(self, root, request, progress):
            stage = request.get("execution_stage", "building")
            stages.append(stage)
            if len(stages) > 2:
                assert request["experience_review_state"]["criteria"] == criteria
            if stage == "reviewing":
                if stages.count("reviewing") == 1:
                    raise ReviewRequiresRepair(
                        "Labels; Fullscreen; Optic pathway",
                        {"criteria": criteria, "summary": "Consolidated blockers"},
                    )
                raise ReviewUnavailable("Quota interrupted follow-up")
            if len(stages) > 1:
                assert all(
                    c["requirement"] in request["validation_feedback"] for c in criteria
                )
            generate(root, request, progress)

    monkeypatch.setattr(
        "openatlas.runner.validate",
        lambda root: json.loads((root / "manifest.json").read_text()),
    )
    job = repo.enqueue(
        {
            "prompt": "Atlas",
            "provider": "codex",
            "skills": [],
            "planning_enabled": False,
        }
    )
    Runner(repo, executor=Agent()).process(repo.claim(1))
    assert stages == ["building", "reviewing", "building", "reviewing"]
    assert (
        repo.job(job["id"])["request"]["experience_review_state"]["criteria"]
        == criteria
    )
    resumed = client.post(
        f"/api/jobs/{job['id']}/retry", json={"mode": "continue"}
    ).json()
    assert resumed["request"]["experience_review_state"]["criteria"] == criteria
    from openatlas.quality import review_scope, review_timeout

    assert "FOLLOW-UP" in review_scope(resumed["request"])
    assert review_timeout(resumed["request"]) < review_timeout({})
