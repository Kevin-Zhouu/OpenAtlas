"""Disposable Docker execution. Inputs/outputs use archives, never host bind mounts."""

import io
import json
import secrets
import socket
import tarfile
import time
from pathlib import Path

import docker

from . import config
from .agents import CodexAdapter
from .credentials import Credentials
from .debug import capture


def ownership(info):
    info.uid = info.gid = 1000
    info.uname = info.gname = "node"
    return info


def archive_input(workspace):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as tar:
        for p in workspace.iterdir():
            tar.add(
                p, arcname=p.name, recursive=True, filter=lambda info: ownership(info)
            )
    return stream.getvalue()


def extract_output(chunks, destination):
    # Reject links, devices, traversal and archive bombs before copying any output.
    stream = io.BytesIO()
    for chunk in chunks:
        stream.write(chunk)
        if stream.tell() > 120 * 1024 * 1024:
            raise ValueError("Generation archive exceeds 120 MB")
    stream.seek(0)
    total = 0
    with tarfile.open(fileobj=stream) as tar:
        for member in tar:
            parts = Path(member.name).parts
            if parts and parts[0] == "workspace":
                parts = parts[1:]
            if not parts or parts[0] not in ("source", "dist", "manifest.json"):
                continue
            path = destination.joinpath(*parts).resolve()
            if not path.is_relative_to(destination.resolve()) or not (
                member.isfile() or member.isdir()
            ):
                raise ValueError("Unsafe generation archive member")
            if any(p in ("node_modules", ".git", ".env") for p in parts):
                raise ValueError(
                    "Source must exclude dependencies, git history and secrets"
                )
            total += member.size
            if total > 100 * 1024 * 1024:
                raise ValueError("Generation output exceeds 100 MB")
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(member) as src, path.open("wb") as out:
                    import shutil

                    shutil.copyfileobj(src, out)


class DockerExecutor:
    def __init__(self, credentials=None, client=None, adapter=None, debug=None):
        self.credentials = credentials or Credentials()
        self.client = client
        self.adapter = adapter or CodexAdapter()
        self.debug = debug

    def run(self, workspace, request, progress):
        client = self.client or docker.from_env()
        key = self.credentials.openai_key()
        token = secrets.token_urlsafe(32)
        broker = container = None
        deadline = time.monotonic() + config.TIMEOUT
        try:
            common = dict(
                image=config.GENERATION_IMAGE,
                detach=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                read_only=True,
                pids_limit=256,
                mem_limit="2g",
                nano_cpus=2_000_000_000,
                labels={
                    "openatlas.job": request["job_id"],
                    "openatlas.expires": str(time.time() + config.TIMEOUT + 120),
                },
                log_config=docker.types.LogConfig(
                    type="json-file", config={"max-size": "5m", "max-file": "1"}
                ),
            )
            broker = client.containers.run(
                command=["python3", "/opt/broker.py"],
                environment={"OPENAI_API_KEY": key, "RELAY_TOKEN": token},
                network_mode="bridge",
                tmpfs={"/tmp": "rw,noexec,nosuid,size=32m"},
                **common,
            )
            container = client.containers.run(
                command=["sleep", "infinity"],
                environment={
                    "CODEX_API_KEY": token,
                    "HOME": "/tmp/home",
                    "CODEX_HOME": "/tmp/home/.codex",
                },
                network_mode="container:" + broker.id,
                tmpfs={
                    "/workspace": "rw,nosuid,uid=1000,gid=1000,size=768m",
                    "/tmp": "rw,nosuid,uid=1000,gid=1000,size=256m",
                },
                **common,
            )
            upload = client.api.exec_create(
                container.id,
                ["tar", "xf", "-", "-C", "/workspace"],
                stdin=True,
                user="1000:1000",
            )
            connection = client.api.exec_start(upload["Id"], socket=True)
            try:
                connection._sock.sendall(archive_input(workspace))
                connection._sock.shutdown(socket.SHUT_WR)
                while client.api.exec_inspect(upload["Id"])["Running"]:
                    time.sleep(0.1)
                if client.api.exec_inspect(upload["Id"])["ExitCode"] != 0:
                    raise ValueError(
                        "Could not transfer the isolated generation workspace"
                    )
            finally:
                connection.close()
            container.exec_run(["mkdir", "-p", "/tmp/home/.codex"], user="1000:1000")
            progress("Codex is writing, building, and testing your Notebook")
            command = [
                "sh",
                "-c",
                'exec "$@" > /tmp/codex-output.log 2>&1',
                "openatlas",
            ] + self.adapter.command(request)
            execution = client.api.exec_create(
                container.id, command, workdir="/workspace", user="1000:1000"
            )
            client.api.exec_start(execution["Id"], detach=True)
            while client.api.exec_inspect(execution["Id"])["Running"]:
                if time.monotonic() > deadline:
                    raise ValueError(
                        "Codex generation exceeded the configured time limit"
                    )
                time.sleep(2)
            if client.api.exec_inspect(execution["Id"])["ExitCode"] != 0:
                diagnostic = container.exec_run(
                    ["tail", "-c", "3000", "/tmp/codex-output.log"]
                ).output.decode("utf-8", errors="replace")
                messages = []
                for line in diagnostic.splitlines():
                    try:
                        event = json.loads(line)
                        message = event.get("message") or (
                            event.get("error") or {}
                        ).get("message")
                        if message:
                            messages.append(message)
                    except (ValueError, AttributeError):
                        pass
                diagnostic = (
                    (messages[-1] if messages else diagnostic[-600:])
                    .replace(key, "[redacted]")
                    .replace(token, "[redacted]")
                )
                raise ValueError(
                    "Codex exited unsuccessfully. No demo fallback was used. "
                    + diagnostic[-1500:]
                )
            progress("Collecting generated source and static files")
            # Remove generation-only inputs and dependencies before archive collection.
            container.exec_run(
                [
                    "sh",
                    "-c",
                    "rm -rf /workspace/skills /workspace/source/node_modules /workspace/source/.git",
                ],
                user="1000:1000",
            )
            # Docker's filesystem archive API omits tmpfs contents. Read the running
            # mount through exec instead; validate the untrusted tar on receipt.
            result = container.exec_run(
                [
                    "tar",
                    "cf",
                    "-",
                    "-C",
                    "/workspace",
                    "source",
                    "dist",
                    "manifest.json",
                ],
                stream=True,
                demux=True,
                user="1000:1000",
            )

            def output_chunks():
                for stdout, stderr in result.output:
                    if stderr:
                        raise ValueError(
                            "Could not collect source, dist, and manifest.json from the generation workspace"
                        )
                    if stdout:
                        yield stdout

            extract_output(output_chunks(), workspace)
        finally:
            for c in (container, broker):
                if c:
                    if self.debug:
                        try:
                            capture(c, self.debug)
                        except Exception:
                            pass
                    try:
                        c.remove(force=True)
                        if self.debug:
                            try:
                                data = self.debug.read(request["job_id"])
                                previous = next(
                                    (v for v in data["containers"] if v["id"] == c.id),
                                    None,
                                )
                                if previous:
                                    previous["status"] = "removed"
                                    self.debug.record(request["job_id"], previous)
                            except Exception:
                                pass
                    except docker.errors.DockerException:
                        pass
            if self.client is None:
                client.close()
