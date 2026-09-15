"""Codex-managed ChatGPT login. Only the trusted runner talks to Docker."""

import json
import os
import re
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from . import config

LOGIN_TIMEOUT = 15 * 60
AUTH_PATH = "/tmp/home/.codex/auth.json"


def auth_secrets(auth):
    tokens = auth.get("tokens") or {}
    return [
        v
        for k, v in tokens.items()
        if k in ("access_token", "refresh_token", "id_token")
        and isinstance(v, str)
        and v
    ]


def validate_auth(auth):
    if (
        not isinstance(auth, dict)
        or auth.get("auth_mode") != "chatgpt"
        or not auth_secrets(auth)
    ):
        raise ValueError(
            "Codex did not produce a ChatGPT subscription login. Sign in again in Settings."
        )
    if not (auth.get("tokens") or {}).get("access_token"):
        raise ValueError("The ChatGPT login is incomplete. Sign in again in Settings.")
    return auth


def upload_auth(client, container, auth):
    """Transfer a private login cache without command-line or environment tokens."""
    validate_auth(auth)
    execution = client.api.exec_create(
        container.id,
        ["sh", "-c", "umask 077; cat > " + AUTH_PATH],
        stdin=True,
        user="1000:1000",
    )
    connection = client.api.exec_start(execution["Id"], socket=True)
    try:
        import socket

        connection._sock.sendall(json.dumps(auth).encode())
        connection._sock.shutdown(socket.SHUT_WR)
        while client.api.exec_inspect(execution["Id"])["Running"]:
            time.sleep(0.05)
        if client.api.exec_inspect(execution["Id"])["ExitCode"] != 0:
            raise ValueError("Could not transfer the subscription login")
    finally:
        connection.close()


