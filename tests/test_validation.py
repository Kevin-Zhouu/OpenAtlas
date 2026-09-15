import json

import pytest
from fastapi.testclient import TestClient

from openatlas.api import create_app
from openatlas.artifacts import ArtifactStore, validate
from openatlas.demo import generate
from openatlas.repository import Repository
from openatlas.runner import Runner


def workspace(tmp_path, script, feedback, target=""):
    (tmp_path / "source").mkdir()
    (tmp_path / "source" / "README.md").write_text("Editable lesson source")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "index.html").write_text(
        "<!doctype html><html><body><p>"
        + "A learning example explains how an expandable diagram works. " * 5
        + '</p><button id="toggle" '
        + target
        + ">Show explanation</button>"
        + feedback
        + '<script>document.querySelector("#toggle").onclick=()=>{'
        + script
        + "};</script></body></html>"
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "title": "Expandable lesson",
                "entrypoint": "index.html",
                "checks": [
                    {
                        "selector": "#toggle",
                        "action": "click",
                        "expect_selector": "#feedback",
                        "expect_text": "A visible explanation",
                    }
                ],
            }
        )
    )
    return tmp_path


@pytest.mark.parametrize("allow_blob_fetch", [False, True])
def test_embedded_texture_fetch_in_opaque_reader(tmp_path, monkeypatch, allow_blob_fetch):
    from openatlas import config

    if not allow_blob_fetch:
        monkeypatch.setattr(
            config, "ARTIFACT_CSP",
            config.ARTIFACT_CSP.replace(
                "connect-src http: https: blob:", "connect-src http: https:"
            ),
        )
    # Exercise the object-URL fetch/decode path used by embedded GLTF textures.
    # Completing the interaction on failure also checks the final runtime gate.
    path = workspace(tmp_path, """
        const canvas = document.createElement('canvas');
        canvas.width = canvas.height = 2;
        canvas.getContext('2d').fillRect(0, 0, 2, 2);
        canvas.toBlob(async blob => {
            const url = URL.createObjectURL(blob);
            try {
                if (!url.startsWith('blob:null/')) throw new Error('Reader is not opaque');
                const response = await fetch(url);
                const bitmap = await createImageBitmap(await response.blob());
                if (bitmap.width !== 2) throw new Error('Texture did not decode');
                bitmap.close();
            } catch (error) {
                console.error('Texture fetch failed: ' + error.message);
            } finally {
                URL.revokeObjectURL(url);
                document.querySelector('#feedback').textContent = 'A visible explanation';
            }
        }, 'image/png');
    """, '<p id="feedback">Waiting for texture</p>')
    if allow_blob_fetch:
        assert validate(path)["title"] == "Expandable lesson"
    else:
        with pytest.raises(ValueError, match="Browser validation failed:.*connect-src"):
            validate(path)


@pytest.mark.parametrize("kind", ["reveal", "insert", "reveal-without-text"])
def test_feedback_can_be_revealed_or_created(tmp_path, kind):
    if kind == "insert":
        path = workspace(
            tmp_path,
            "setTimeout(()=>document.body.insertAdjacentHTML('beforeend','<p id=feedback>A visible explanation</p>'),100)",
            "",
        )
    else:
        path = workspace(
            tmp_path,
            "document.querySelector('#feedback').hidden=false",
            '<p id="feedback" hidden>A visible explanation</p>',
        )
    if kind == "reveal-without-text":
        manifest = json.loads((path / "manifest.json").read_text())
        del manifest["checks"][0]["expect_text"]
        (path / "manifest.json").write_text(json.dumps(manifest))
    assert validate(path)["title"] == "Expandable lesson"


@pytest.mark.parametrize("outcome", ["hide", "remove", "reveal"])
def test_visibility_outcomes_do_not_require_artificial_text(tmp_path, outcome):
    visible = outcome == "reveal"
    script = {
        "hide": "document.querySelector('#feedback').hidden=true",
        "remove": "document.querySelector('#feedback').remove()",
        "reveal": "document.querySelector('#feedback').hidden=false",
    }[outcome]
    path = workspace(
        tmp_path,
        script,
        '<p id="feedback"' + (" hidden" if visible else "") + ">Real panel content</p>",
    )
    manifest = json.loads((path / "manifest.json").read_text())
    check = manifest["checks"][0]
    del check["expect_text"]
    check["expect_visible"] = visible
    (path / "manifest.json").write_text(json.dumps(manifest))
    assert validate(path)["title"] == "Expandable lesson"


