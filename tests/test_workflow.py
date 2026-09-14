import io
import json
import tarfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from openatlas.agents import CodexAdapter
from openatlas.api import create_app
from openatlas.artifacts import ArtifactStore, validate
from openatlas.demo import generate
from openatlas.execution import archive_input, extract_output
from openatlas.repository import Repository
from openatlas.runner import Runner
from openatlas.skills import SkillCatalog


@pytest.fixture
def system(tmp_path):
    repo = Repository(tmp_path / "data")
    catalog = SkillCatalog(tmp_path / "skills")
    store = ArtifactStore(repo.data)
    client = TestClient(create_app(repo, catalog, store), base_url="http://localhost")
    class Planner:
        def run(self, *args):
            return "Build an explorable lesson about the requested topic with meaningful visual explanations and controls."
    runner = Runner(repo, store, catalog, planner=Planner())
    return repo, catalog, store, client, runner


def test_full_publication_revision_and_restart(system):
    repo, catalog, store, client, runner = system
    response = client.post(
        "/api/jobs",
        json={
            "prompt": "Teach me caching",
            "skills": ["builtin:visual-explainer"],
            "reading_minutes": 50,
        },
    )
    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "queued" and repo.library() == []
    runner.process(repo.claim(2))
    finished = repo.job(job["id"])
    assert finished["status"] == "succeeded", finished
    n = client.get("/api/notebooks/" + job["notebook_id"]).json()
    v = n["versions"][0]
    assert {s["id"] for s in v["provenance"]} == {
        "builtin:openatlas-core",
        "builtin:blender",
        "builtin:visual-explainer",
    }
    url = f"/artifacts/{n['id']}/{v['id']}/index.html"
    artifact = client.get(url)
    assert artifact.status_code == 200 and "Demo content" in artifact.text
    assert "sandbox allow-scripts;" in artifact.headers["content-security-policy"]
    assert "allow-same-origin" not in artifact.headers["content-security-policy"]
    assert store.version_path(n["id"], v["id"]).joinpath("source/index.html").exists()
    rev = client.post(
        "/api/notebooks/" + n["id"] + "/revisions",
        json={"prompt": "Make it more visual"},
    ).json()
    assert v["manifest"]["target_reading_minutes"] == 50
    assert rev["request"]["reading_minutes"] == 50
    assert rev["request"]["base_version"] == v["id"]
    assert rev["request"]["skills"] == v["provenance"]
    runner.process(repo.claim(2))
    restarted = Repository(repo.data)
    assert len(restarted.notebook(n["id"])["versions"]) == 2
    assert len(restarted.library()) == 1
    assert client.get(url).text == artifact.text
    assert (
        client.get(
            f"/artifacts/{n['id']}/{v['id']}/%2e%2e/source/index.html"
        ).status_code
        == 404
    )
    assert client.get("/.data/openatlas.sqlite3").status_code == 404


