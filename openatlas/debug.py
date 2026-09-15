"""Bounded, private diagnostics. Only the trusted runner talks to Docker."""

import json
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

MAX_TRACE_BYTES = 10 * 1024 * 1024


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
            data = json.loads(self.path(job_id).read_text())
            for container in data["containers"]:
                trace = self.trace(job_id, container["id"])
                if trace and trace.get("agent_log"):
                    lines = (
                        trace["agent_log"] + "\n" + container.get("agent_log", "")
                    ).splitlines()
                    container["agent_log"] = "\n".join(dict.fromkeys(lines))
            return data
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
            if not self.job_retained(job_id):
                return
            records = self.invocations(job_id)
            records.append(
                {
                    "captured_at": datetime.now(timezone.utc).isoformat(),
                    "execution": execution or {},
                    "phase": "review"
                    if request.get("execution_stage") == "reviewing"
                    else "planning"
                    if request.get("execution_stage") == "planning"
                    else "repair"
                    if request.get("validation_feedback")
                    else "continue"
                    if request.get("continue_job")
                    else "generate",
                    "command": command,
                    "prompt": command[-1]
                    if command and command[0] == "codex"
                    else "\n\n".join(command[-2:])
                    if request.get("execution_stage") == "planning"
                    else None,
                    "model": request.get("planner_model")
                    if request.get("execution_stage") == "planning"
                    else request.get("model"),
                    "skills": request.get("skills", []),
                    "validation_feedback": request.get("validation_feedback"),
                }
            )
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd, tmp = tempfile.mkstemp(
                prefix=str(UUID(job_id)) + "-", dir=self.directory
            )
            try:
                with os.fdopen(fd, "w") as out:
                    out.write(redact(json.dumps(records), secrets))
                os.replace(
                    tmp, self.directory / (str(UUID(job_id)) + ".invocations.json")
                )
            finally:
                Path(tmp).unlink(missing_ok=True)

    def trace_path(self, job_id, container_id):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", container_id):
            raise ValueError("Invalid trace container identifier")
        return self.directory / "traces" / str(UUID(job_id)) / (container_id + ".json")

    def save_trace(self, job_id, container_id, content):
        with self.lock:
            if not self.job_retained(job_id):
                return
            previous = self.trace(job_id, container_id)
            if previous and (
                previous.get("captured_at", "") > content.get("captured_at", "")
                or (previous.get("final_capture") and not content.get("final_capture"))
            ):
                return
            path = self.trace_path(job_id, container_id)
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd, temporary = tempfile.mkstemp(dir=path.parent)
            try:
                with os.fdopen(fd, "w") as out:
                    json.dump(content, out)
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)

    def trace(self, job_id, container_id):
        try:
            return json.loads(self.trace_path(job_id, container_id).read_text())
        except FileNotFoundError:
            return None

    def job_retained(self, job_id):
        database = self.directory.parent / "openatlas.sqlite3"
        if not database.exists():
            return True
        import sqlite3

        with sqlite3.connect(database) as connection:
            return bool(
                connection.execute(
                    "SELECT 1 FROM jobs WHERE id=?", (job_id,)
                ).fetchone()
            )

    def record(self, job_id, snapshot):
        with self.lock:
            if not self.job_retained(job_id):
                return
            data = self.read(job_id)
            previous = next(
                (c for c in data["containers"] if c["id"] == snapshot["id"]), {}
            )
            # Merge complete JSON events, retaining start/update/completion order.
            lines = list(
                dict.fromkeys(
                    (
                        previous.get("agent_log", "")
                        + "\n"
                        + snapshot.get("agent_log", "")
                    ).splitlines()
                )
            )
            events = []
            size = 0
            for line in lines:
                try:
                    json.loads(line)
                except ValueError:
                    continue
                size += len(line.encode("utf-8")) + 1
                if size > MAX_TRACE_BYTES:
                    snapshot["history_truncated"] = True
                    break
                events.append(line)
            snapshot["agent_log"] = (
                "\n".join(events)
                if events
                else previous.get("agent_log") or snapshot.get("agent_log", "")
            )
            containers = [c for c in data["containers"] if c["id"] != snapshot["id"]]
            containers.append(snapshot)
            data = {
                "containers": containers,
                "updated_at": snapshot["observed_at"],
            }
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd, tmp = tempfile.mkstemp(
                prefix=str(UUID(job_id)) + "-", dir=self.directory
            )
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


def capture(
    container, store, removed=False, extra_secrets=(), archive=False, preserve=False
):
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
    secrets += list(extra_secrets)
    role = "relay" if "/opt/broker.py" in (cfg.get("Cmd") or []) else "agent"
    state = attrs.get("State", {})
    if (
        state.get("Running")
        and container.labels.get("openatlas.authentication") == "chatgpt"
    ):
        # Subscription tokens are in a private cache, never environment variables.
        from .subscription import AUTH_PATH, SubscriptionStore, auth_secrets

        try:
            session_state = SubscriptionStore(store.directory.parent)._read()
            secrets += auth_secrets(session_state.get("auth") or {})
            result = container.exec_run(["head", "-c", "200001", AUTH_PATH])
            if result.exit_code == 0:
                secrets += auth_secrets(json.loads(result.output))
            else:
                return
        except Exception:
            # Do not persist unredacted subscription logs if the cache is unreadable.
            return
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
                ["head", "-c", str(MAX_TRACE_BYTES), "/tmp/codex-output.log"]
            )
            if result.exit_code == 0:
                raw = result.output
                snapshot["history_truncated"] = len(raw) >= MAX_TRACE_BYTES
                if snapshot["history_truncated"]:
                    raw = raw.rsplit(b"\n", 1)[0] if b"\n" in raw else b""
                snapshot["agent_log"] = redact(
                    raw.decode("utf-8", errors="replace"), secrets
                )
    try:
        snapshot["container_log"] = redact(
            container.logs(tail=100).decode("utf-8", errors="replace")[-32768:], secrets
        )
    except Exception:
        pass
    trace_path = store.trace_path(container.labels["openatlas.job"], container.id)
    due = preserve and (
        not trace_path.exists() or time.time() - trace_path.stat().st_mtime >= 30
    )
    if (archive or due) and role == "agent" and state.get("Running"):
        limit = MAX_TRACE_BYTES
        result = container.exec_run(
            ["head", "-c", str(limit + 1), "/tmp/codex-output.log"]
        )
        if result.exit_code == 0:
            truncated = len(result.output) > limit
            raw = result.output[:limit]
            if truncated:
                # Never retain a partial final line (which could split a credential).
                raw = raw.rsplit(b"\n", 1)[0] if b"\n" in raw else b""
            store.save_trace(
                container.labels["openatlas.job"],
                container.id,
                {
                    "stage": snapshot["stage"],
                    "captured_at": snapshot["observed_at"],
                    "retention": "truncated"
                    if truncated
                    else "complete"
                    if archive
                    else "in_progress",
                    "byte_limit": limit,
                    "final_capture": archive,
                    "agent_log": redact(raw.decode("utf-8", errors="replace"), secrets),
                },
            )
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
                        capture(container, store, preserve=True)
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
