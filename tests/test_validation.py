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
    w = workspace(tmp_path, "document.querySelector('#feedback').textContent='A visible explanation'", '<p id="feedback"></p>')
    for name, content in {'Wire.cs':'public class Wire {}', 'Demo.csproj':'<Project/>', 'certs.sh':'#!/bin/sh\nexit 1', 'README.md':'# Teaching prototype'}.items():
        file = w/'dist'/name
        file.write_text(content)
        assert artifact_media_type(file) == 'text/plain; charset=utf-8'
    assert validate(w)['entrypoint'] == 'index.html'
    (w/'dist/Wire.cs').write_bytes(b'\x00binary')
    with pytest.raises(ValueError, match='binary data'): validate(w)
    (w/'dist/Wire.cs').unlink()
    (w/'dist/server.exe').write_bytes(b'MZ')
    with pytest.raises(ValueError, match='Unsupported static artifact'): validate(w)


@pytest.mark.parametrize('action', ['select', 'fill'])
def test_dropdown_selection_and_legacy_fill(tmp_path, action):
    w = workspace(tmp_path, "", '<p id="feedback"></p>')
    html = '<!doctype html><html><body><p>' + 'Learn how changing a request changes its routing. ' * 6 + '</p><select id="request"><option value="one">One order</option><option value="all">All orders</option></select><p id="feedback">One order</p><script>document.querySelector("#request").addEventListener("change",e=>document.querySelector("#feedback").textContent=e.target.value==="all"?"All packed orders":"One order");</script></body></html>'
    (w/'dist/index.html').write_text(html)
    manifest=json.loads((w/'manifest.json').read_text())
    manifest['checks']=[{'selector':'#request','action':action,'value':'all','expect_selector':'#feedback','expect_text':'All packed orders'}]
    (w/'manifest.json').write_text(json.dumps(manifest))
    assert validate(w)['entrypoint']=='index.html'
    manifest['checks'][0]['value']='missing-option'
    (w/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='Interaction check 1 failed'):
        validate(w)


def test_select_action_rejects_non_dropdown(tmp_path):
    w=workspace(tmp_path,'', '<p id="feedback">A visible explanation</p>')
    manifest=json.loads((w/'manifest.json').read_text())
    manifest['checks'][0].update(action='select', value='all')
    (w/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='requires a <select>'):
        validate(w)