class SubscriptionStore:
    _locks = {}

    def __init__(self, data=None):
        self.directory = Path(data or config.DATA) / "private"
        self.path = self.directory / "subscription.json"
        self.worker_path = self.directory / "subscription-worker"
        self.lock = self._locks.setdefault(
            str(self.directory.resolve()), threading.RLock()
        )

    @contextmanager
    def transaction(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.lock, (self.directory / ".subscription.lock").open("a+b") as lock:
            # API and runner are separate Linux containers sharing the data volume.
            import fcntl

            os.chmod(lock.name, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _read(self):
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return {"status": "signed_out", "epoch": None}

    def _write(self, state):
        fd, name = tempfile.mkstemp(dir=self.directory, prefix=".subscription-")
        try:
            with os.fdopen(fd, "w") as out:
                json.dump(state, out)
                out.flush()
                os.fsync(out.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def heartbeat(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.worker_path.touch(mode=0o600)

    def available(self):
        try:
            return time.time() - self.worker_path.stat().st_mtime < 30
        except FileNotFoundError:
            return False

    def status(self):
        state = self._read()
        result = {
            k: state[k]
            for k in (
                "status",
                "user_code",
                "verification_url",
                "expires_at",
                "email",
                "plan",
                "message",
            )
            if k in state
        }
        if state.get("status") in ("pending", "waiting") and time.time() > state.get(
            "expires_at", 0
        ):
            result = {
                "status": "error",
                "message": "Sign-in expired. Start sign-in again.",
            }
        return dict(result, runner_available=self.available())

    def start(self):
        with self.transaction():
            state = self._read()
            if state["status"] == "signed_in":
                raise ValueError(
                    "Already signed in. Sign out before changing accounts."
                )
            if state["status"] in ("pending", "waiting") and time.time() < state.get(
                "expires_at", 0
            ):
                return self.status()
            self._write(
                {
                    "status": "pending",
                    "epoch": str(uuid4()),
                    "expires_at": time.time() + LOGIN_TIMEOUT,
                }
            )
            return self.status()

    def sign_out(self):
        with self.transaction():
            # Invalidate pending callbacks and refresh writes from running containers.
            self._write({"status": "signed_out", "epoch": str(uuid4())})
            return self.status()

    def update(self, epoch, **fields):
        with self.transaction():
            state = self._read()
            if state.get("epoch") != epoch:
                return False
            state.update(fields)
            if state["status"] not in ("pending", "waiting"):
                for key in ("user_code", "verification_url", "expires_at"):
                    state.pop(key, None)
            self._write(state)
            return True

    def session(self, epoch=None):
        with self.transaction():
            state = self._read()
            if state["status"] != "signed_in" or (
                epoch is not None and epoch != state.get("epoch")
            ):
                raise ValueError(
                    "Sign in with ChatGPT in Settings to use subscription mode. API keys will not be used as a fallback."
                )
            return {
                "mode": "chatgpt",
                "epoch": state["epoch"],
                "auth": validate_auth(state["auth"]),
            }

    def current(self, epoch):
        state = self._read()
        return state.get("epoch") == epoch and state["status"] == "signed_in"

    def refresh(self, epoch, auth):
        validate_auth(auth)
        with self.transaction():
            state = self._read()
            if state.get("epoch") != epoch or state["status"] != "signed_in":
                return False
            state["auth"] = auth
            self._write(state)
            return True


class SubscriptionWorker:
    def __init__(self, store, client=None):
        self.store = store
        self.client = client
        self.container = None
        self.epoch = None

    def cleanup(self):
        if self.container:
            try:
                self.container.remove(force=True)
            finally:
                self.container = None

    def tick(self):
        self.store.heartbeat()
        state = self.store._read()
        active = state["status"] in ("pending", "waiting")
        if self.container and (self.epoch != state.get("epoch") or not active):
            self.cleanup()
        if not active:
            return
        self.epoch = state["epoch"]
        if time.time() > state["expires_at"]:
            self.cleanup()
            self.store.update(
                self.epoch,
                status="error",
                message="Sign-in expired. Start sign-in again.",
            )
            return
        if not self.container:
            import docker

            self.client = self.client or docker.from_env(timeout=10)
            self.container = self.client.containers.run(
                config.GENERATION_IMAGE,
                ["python3", "/opt/subscription_login.py"],
                detach=True,
                network_mode="bridge",
                read_only=True,
                environment={"HOME": "/tmp/home", "CODEX_HOME": "/tmp/home/.codex"},
                tmpfs={"/tmp": "rw,nosuid,uid=1000,gid=1000,size=128m"},
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                mem_limit="512m",
                pids_limit=128,
                labels={
                    "openatlas.login": self.epoch,
                    "openatlas.expires": str(state["expires_at"]),
                },
                log_config=docker.types.LogConfig(
                    type="json-file", config={"max-size": "64k", "max-file": "1"}
                ),
            )
        self.container.reload()
        for line in (
            self.container.logs(tail=10).decode("utf-8", errors="replace").splitlines()
        ):
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "login.waiting":
                url, code = (
                    event.get("verification_url", ""),
                    event.get("user_code", ""),
                )
                if url != "https://auth.openai.com/codex/device" or not re.fullmatch(
                    r"[A-Z0-9-]{6,32}", code
                ):
                    raise ValueError("Unexpected device login response")
                self.store.update(
                    self.epoch, status="waiting", verification_url=url, user_code=code
                )
            elif event.get("type") == "login.completed":
                result = self.container.exec_run(["cat", AUTH_PATH])
                if result.exit_code:
                    raise ValueError("Login cache missing")
                auth = validate_auth(json.loads(result.output))
                self.store.update(
                    self.epoch,
                    status="signed_in",
                    auth=auth,
                    email=str(event.get("email") or "")[:254],
                    plan=str(event.get("plan") or "unknown")[:50],
                )
                self.cleanup()
                return
            elif event.get("type") == "login.error":
                raise ValueError("Codex login failed")
        if self.container.status != "running":
            raise ValueError("Login container exited")

    def run(self, stop):
        try:
            # Remove interrupted sign-in containers; a replacement gets a fresh code.
            import docker

            self.client = self.client or docker.from_env(timeout=10)
            for container in self.client.containers.list(
                all=True, filters={"label": "openatlas.login"}
            ):
                container.remove(force=True)
            while not stop.is_set():
                try:
                    self.tick()
                except Exception:
                    try:
                        self.cleanup()
                    except Exception:
                        pass
                    if self.epoch:
                        self.store.update(
                            self.epoch,
                            status="error",
                            message="Could not sign in. Check the runner and Docker, enable device-code login in ChatGPT security settings, then try again.",
                        )
                stop.wait(2)
        finally:
            self.cleanup()
            if self.client:
                self.client.close()
