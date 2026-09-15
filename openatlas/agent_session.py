"""Job-scoped Codex conversation transfer. Never transfer auth/config or publish history."""

import io
import tarfile
from uuid import UUID

LIMIT = 32 * 1024 * 1024


def session_archive(raw, secrets=()):
    if len(raw) > LIMIT:
        raise ValueError("Codex session history exceeds the private transfer limit")
    output = io.BytesIO()
    total = 0
    files = 0
    with (
        tarfile.open(fileobj=io.BytesIO(raw)) as source,
        tarfile.open(fileobj=output, mode="w") as dest,
    ):
        for member in source:
            parts = member.name.split("/")
            if parts[0] != "sessions" or any(p in ("..", "") for p in parts):
                raise ValueError("Unsafe Codex session archive path")
            if member.isdir():
                continue
            if not member.isfile() or not member.name.endswith(".jsonl"):
                raise ValueError(
                    "Codex session transfer accepts only regular JSONL history files"
                )
            total += member.size
            if total > LIMIT:
                raise ValueError(
                    "Codex session history exceeds the private transfer limit"
                )
            files += 1
            body = source.extractfile(member).read()
            for secret in secrets:
                if secret:
                    body = body.replace(secret.encode(), b"[REDACTED]")
            clean = tarfile.TarInfo(member.name)
            clean.size, clean.mode, clean.uid, clean.gid = len(body), 0o600, 1000, 1000
            dest.addfile(clean, io.BytesIO(body))
    if not files:
        raise ValueError("Codex session history contains no resumable files")
    return output.getvalue()


def thread_id(log):
    import json

    for line in log.splitlines():
        try:
            event = json.loads(line)
            if event.get("type") == "thread.started":
                return str(UUID(event["thread_id"]))
        except (ValueError, KeyError, TypeError):
            continue
    raise ValueError("Codex did not report a resumable session ID")
