"""Bounded, private diagnostics. Only the trusted runner talks to Docker."""

import json
import os
import re
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID


class DebugStore:
    _locks = {}

    def __init__(self, data):
        self.directory = Path(data) / "debug"
        self.lock = self._locks.setdefault(
            str(self.directory.resolve()), threading.Lock()
        )

    def path(self, job_id):
        return self.directory / (str(UUID(job_id)) + ".json")

    def read(self, job_id):
        try:
            return json.loads(self.path(job_id).read_text())
        except FileNotFoundError:
            return {"containers": [], "updated_at": None}

    def invocations(self, job_id):
        path = self.directory / (str(UUID(job_id)) + ".invocations.json")
        try:
            return json.loads(path.read_text())
        except FileNotFoundError:
            return []

    def record_invocation(self, job_id, command, request, secrets=(), execution=None):
        with self.lock:
            records = self.invocations(job_id)
            records.append({
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "execution": execution or {},
                "phase": "planning" if request.get("execution_stage") == "planning" else "repair" if request.get("validation_feedback") else "continue" if request.get("continue_job") else "generate",
                "command": command,
                "prompt": command[-1] if command and command[0] == "codex" else "\n\n".join(command[-2:]) if request.get("execution_stage") == "planning" else None,
                "model": request.get("planner_model") if request.get("execution_stage") == "planning" else request.get("model"),
                "skills": request.get("skills", []),
                "validation_feedback": request.get("validation_feedback"),
            })
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd, tmp = tempfile.mkstemp(dir=self.directory)
            try:
                with os.fdopen(fd, "w") as out:
                    out.write(redact(json.dumps(records[-8:]), secrets))
                os.replace(tmp, self.directory / (str(UUID(job_id)) + ".invocations.json"))
            finally:
                Path(tmp).unlink(missing_ok=True)

    def record(self, job_id, snapshot):
        with self.lock:
            data = self.read(job_id)
            containers = [c for c in data["containers"] if c["id"] != snapshot["id"]]
            containers.append(snapshot)
            data = {
                "containers": containers[-16:],
                "updated_at": snapshot["observed_at"],
            }
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd, tmp = tempfile.mkstemp(dir=self.directory)
            try:
                with os.fdopen(fd, "w") as out:
                    json.dump(data, out)
                os.replace(tmp, self.path(job_id))
            finally:
                Path(tmp).unlink(missing_ok=True)


def redact(value, secrets=()):
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[redacted]")
    value = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "[redacted]", value)
    return re.sub(r"(?i)(Bearer\s+)[A-Za-z0-9._\-]+", r"\1[redacted]", value)


def capture(container, store, removed=False):
    """Whitelist inspect fields; never persist raw inspect, environment or process args."""
    container.reload()
    attrs = container.attrs
    cfg = attrs.get("Config", {})
    env = cfg.get("Env") or []
    secrets = [
        v.split("=", 1)[1]
        for v in env
        if "=" in v
        and any(k in v.split("=", 1)[0] for k in ("KEY", "TOKEN", "SECRET", "PASSWORD"))
    ]
    role = "relay" if "/opt/broker.py" in (cfg.get("Cmd") or []) else "agent"
    state = attrs.get("State", {})
    snapshot = {
        "id": container.id,
        "role": role,
        "stage": container.labels.get("openatlas.stage", "building"),
        "image": cfg.get("Image"),
        "status": "removed" if removed else state.get("Status"),
        "started_at": state.get("StartedAt"),
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "memory_limit": attrs.get("HostConfig", {}).get("Memory"),
        "cpu_limit": attrs.get("HostConfig", {}).get("NanoCpus", 0) / 1e9,
        "read_only": attrs.get("HostConfig", {}).get("ReadonlyRootfs"),
        "processes": [],
        "agent_log": "",
        "container_log": "",
    }
    if state.get("Running"):
        try:
            # Executable names only: full command lines may include provider credentials.
            snapshot["processes"] = container.top(ps_args="-eo pid,comm").get(
                "Processes", []
            )[:100]
        except Exception:
            pass
        if role == "agent":
            result = container.exec_run(
                ["tail", "-c", "131072", "/tmp/codex-output.log"]
            )
            if result.exit_code == 0:
                snapshot["agent_log"] = redact(
                    result.output.decode("utf-8", errors="replace"), secrets
                )
    try:
        snapshot["container_log"] = redact(
            container.logs(tail=100).decode("utf-8", errors="replace")[-32768:], secrets
        )
    except Exception:
        pass
    store.record(container.labels["openatlas.job"], snapshot)


def observe(data, stop):
    """Separate observer also supports containers started before an app upgrade."""
    import docker

    store = DebugStore(data)
    client = docker.from_env(timeout=5)
    previous = {}
    try:
        while not stop.is_set():
            try:
                current = {}
                for container in client.containers.list(
                    filters={"label": "openatlas.job"}
                ):
                    current[container.id] = container.labels.get("openatlas.job")
                    try:
                        capture(container, store)
                    except Exception:
                        pass  # A container may disappear between list and inspection.
                for container_id, job_id in previous.items():
                    if container_id not in current and job_id:
                        for snapshot in store.read(job_id)["containers"]:
                            if (
                                snapshot["id"] == container_id
                                and snapshot["status"] != "removed"
                            ):
                                snapshot["status"] = "no longer running"
                                store.record(job_id, snapshot)
                previous = current
            except Exception:
                pass
            stop.wait(3)
    finally:
        client.close()


if __name__ == "__main__":
    from .config import DATA

    observe(DATA, threading.Event())