def test_concurrent_claims_and_generation(system):
    repo, _, _, client, runner = system
    for topic in ["Learn caching", "Learn queues", "Learn memory"]:
        client.post("/api/jobs", json={"prompt": topic})
    with ThreadPoolExecutor(max_workers=3) as pool:
        claimed = list(pool.map(lambda _: repo.claim(2), range(3)))
    jobs = [j for j in claimed if j]
    assert len(jobs) == 2 and jobs[0]["id"] != jobs[1]["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(runner.process, jobs))
    assert all(repo.job(j["id"])["status"] == "succeeded" for j in jobs)
    assert repo.claim(2)


def test_skills_malformed_selection_and_changed_snapshot(system, tmp_path):
    repo, catalog, _, client, _ = system
    folder = catalog.directory / "test-skill"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text("broken")
    skills = client.get("/api/skills").json()
    assert next(s for s in skills if s["id"] == "local:test-skill")["valid"] is False
    assert (
        client.post(
            "/api/jobs",
            json={"prompt": "Learn something", "skills": ["local:test-skill"]},
        ).status_code
        == 422
    )
    (folder / "SKILL.md").write_text(
        '---\nname: test-skill\ndescription: A test skill\nmetadata:\n  version: "2"\n---\nTeach well.'
    )
    selected = catalog.resolve(["local:test-skill"])
    catalog.stage(selected, tmp_path / "staged")
    assert sorted(p.name for p in (tmp_path / "staged").iterdir()) == [
        "builtin--blender",
        "builtin--openatlas-core",
        "local--test-skill",
    ]
    (folder / "SKILL.md").write_text("changed")
    with pytest.raises(ValueError):
        catalog.stage(selected, tmp_path / "changed")


def test_symlink_skill_rejected(system, tmp_path):
    _, catalog, _, _, _ = system
    folder = catalog.directory / "linked"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").symlink_to(tmp_path / "outside")
    assert (
        next(s for s in catalog.discover() if s["id"] == "local:linked")["valid"]
        is False
    )


def test_csrf_and_settings(system):
    _, _, _, client, _ = system
    assert (
        client.post(
            "/api/jobs", json={"prompt": "Learn caching"}, headers={"Origin": "null"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/jobs",
            json={"prompt": "Learn caching"},
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    assert client.put("/api/settings", json={"concurrency": 9}).status_code == 422
    assert (
        client.post(
            "/api/jobs", json={"prompt": "Learn", "provider": "unknown"}
        ).status_code
        == 422
    )
    assert client.get("/api/jobs", headers={"Host": "evil.example"}).status_code == 400


def test_expired_lease_failure(system):
    repo, _, _, client, _ = system
    id = client.post("/api/jobs", json={"prompt": "Learn caching"}).json()["id"]
    repo.claim(1)
    with repo.engine.begin() as c:
        c.exec_driver_sql("UPDATE jobs SET lease_until=0")
    assert repo.claim(1) is None
    assert repo.job(id)["status"] == "failed"


def test_failed_real_job_never_falls_back(system):
    repo, _, _, client, runner = system

    class Broken:
        def run(self, *args):
            raise ValueError("No provider configured")

    runner.executor = Broken()
    id = client.post(
        "/api/jobs", json={"prompt": "Learn caching", "provider": "codex"}
    ).json()["id"]
    runner.process(repo.claim(1))
    assert repo.job(id)["status"] == "failed"
    assert repo.library() == []


def test_archive_rejects_traversal(tmp_path):
    for name in ["workspace/source/../../../escape", "workspace/dist/link"]:
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w") as tar:
            info = tarfile.TarInfo(name)
            if name.endswith("link"):
                info.type = tarfile.SYMTYPE
                info.linkname = "/etc/passwd"
            tar.addfile(info)
        with pytest.raises(ValueError):
            extract_output([stream.getvalue()], tmp_path / "out")


def test_codex_explicit_skills_and_ownership(system, tmp_path):
    _, catalog, _, _, _ = system
    request = {
        "prompt": "Teach trees",
        "skills": catalog.resolve(["builtin:visual-explainer"]),
        "model": "gpt-5.3-codex",
    }
    adapter = CodexAdapter()
    assert "Before planning, READ" in adapter.prompt(request)
    assert "3d-explorer" not in adapter.prompt(request)
    assert adapter.command(request)[:2] == ["codex", "exec"]
    (tmp_path / "source").mkdir()
    (tmp_path / "source/index.html").write_text("test")
    with tarfile.open(fileobj=io.BytesIO(archive_input(tmp_path))) as tar:
        assert all(m.uid == 1000 for m in tar)


def test_nonrenderable_and_broken_interaction_rejected(tmp_path):
    (tmp_path / "source").mkdir()
    (tmp_path / "dist").mkdir()
    (tmp_path / "source/lesson.md").write_text("Not a web Notebook")
    (tmp_path / "dist/index.html").write_text("Just markdown")
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {"title": "Not a Notebook", "entrypoint": "index.html", "checks": []}
        )
    )
    with pytest.raises(ValueError, match="HTML"):
        validate(tmp_path)
    generate(tmp_path, {"prompt": "test"}, lambda _: None)
    s = (
        (tmp_path / "dist/index.html")
        .read_text()
        .replace("cached=!cached;render()", "cached=cached;render()")
    )
    (tmp_path / "dist/index.html").write_text(s)
    with pytest.raises(ValueError, match="Interaction check 1 failed"):
        validate(tmp_path)


def test_codex_publication_failure_gets_one_repair(system):
    repo, _, store, client, runner = system

    class RepairableAgent:
        calls = 0

        def run(self, workspace, request, progress):
            self.calls += 1
            if self.calls == 1:
                generate(workspace, request, progress)
                path = workspace / "manifest.json"
                manifest = json.loads(path.read_text())
                manifest["entrypoint"] = "dist/index.html"
                path.write_text(json.dumps(manifest))
            else:
                assert "relative to dist" in request["validation_feedback"]
                path = workspace / "manifest.json"
                manifest = json.loads(path.read_text())
                manifest["entrypoint"] = "index.html"
                path.write_text(json.dumps(manifest))

    agent = RepairableAgent()
    runner.executor = agent
    job = client.post(
        "/api/jobs", json={"prompt": "Explain binary search", "provider": "codex"}
    ).json()
    runner.process(repo.claim(1))
    assert agent.calls == 2
    saved_request = repo.job(job['id'])['request']
    published = repo.notebook(job['notebook_id'])['versions'][0]['manifest']
    assert published['planning_attempt_id'] == saved_request['planning_attempt_id']
    assert published['prompt_revision_id'] == saved_request['prompt_revision_id']
    revision = client.post(
        "/api/notebooks/" + job["notebook_id"] + "/revisions",
        json={"prompt": "Improve the lesson"},
    ).json()
    assert revision["request"]["provider"] == "codex"  # Global setting is still demo.
    assert repo.job(job["id"])["status"] == "succeeded"
    assert (store.root.parent / "failed" / job["id"] / "0" / "manifest.json").exists()
    assert client.get("/failed/" + job["id"] + "/0/manifest.json").status_code == 404


def test_parallel_initial_migrations(tmp_path):
    with ThreadPoolExecutor(max_workers=2) as pool:
        repos = list(pool.map(lambda _: Repository(tmp_path / "new"), range(2)))
    assert all(r.settings()["concurrency"] == 2 for r in repos)
    assert len(repos[0].rows("SELECT * FROM schema_migrations")) == 4


def test_shared_access_token(system, monkeypatch):
    repo, catalog, store, _, _ = system
    monkeypatch.setenv("OPENATLAS_ACCESS_TOKEN", "local-test-token")
    client = TestClient(create_app(repo, catalog, store), base_url="http://localhost")
    assert client.get("/api/notebooks").status_code == 401
    assert client.post("/api/session", json={"token": "wrong"}).status_code == 403
    result = client.post("/api/session", json={"token": "local-test-token"})
    assert result.status_code == 200
    assert "HttpOnly" in result.headers["set-cookie"]
    assert client.get("/api/notebooks").status_code == 200


def test_skill_frontmatter_delimiters_are_lines(system):
    _, catalog, _, _, _ = system
    folder = catalog.directory / "portable"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        '---\nname: portable\ndescription: "Use --- markers in explanations"\n---\nTeach with examples.'
    )
    assert (
        catalog.resolve(["local:portable"])[-1]["description"]
        == "Use --- markers in explanations"
    )
