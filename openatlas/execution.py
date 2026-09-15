"""Disposable Docker execution. Inputs/outputs use archives, never host bind mounts."""

import io
import json
import secrets
import socket
import tarfile
import tempfile
import time
from pathlib import Path

import docker

from . import config
from .agent_session import session_archive, thread_id
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
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    # A returned workspace is a snapshot, not an overlay: repairs can delete files.
    # Validate everything in staging before replacing any existing deliverable.
    with tempfile.TemporaryDirectory(
        prefix=destination.name + "-output-", dir=destination.parent
    ) as temporary:
        staged = Path(temporary) / "incoming"
        staged.mkdir()
        total = 0
        with tarfile.open(fileobj=stream) as tar:
            for member in tar:
                parts = Path(member.name).parts
                if parts and parts[0] == "workspace":
                    parts = parts[1:]
                if not parts or parts[0] not in ("source", "dist", "manifest.json"):
                    continue
                path = staged.joinpath(*parts).resolve()
                if not path.is_relative_to(staged.resolve()) or not (
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
                    with tar.extractfile(member) as src:
                        content = src.read()
                    if any(secret and secret.encode() in content for secret in secrets):
                        raise ValueError(
                            "Generation output contains a private credential and cannot be saved"
                        )
                    path.write_bytes(content)
        if not any(staged.iterdir()):
            raise ValueError("Generation archive contains no deliverables")
        backup = Path(temporary) / "previous"
        backup.mkdir()
        replaced = []
        try:
            for name in ("source", "dist", "manifest.json"):
                target = destination / name
                old = backup / name
                if target.exists() or target.is_symlink():
                    target.rename(old)
                replaced.append(name)
                incoming = staged / name
                if incoming.exists():
                    incoming.rename(target)
        except Exception:
            for name in reversed(replaced):
                target = destination / name
                if target.exists() or target.is_symlink():
                    target.rename(staged / name)
                old = backup / name
                if old.exists() or old.is_symlink():
                    old.rename(target)
            raise


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
        self._sessions = {}
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

    def release(self, job_id):
        """Discard private in-memory conversation state at job completion/cancellation."""
        self._sessions.pop(job_id, None)

    def run(self, workspace, request, progress, connection=None):
        request = dict(request)
        reviewing = request.get("execution_stage") == "reviewing"
        resumable = (
            isinstance(self.adapter, CodexAdapter)
            and not reviewing
            and request.get("execution_stage") != "planning"
        )
        previous_session = (
            self._sessions.get(request.get("job_id")) if resumable else None
        )
        if previous_session:
            request["resume_session_id"] = previous_session[0]
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
        if reviewing:
            from .quality import review_timeout

            timeout_seconds = min(timeout_seconds, review_timeout(request))
        deadline = time.monotonic() + timeout_seconds
        try:
            common = dict(
                image=config.GENERATION_IMAGE,
                detach=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                read_only=True,
                # Codex plus MCP Chromium and a separate browser test need headroom.
                pids_limit=512,
                mem_limit=config.GENERATION_MEMORY,
                nano_cpus=int(config.GENERATION_CPUS * 1_000_000_000),
                labels={
                    "openatlas.job": request["job_id"],
                    "openatlas.stage": "planning"
                    if planning
                    else "validating"
                    if reviewing
                    else "building",
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
                    "/workspace": "rw,exec,nosuid,uid=1000,gid=1000,size=2g",
                    "/tmp": "rw,nosuid,uid=1000,gid=1000,size=512m",
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
            if previous_session:
                transfer = client.api.exec_create(
                    container.id,
                    ["tar", "xf", "-", "-C", "/tmp/home/.codex"],
                    stdin=True,
                    user="1000:1000",
                )
                channel = client.api.exec_start(transfer["Id"], socket=True)
                try:
                    channel._sock.sendall(previous_session[1])
                    channel._sock.shutdown(socket.SHUT_WR)
                    while client.api.exec_inspect(transfer["Id"])["Running"]:
                        time.sleep(0.1)
                    if client.api.exec_inspect(transfer["Id"])["ExitCode"] != 0:
                        raise ValueError(
                            "Could not restore the implementation conversation"
                        )
                finally:
                    channel.close()

            progress(
                "Planner is designing your Notebook"
                if planning
                else (
                    "Codex is rechecking the reported fixes and affected interactions"
                    if request.get("experience_review_state")
                    else "Codex is independently reviewing the learning experience"
                )
                if reviewing
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
                        "resume_session_id": request.get("resume_session_id"),
                        "reviewing": reviewing,
                        "memory": config.GENERATION_MEMORY,
                        "cpus": config.GENERATION_CPUS,
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
                    if reviewing:
                        from .quality import ReviewUnavailable

                        raise ReviewUnavailable(
                            f"Independent review exceeded its {timeout_seconds / 60:g}-minute budget; the built application is retained for Continue."
                        )
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
            if resumable:
                start = container.exec_run(
                    ["head", "-c", "65536", "/tmp/codex-output.log"]
                )
                identifier = thread_id(start.output.decode("utf-8", errors="replace"))
                history = container.exec_run(
                    [
                        "sh",
                        "-c",
                        "tar cf - -C /tmp/home/.codex sessions | head -c 33554433",
                    ]
                )
                if history.exit_code != 0:
                    raise ValueError(
                        "Could not preserve the implementation session for review and repair"
                    )
                self._sessions[request["job_id"]] = (
                    identifier,
                    session_archive(history.output, private_values),
                )
            review_result = review_probe = None
            if reviewing:
                from .quality import artifact_fingerprint

                result = container.exec_run(
                    ["head", "-c", "100001", "/workspace/quality-result.json"]
                )
                if result.exit_code != 0 or len(result.output) > 100000:
                    raise ValueError(
                        "Independent experience review did not return a bounded report"
                    )
                review_result = json.loads(result.output)
                probe = container.exec_run(["python3", "/opt/review_probe.py"])
                if probe.exit_code != 0:
                    raise ValueError("Could not verify independent review evidence")
                review_probe = json.loads(probe.output)
                if review_probe["artifact_sha256"] != artifact_fingerprint(workspace):
                    raise ValueError(
                        "Reviewer changed the artifact; it cannot approve publication"
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
            if reviewing:
                from .quality import save_review, validate_review

                save_review(
                    workspace,
                    review_result,
                    review_probe["artifact_sha256"],
                    review_probe["screenshot_calls"],
                )
                return validate_review(
                    review_result,
                    workspace,
                    review_probe["screenshot_calls"],
                    request.get("experience_review_state"),
                )
        except Exception:
            # Collect only deliverable files, never agent home/auth/history or
            # skills. A failed generation can be partial and lack a manifest.
            if (
                not planning
                and not reviewing
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
                        prefix=request["job_id"] + "-checkpoint-", dir=workspace.parent
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