@pytest.mark.parametrize(
    "defect", ["already-hidden", "ineffective-close", "invalid-flag", "hidden-text"]
)
def test_visibility_checks_reject_false_success(tmp_path, monkeypatch, defect):
    # Keep intentionally failing browser waits short; production retains its
    # software-renderer action budget.
    monkeypatch.setattr("openatlas.artifacts.INTERACTION_TIMEOUT_MS", 1000)
    path = workspace(
        tmp_path,
        "",
        '<p id="feedback"'
        + (" hidden" if defect == "already-hidden" else "")
        + ">Real panel content</p>",
    )
    manifest = json.loads((path / "manifest.json").read_text())
    check = manifest["checks"][0]
    del check["expect_text"]
    check["expect_visible"] = "false" if defect == "invalid-flag" else False
    if defect == "hidden-text":
        check["expect_text"] = "Real panel content"
    (path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Interaction check 1 failed"):
        validate(path)


@pytest.mark.parametrize("kind", ["hidden-feedback", "hidden-control", "unchanged"])
def test_hidden_or_ineffective_interactions_still_fail(tmp_path, kind):
    feedback = (
        '<p id="feedback"'
        + (" hidden" if kind == "hidden-feedback" else "")
        + ">A visible explanation</p>"
    )
    path = workspace(
        tmp_path, "", feedback, "hidden" if kind == "hidden-control" else ""
    )
    if kind == "unchanged":
        manifest = json.loads((path / "manifest.json").read_text())
        del manifest["checks"][0]["expect_text"]
        (path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(
        ValueError, match="Interaction check 1 failed: control="
    ) as error:
        validate(path)
    assert "#feedback" in str(error.value)


def test_revalidation_publishes_without_inference_preserving_failure(tmp_path):
    repo = Repository(tmp_path / "data")
    store = ArtifactStore(repo.data)
    client = TestClient(create_app(repo, store=store), base_url="http://localhost")
    failed = client.post(
        "/api/jobs", json={"prompt": "Teach me caching", "provider": "codex"}
    ).json()
    repo.claim(2)
    work = tmp_path / "work"
    work.mkdir()
    generate(work, failed["request"], lambda _: None)
    store.quarantine(failed["id"], 1, work, ValueError("Old validator failure"))
    repo.fail(failed["id"], "Old validator failure")
    response = client.post("/api/jobs/" + failed["id"] + "/revalidate")
    assert response.status_code == 202
    recovery = response.json()
    assert recovery["notebook_id"] == failed["notebook_id"]

    class NoInference:
        def run(self, *args):
            raise AssertionError("Revalidation must not invoke the agent")

    Runner(repo, store=store, executor=NoInference()).process(repo.claim(2))
    assert repo.job(recovery["id"])["status"] == "succeeded"
    assert repo.job(failed["id"])["status"] == "failed"
    assert (
        repo.notebook(failed["notebook_id"])["versions"][0]["provenance"]
        == failed["request"]["skills"]
    )
    assert client.post("/api/jobs/" + recovery["id"] + "/revalidate").status_code == 409


def test_teaching_source_attachments_are_plain_text_not_executed(tmp_path):
    from openatlas.artifacts import artifact_media_type

    w = workspace(
        tmp_path,
        "document.querySelector('#feedback').textContent='A visible explanation'",
        '<p id="feedback"></p>',
    )
    for name, content in {
        "Wire.cs": "public class Wire {}",
        "Demo.csproj": "<Project/>",
        "certs.sh": "#!/bin/sh\nexit 1",
        "README.md": "# Teaching prototype",
    }.items():
        file = w / "dist" / name
        file.write_text(content)
        assert artifact_media_type(file) == "text/plain; charset=utf-8"
    assert validate(w)["entrypoint"] == "index.html"
    (w / "dist/Wire.cs").write_bytes(b"\x00binary")
    with pytest.raises(ValueError, match="binary data"):
        validate(w)
    (w / "dist/Wire.cs").unlink()
    (w / "dist/server.exe").write_bytes(b"MZ")
    with pytest.raises(ValueError, match="Unsupported static artifact"):
        validate(w)


@pytest.mark.parametrize("action", ["select", "fill"])
def test_dropdown_selection_and_legacy_fill(tmp_path, action):
    w = workspace(tmp_path, "", '<p id="feedback"></p>')
    html = (
        "<!doctype html><html><body><p>"
        + "Learn how changing a request changes its routing. " * 6
        + '</p><select id="request"><option value="one">One order</option><option value="all">All orders</option></select><p id="feedback">One order</p><script>document.querySelector("#request").addEventListener("change",e=>document.querySelector("#feedback").textContent=e.target.value==="all"?"All packed orders":"One order");</script></body></html>'
    )
    (w / "dist/index.html").write_text(html)
    manifest = json.loads((w / "manifest.json").read_text())
    manifest["checks"] = [
        {
            "selector": "#request",
            "action": action,
            "value": "all",
            "expect_selector": "#feedback",
            "expect_text": "All packed orders",
        }
    ]
    (w / "manifest.json").write_text(json.dumps(manifest))
    assert validate(w)["entrypoint"] == "index.html"
    manifest["checks"][0]["value"] = "missing-option"
    (w / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="Interaction check 1 failed"):
        validate(w)


def test_select_action_rejects_non_dropdown(tmp_path):
    w = workspace(tmp_path, "", '<p id="feedback">A visible explanation</p>')
    manifest = json.loads((w / "manifest.json").read_text())
    manifest["checks"][0].update(action="select", value="all")
    (w / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="requires a <select>"):
        validate(w)


def test_validation_rounds_keep_pass_failure_and_unrun_evidence(tmp_path):
    from openatlas.validation_report import recording

    repo = Repository(tmp_path / "data")
    job = repo.enqueue({"prompt": "Explain a motor", "provider": "demo", "skills": []})
    repo.claim(1)
    work = tmp_path / "work"
    work.mkdir()
    workspace(work, "", '<p id="feedback" hidden>A visible explanation</p>')
    with pytest.raises(ValueError, match="Interaction check 1 failed"):
        with recording(repo.data, job["id"], 0):
            validate(work)
    client = TestClient(create_app(repo), base_url="http://localhost")
    report = client.get(f"/api/jobs/{job['id']}/debug").json()["validation"][0]
    checks = {c["id"]: c for c in report["checks"]}
    assert report["status"] == "failed"
    assert checks["source"]["status"] == "passed"
    assert checks["interaction-1"]["status"] == "failed"
    assert checks["interaction-1"]["definition"]["selector"] == "#toggle"
    assert checks["interaction-1"]["duration_ms"] >= 0
    assert checks["mobile"]["status"] == "not_run"
    html = work / "dist/index.html"
    html.write_text(html.read_text().replace(" hidden", ""))
    with recording(repo.data, job["id"], 1):
        validate(work)
    rounds = client.get(f"/api/jobs/{job['id']}/debug").json()["validation"]
    assert [r["status"] for r in rounds] == ["failed", "passed"]
    interaction = next(c for c in rounds[1]["checks"] if c["id"] == "interaction-1")
    assert interaction["after_text"] == "A visible explanation"
    assert all(c["status"] == "passed" for c in rounds[1]["checks"])


def test_preflight_failure_reports_unrun_checks(tmp_path):
    from uuid import uuid4

    from openatlas.validation_report import recording, reports

    job = {"id": str(uuid4()), "status": "failed"}
    with pytest.raises(ValueError, match="retained editable source"):
        with recording(tmp_path, job["id"], 0):
            validate(tmp_path / "missing")
    report = reports(tmp_path, job)[0]
    assert report["checks"][0]["status"] == "failed"
    assert all(c["status"] == "not_run" for c in report["checks"][1:])
