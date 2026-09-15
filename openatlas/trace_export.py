"""Portable, stage-scoped archives of retained diagnostics; no Docker access."""

import io
import json
import zipfile
from datetime import datetime, timezone

from .debug import DebugStore, redact

STAGES = ("planning", "building", "validating", "publishing")
FOLDERS = {
    "planning": "planning",
    "building": "implementing",
    "validating": "validating",
    "publishing": "publishing",
}


def trace_archive(data, snapshot, planning=None, stage=None, secrets=()):
    debug = DebugStore(data)
    output = io.BytesIO()
    exported = datetime.now(timezone.utc).isoformat()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:

        def write(path, value, text=False):
            archive.writestr(
                path,
                redact(
                    value if text else json.dumps(value, ensure_ascii=False, indent=2),
                    secrets,
                ),
            )

        write(
            "README.txt",
            "OpenAtlas generation trace\n\nJSON files contain job inputs, captured invocations, stage events and validation results. Agent log files contain emitted CLI/SDK activity. Known credentials are redacted.\n\nCompleted agent logs are retained up to 10 MiB each. Metadata labels retention as complete, in_progress, truncated, or snapshot_only. Running logs are checkpointed about every 30 seconds, with a final capture on exit. A recent.agent.log file includes the latest snapshot tail when the archive is incomplete. Older jobs may only have the latest retained log tail. Missing history cannot be reconstructed. System stages have events and reports rather than an agent log. A live download is a snapshot at export time.\n",
            text=True,
        )
        write(
            "manifest.json",
            {
                "format_version": 1,
                "exported_at": exported,
                "job_id": snapshot["job"]["id"],
                "job_status": snapshot["job"]["status"],
                "selected_stage": stage or "all",
                "planning_source_job_id": planning["job"]["id"] if planning else None,
            },
        )
        for selected in STAGES if stage is None else (stage,):
            origin = planning if selected == "planning" and planning else snapshot
            folder = FOLDERS[selected]
            generation = origin.get("generation") or {}
            invocations = (
                [
                    i
                    for i in generation.get("invocations", [])
                    if (i.get("phase") == "planning") == (selected == "planning")
                ]
                if selected in ("planning", "building")
                else []
            )
            write(
                folder + "/stage.json",
                {
                    "stage": selected,
                    "source_job_id": origin["job"]["id"],
                    "job": origin["job"],
                    "request": generation.get(
                        "request", origin["job"].get("request", {})
                    ),
                    "invocations": invocations,
                    "events": [
                        e
                        for e in origin.get("events", [])
                        if e.get("stage") == selected
                    ],
                },
            )
            if selected == "validating":
                write(folder + "/validation-rounds.json", origin.get("validation", []))
            containers = [
                c
                for c in origin.get("containers", [])
                if c.get("stage", "building") == selected
            ]
            for container in containers:
                ident = container["id"]
                saved = debug.trace(origin["job"]["id"], ident)
                metadata = {
                    k: v
                    for k, v in container.items()
                    if k not in ("agent_log", "container_log")
                }
                metadata.update(
                    {
                        k: v
                        for k, v in (saved or {"retention": "snapshot_only"}).items()
                        if k != "agent_log"
                    }
                )
                write(f"{folder}/{ident}.json", metadata)
                write(
                    f"{folder}/{ident}.agent.log",
                    saved["agent_log"] if saved else container.get("agent_log", ""),
                    text=True,
                )
                if saved and saved.get("retention") != "complete":
                    write(
                        f"{folder}/{ident}.recent.agent.log",
                        container.get("agent_log", ""),
                        text=True,
                    )
                write(
                    f"{folder}/{ident}.container.log",
                    container.get("container_log", ""),
                    text=True,
                )
    return output.getvalue()
