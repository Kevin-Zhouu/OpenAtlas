"""Persistent per-check validation evidence, including failed repair rounds."""

import json
import os
import tempfile
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

_current = ContextVar("validation_report", default=None)


def stamp():
    return datetime.now(timezone.utc).isoformat()


class ValidationReport:
    def __init__(self, path=None, round_number=1):
        self.path = path
        self.data = {
            "round": round_number,
            "status": "running",
            "started_at": stamp(),
            "finished_at": None,
            "checks": [],
            "browser": "Chromium",
            "sandbox": "allow-scripts",
        }

    def save(self):
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=self.path.parent)
        try:
            with os.fdopen(fd, "w") as out:
                json.dump(self.data, out)
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def add(self, key, title, expected, before=None, **details):
        definition = details.get("definition")
        if isinstance(definition, dict):
            details["definition"] = {
                field: str(definition[field])[:2000]
                for field in (
                    "selector",
                    "expect_selector",
                    "action",
                    "value",
                    "expect_text",
                    "expect_visible",
                )
                if field in definition
            }
        row = {
            "id": key,
            "title": title,
            "expected": expected,
            "status": "not_run",
            **details,
        }
        if before:
            index = next(
                i
                for i, check in enumerate(self.data["checks"])
                if check["id"] == before
            )
            self.data["checks"].insert(index, row)
        else:
            self.data["checks"].append(row)
        self.save()

    def update(self, key, **fields):
        next(c for c in self.data["checks"] if c["id"] == key).update(fields)
        self.save()

    @contextmanager
    def check(self, key):
        start = time.monotonic()
        self.update(key, status="running", started_at=stamp())
        try:
            yield
        except Exception as error:
            self.update(
                key,
                status="failed",
                reason=str(error)[:4000],
                duration_ms=round((time.monotonic() - start) * 1000),
                finished_at=stamp(),
            )
            raise
        else:
            self.update(
                key,
                status="passed",
                reason="Expected condition met.",
                duration_ms=round((time.monotonic() - start) * 1000),
                finished_at=stamp(),
            )

    def finish(self, error=None):
        self.data.update(
            status="failed" if error else "passed",
            passed=error is None,
            finished_at=stamp(),
        )
        if error:
            self.data["reason"] = str(error)[:4000]
        self.save()


@contextmanager
def recording(data, job_id, attempt):
    report = ValidationReport(
        Path(data) / "validation" / str(UUID(job_id)) / f"{attempt}.json", attempt + 1
    )
    token = _current.set(report)
    try:
        yield report
    finally:
        _current.reset(token)


def current_report():
    return _current.get() or ValidationReport()


def reports(data, job):
    root = Path(data)
    job_id = str(UUID(job["id"]))
    result = []
    for path in sorted((root / "validation" / job_id).glob("*.json")):
        report = json.loads(path.read_text())
        if report["status"] == "running" and job["status"] in ("failed", "succeeded"):
            report["status"] = "interrupted"
            for check in report["checks"]:
                if check["status"] == "running":
                    check.update(
                        status="interrupted",
                        reason="The runner stopped before recording a result.",
                    )
        result.append(report)
    if result:
        return result
    # Older runners retained only the failure and declared checks, not results per check.
    for path in sorted((root / "failed" / job_id).glob("*/error.txt")):
        result.append(
            {
                "round": int(path.parent.name) + 1,
                "status": "failed",
                "legacy": True,
                "reason": path.read_text()[:4000],
                "checks": [],
            }
        )
    if job.get("version_id"):
        path = (
            root
            / "library"
            / job["notebook_id"]
            / job["version_id"]
            / "validation.json"
        )
        if path.is_file():
            result.append(
                {
                    "round": len(result) + 1,
                    "status": "passed",
                    "legacy": True,
                    "reason": "Published Notebook passed the validation available at the time. Individual check evidence was not recorded.",
                    "checks": [],
                }
            )
    return result
