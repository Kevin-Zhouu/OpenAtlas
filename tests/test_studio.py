import io
import zipfile

from fastapi.testclient import TestClient
import pytest

from openatlas.api import create_app
from openatlas.agents import CodexAdapter, DEFAULT_TEACHING_PROMPT
from openatlas.repository import Repository
from openatlas.skills import SkillCatalog
from openatlas.skill_editor import SkillEditor


def test_prompt_persistence_snapshot_and_contract(tmp_path):
    repo = Repository(tmp_path / "data")
    client = TestClient(
        create_app(repo, SkillCatalog(tmp_path / "skills")), base_url="http://localhost"
    )
    settings = client.get("/api/settings").json()
    settings["teaching_prompt"] = (
        "Teach visually for {{reading_minutes}} minutes. {literal braces}"
    )
    assert client.put("/api/settings", json=settings).status_code == 200
    job = client.post(
        "/api/jobs",
        json={"prompt": "Learn HTTP", "skills_enabled": False, "reading_minutes": 35},
    ).json()
    settings["teaching_prompt"] = "changed"
    client.put("/api/settings", json=settings)
    prompt = CodexAdapter().prompt(repo.job(job["id"])["request"])
    assert "Teach visually for 35 minutes. {literal braces}" in prompt
    assert "sandbox=allow-scripts" in prompt and "/workspace/dist/index.html" in prompt
    assert Repository(repo.data).settings()["teaching_prompt"] == "changed"
    assert client.get("/api/prompt").json()["default"] == DEFAULT_TEACHING_PROMPT
    assert (
        "changed"
        in client.post("/api/prompt/preview", json={"content": "changed"}).json()[
            "prompt"
        ]
    )


def archive(files):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    return data.getvalue()


def test_skill_create_edit_stage_override_and_conflict(tmp_path):
    catalog = SkillCatalog(tmp_path / "skills")
    editor = SkillEditor(catalog)
    identifier = editor.create("my-skill")["id"]
    original = editor.read(identifier, "SKILL.md")
    editor.save(
        identifier,
        "SKILL.md",
        original["content"] + "\nUse diagrams.",
        original["revision"],
    )
    with pytest.raises(ValueError, match="changed"):
        editor.save(identifier, "SKILL.md", "stale", original["revision"])
    editor.save(identifier, "references/notes.md", "hello")
    assert "references/notes.md" in editor.read(identifier)["files"]
    selected = catalog.resolve([identifier])
    catalog.stage(selected, tmp_path / "stage")
    assert (
        tmp_path / "stage/local--my-skill/references/notes.md"
    ).read_text() == "hello"
    builtin = "builtin:openatlas-core"
    initial = editor.read(builtin, "SKILL.md")
    editor.save(
        builtin,
        "SKILL.md",
        initial["content"] + "\nCustom teaching.",
        initial["revision"],
    )
    assert editor.read(builtin, "SKILL.md")["content"].endswith("Custom teaching.")
    assert (
        SkillEditor(SkillCatalog(tmp_path / "skills"))
        .read(builtin, "SKILL.md")["content"]
        .endswith("Custom teaching.")
    )
    with pytest.raises(ValueError, match="changed"):
        catalog.stage(selected, tmp_path / "old-stage")


def test_install_and_boundaries(tmp_path):
    catalog = SkillCatalog(tmp_path / "skills")
    editor = SkillEditor(catalog)
    content = "---\nname: diagrams\ndescription: Draw diagrams\n---\nTeach visually."
    data = archive({"diagrams/SKILL.md": content, "diagrams/assets/icon.svg": "<svg/>"})
    assert editor.install(data)["id"] == "local:diagrams"
    with pytest.raises(ValueError, match="already exists"):
        editor.install(data)
    for path in ("../escape", "/tmp/escape", "C:/escape", "x/../../escape"):
        with pytest.raises(ValueError):
            editor.install(archive({path: "bad"}))
        with pytest.raises(ValueError):
            editor.save("local:diagrams", path, "bad")
    (tmp_path / "skills/diagrams/link").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="links"):
        editor.read("local:diagrams")


def test_skill_http_validation_and_install(tmp_path):
    catalog = SkillCatalog(tmp_path / "skills")
    client = TestClient(
        create_app(Repository(tmp_path / "data"), catalog), base_url="http://localhost"
    )
    assert client.post("/api/skills/create", json={"name": "../bad"}).status_code == 422
    assert (
        client.post("/api/skills/create", json={"name": "new-skill"}).status_code == 201
    )
    file = client.get(
        "/api/skill-files", params={"skill_id": "local:new-skill", "path": "SKILL.md"}
    ).json()
    assert (
        client.put(
            "/api/skill-files",
            json={
                "skill_id": "local:new-skill",
                "path": "SKILL.md",
                "content": "malformed",
                "revision": file["revision"],
            },
        ).status_code
        == 200
    )
    skill = next(
        s for s in client.get("/api/skills").json() if s["id"] == "local:new-skill"
    )
    assert not skill["valid"]
    assert (
        client.post(
            "/api/jobs", json={"prompt": "Learn", "skills": ["local:new-skill"]}
        ).status_code
        == 422
    )
    assert client.post("/api/skills/install", content=b"not a zip").status_code == 422
