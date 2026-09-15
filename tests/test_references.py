"""Exercise portable evidence delivery without inference or a host dataset."""

import ast
import asyncio
import io
import json
import tarfile
from pathlib import Path

import pytest

from openatlas.execution import archive_input
from openatlas.references import stage_references


def test_reference_archive_survives_host_removal(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    status = stage_references(workspace)
    assert status["status"] == "available"
    with tarfile.open(fileobj=io.BytesIO(archive_input(workspace))) as archive:
        catalog = json.load(archive.extractfile("references/goldens/CATALOG.json"))
        assert len(catalog["references"]) == 15
        for reference in catalog["references"]:
            for record in reference["files"]:
                assert archive.extractfile(
                    "references/goldens/" + record["path"]
                ).read()


def test_missing_and_modified_records_are_honest(tmp_path):
    missing = stage_references(tmp_path / "empty", tmp_path / "absent")
    assert missing["status"] == "unavailable"
    source = tmp_path / "input"
    source.mkdir()
    (source / "changed.md").write_text("Changed")
    (source / "CATALOG.json").write_text(
        json.dumps(
            {
                "references": [
                    {
                        "files": [
                            {"path": "missing.md", "sha256": "no"},
                            {"path": "changed.md", "sha256": "no"},
                            {"path": "../outside.md", "sha256": "no"},
                        ]
                    }
                ]
            }
        )
    )
    result = stage_references(tmp_path / "partial", source)
    assert result["status"] == "partial" and len(result["missing_or_changed"]) == 3
    assert result["files"] == []
    assert not (tmp_path / "partial/references/goldens/changed.md").exists()


def test_planner_reads_references_and_rejects_escape_and_images(tmp_path):
    # Execute the actual tool functions without loading the container-only Agents SDK.
    tree = ast.parse(Path("generation/planner.py").read_text())
    nodes = [
        n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name in ("emit", "list_resources", "read_resource")
    ]
    for node in nodes:
        node.decorator_list = []
    env = {
        "json": json,
        "ROOT": tmp_path / "skills",
        "REFERENCES": tmp_path / "references",
        "READ": set(),
        "REFERENCE_READS": [],
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "planner-tools", "exec"), env)
    stage_references(tmp_path)
    listed = asyncio.run(env["list_resources"]())
    assert "references/goldens/CATALOG.json" in listed
    path = "references/goldens/chernobyl-atlas-1575d13d/principles.md"
    text = asyncio.run(env["read_resource"](path))
    assert "reversible" in text
    assert env["REFERENCE_READS"] == [
        {"path": path, "offset": 0, "characters": len(text)}
    ]
    for path in [
        "references/../../etc/passwd",
        "../../etc/passwd",
        "references/missing.md",
    ]:
        with pytest.raises(ValueError):
            asyncio.run(env["read_resource"](path))
    with pytest.raises(ValueError, match="Text-only"):
        asyncio.run(
            env["read_resource"](
                "references/goldens/chernobyl-atlas-1575d13d/contact-sheet.jpg"
            )
        )
    assert len(env["REFERENCE_READS"]) == 1
