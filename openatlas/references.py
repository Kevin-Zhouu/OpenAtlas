"""Portable, versioned study inputs shared by planning and building."""

import hashlib
import json
import shutil
from pathlib import Path

GOLDENS = Path(__file__).parent / "resources" / "goldens"


def stage_references(workspace, source=None):
    source = Path(source) if source is not None else GOLDENS
    destination = workspace / "references" / "goldens"
    destination.mkdir(parents=True, exist_ok=True)
    catalog = source / "CATALOG.json"
    if not catalog.is_file():
        status = {
            "status": "unavailable",
            "reason": "Packaged golden reference catalog is missing",
            "references": [],
        }
        (destination / "CATALOG.json").write_text(json.dumps(status), encoding="utf-8")
        return status
    manifest = json.loads(catalog.read_text(encoding="utf-8"))
    missing = []
    copied = []
    for reference in manifest["references"]:
        for record in reference["files"]:
            relative = record["path"]
            path = (source / relative).resolve()
            if not path.is_relative_to(source.resolve()) or not path.is_file():
                missing.append(relative)
                continue
            if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
                missing.append(relative)
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            copied.append(record)
    manifest["availability"] = {"missing_or_changed": missing}
    (destination / "CATALOG.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return {
        "status": "partial" if missing else "available",
        "catalog": "references/goldens/CATALOG.json",
        "catalog_sha256": hashlib.sha256(catalog.read_bytes()).hexdigest(),
        "files": copied,
        "missing_or_changed": missing,
    }
