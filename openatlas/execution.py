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
from .debug import capture, redact
from .subscription import AUTH_PATH, SubscriptionStore, auth_secrets, upload_auth


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


def extract_output(chunks, destination, secrets=()):
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
                    content = src.read()
                    if any(secret and secret.encode() in content for secret in secrets):
                        raise ValueError(
                            "Generation output contains a private credential and cannot be saved"
                        )
                    out.write(content)


class DockerExecutor:
    def __init__(
        self,
        credentials=None,
        client=None,
        adapter=None,
        debug=None,
        checkpoint_store=None,
        cancelled=None,
    ):
        self.cancelled = cancelled or (lambda request: False)
        self.credentials = credentials or Credentials()
        self.client = client
        self.adapter = adapter or CodexAdapter()
        self.debug = debug
        self.checkpoint_store = checkpoint_store
        self.subscription = SubscriptionStore(
            self.credentials.directory.parent
            if isinstance(self.credentials, Credentials)
            else None
        )

    def run(self, workspace, request, progress, connection=None):
        if self.cancelled(request):
            raise ValueError("Generation cancelled before dispatch")
        connection = connection or (
            self.subscription.session()
            if request.get("inference_auth") == "chatgpt"
            else self.credentials.connection()
        )
        subscription = connection.get("mode") == "chatgpt"
        if subscription:
            connection = self.subscription.session(connection["epoch"])
            request = dict(request, inference_auth="chatgpt")
        client = self.client or docker.from_env()
        key = connection.get("api_key", "")
        token = secrets.token_urlsafe(32)
        private_values = [key, token] + (
            auth_secrets(connection["auth"]) if subscription else []
        )
        broker = container = None
        planning = request.get("execution_stage") == "planning"
        timeout_seconds = (
            request.get("generation_timeout_minutes", config.TIMEOUT / 60) * 60
        )
        deadline = time.monotonic() + timeout_seconds
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
                    "openatlas.stage": "planning" if planning else "building",
                    "openatlas.expires": str(time.time() + timeout_seconds + 120),
                    "openatlas.authentication": "chatgpt"
                    if subscription
                    else "api_key",
                },
                log_config=docker.types.LogConfig(
                    type="json-file", config={"max-size": "5m", "max-file": "1"}
                ),
            )
            if not subscription:
                broker = client.containers.run(
                    command=["python3", "/opt/broker.py"],
                    environment={
                        "OPENAI_API_KEY": key,
                        "RELAY_TOKEN": token,
                        "INFERENCE_BASE_URL": connection["base_url"],
                    },
                    network_mode="bridge",
                    tmpfs={"/tmp": "rw,noexec,nosuid,size=32m"},
                    **common,
                )
            container = client.containers.run(
                command=["sleep", "infinity"],
                environment={
                    **(
                        {"OPENATLAS_AUTH_MODE": "chatgpt"}
                        if subscription
                        else {"CODEX_API_KEY": token}
                    ),
                    "HOME": "/tmp/home",
                    "CODEX_HOME": "/tmp/home/.codex",
                },
                network_mode="bridge" if subscription else "container:" + broker.id,
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
            upload_connection = client.api.exec_start(upload["Id"], socket=True)
            try:
                upload_connection._sock.sendall(archive_input(workspace))
                upload_connection._sock.shutdown(socket.SHUT_WR)
                while client.api.exec_inspect(upload["Id"])["Running"]:
                    time.sleep(0.1)
                if client.api.exec_inspect(upload["Id"])["ExitCode"] != 0:
                    raise ValueError(
                        "Could not transfer the isolated generation workspace"
                    )
            finally:
                upload_connection.close()
            container.exec_run(["mkdir", "-p", "/tmp/home/.codex"], user="1000:1000")
            if subscription:
                upload_auth(client, container, connection["auth"])
            progress(
                "Planner is designing your Notebook"
                if planning
                else "Codex is writing, building, and testing your Notebook"
            )
            agent_command = self.adapter.command(request)
            if self.debug:
                self.debug.record_invocation(
                    request["job_id"],
                    agent_command,
                    request,
                    private_values,
                    execution={
                        "container_id": container.id,
                        "image": config.GENERATION_IMAGE,
                        "timeout_seconds": timeout_seconds,
                        "workdir": "/workspace",
                        "user": "1000:1000",
                    },
                )
            command = [
                "sh",
                "-c",
                'exec "$@" > /tmp/codex-output.log 2>&1',
                "openatlas",
            ] + agent_command
            execution = client.api.exec_create(
                container.id, command, workdir="/workspace", user="1000:1000"
            )
            if self.cancelled(request):
                raise ValueError("Generation cancelled before agent invocation")
            client.api.exec_start(execution["Id"], detach=True)
            while client.api.exec_inspect(execution["Id"])["Running"]:
                if subscription and not self.subscription.current(connection["epoch"]):
                    raise ValueError(
                        "ChatGPT was signed out. Sign in again and retry this job."
                    )
                if self.cancelled(request):
                    raise ValueError(
                        "Generation cancelled or runner stopping; retry from saved output"
                    )
                if time.monotonic() > deadline:
                    raise ValueError(
                        ("Planning" if planning else "Codex generation")
                        + f" exceeded the configured {timeout_seconds / 60:g}-minute time limit. Increase Generation time limit in Settings, then continue or retry."
                    )
                time.sleep(2)
            if subscription:
                if not self.subscription.current(connection["epoch"]):
                    raise ValueError(
                        "ChatGPT was signed out. Sign in again and retry this job."
                    )
                refreshed = container.exec_run(["head", "-c", "200001", AUTH_PATH])
                if refreshed.exit_code == 0:
                    private_values += auth_secrets(json.loads(refreshed.output))
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
                diagnostic = redact(
                    messages[-1] if messages else diagnostic[-600:], private_values
                )
                raise ValueError(
                    ("Planner" if planning else "Codex")
                    + " exited unsuccessfully. No demo fallback was used. "
                    + diagnostic[-1500:]
                )
            if planning:
                from .planning import validate_prompt

                result = container.exec_run(
                    ["head", "-c", "160001", "/workspace/plan.md"], user="1000:1000"
                )
                if result.exit_code != 0:
                    raise ValueError("Planning failed: missing build prompt")
                return validate_prompt(
                    redact(result.output.decode("utf-8"), private_values)
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

            extract_output(output_chunks(), workspace, private_values)
        except Exception:
            # Collect only deliverable files, never agent home/auth/history or
            # skills. A failed generation can be partial and lack a manifest.
            if (
                not planning
                and container is not None
                and self.checkpoint_store is not None
            ):
                try:
                    import tempfile

                    result = container.exec_run(
                        [
                            "tar",
                            "cf",
                            "-",
                            "--exclude=node_modules",
                            "--exclude=.git",
                            "--exclude=.env*",
                            "--ignore-failed-read",
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
                    with tempfile.TemporaryDirectory(
                        prefix="openatlas-checkpoint-"
                    ) as tmp:
                        saved = Path(tmp)
                        extract_output(
                            (out for out, err in result.output if out),
                            saved,
                            private_values,
                        )
                        if self.checkpoint_store.checkpoint(request["job_id"], saved):
                            progress("Saved partial work; this job can be continued")
                except Exception:
                    # Never replace the original provider error with a recovery
                    # error or claim that an incomplete/unsafe archive was saved.
                    pass
            raise
        finally:
            if subscription and container is not None:
                try:
                    refreshed = container.exec_run(["head", "-c", "200001", AUTH_PATH])
                    if refreshed.exit_code == 0:
                        self.subscription.refresh(
                            connection["epoch"], json.loads(refreshed.output)
                        )
                except Exception:
                    # Preserve sign-out/cancellation and the original execution error.
                    pass
            for c in (container, broker):
                if c:
                    if self.debug:
                        try:
                            capture(
                                c,
                                self.debug,
                                extra_secrets=private_values,
                                archive=True,
                            )
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
