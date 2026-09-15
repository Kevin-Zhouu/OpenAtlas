"""Private, write-only inference profiles shared by the API and trusted runner.

Keys stay outside SQLite, Notebook artifacts and generation containers. Local
storage is permission-restricted, not encrypted; host administrators are trusted.
"""

import json
import os
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from . import config

DEFAULT_BASE_URL = "https://api.openai.com/v1"


def validate_base_url(value):
    value = value.strip().rstrip("/")
    message = "Enter an HTTP or HTTPS API base URL without credentials, query parameters or a fragment (for example, https://api.example.com/v1)."
    try:
        url = urlsplit(value)
        if (
            not 1 <= len(value) <= 2048
            or not value.isascii()
            or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
            or "\\" in value
            or url.scheme not in ("http", "https")
            or not url.hostname
            or url.username is not None
            or url.password is not None
            or "?" in value
            or "#" in value
            or url.port == 0
        ):
            raise ValueError(message)
    except ValueError:
        raise ValueError(message) from None
    if url.path.endswith(("/responses", "/responses/compact", "/chat/completions")):
        raise ValueError(
            "Enter the API base URL, without /responses or /chat/completions."
        )
    return urlunsplit((url.scheme, url.netloc, url.path, "", ""))


def validate_key(value):
    value = value.strip()
    if not 1 <= len(value) <= 4096 or not all(33 <= ord(c) <= 126 for c in value):
        raise ValueError(
            "Enter an API key with 1–4096 printable ASCII characters and no spaces."
        )
    return value


class Credentials:
    _locks = {}

    def __init__(self, data=None):
        self.directory = Path(data or config.DATA) / "private"
        self.path = self.directory / "openai-key"  # pre-profile installations
        self.profiles_path = self.directory / "inference-profiles.json"
        self.lock = self._locks.setdefault(
            str(self.directory.resolve()), threading.RLock()
        )

    def _read(self):
        if self.profiles_path.is_file():
            return json.loads(self.profiles_path.read_text())
        # Read the legacy key as a profile. Migrate atomically on the first edit.
        if self.path.is_file():
            return {
                "active_id": "openai",
                "profiles": [
                    {
                        "id": "openai",
                        "name": "OpenAI",
                        "base_url": DEFAULT_BASE_URL,
                        "api_key": self.path.read_text().strip(),
                    }
                ],
            }
        return {"active_id": "host", "profiles": []}

    def _write(self, state):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        fd, temporary = tempfile.mkstemp(prefix=".profiles-", dir=self.directory)
        try:
            with os.fdopen(fd, "w") as file:
                json.dump(state, file)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.profiles_path)
            self.path.unlink(missing_ok=True)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def _host(self):
        filename = os.getenv("OPENATLAS_OPENAI_KEY_FILE")
        source = "none"
        value = ""
        if filename and Path(filename).is_file():
            value, source = Path(filename).read_text().strip(), "file"
        elif os.getenv("OPENAI_API_KEY", "").strip():
            value, source = os.environ["OPENAI_API_KEY"].strip(), "environment"
        return {
            "id": "host",
            "name": "Host configuration",
            "source": source,
            "api_key": value,
            "base_url": validate_base_url(
                os.getenv("OPENATLAS_API_BASE_URL") or DEFAULT_BASE_URL
            ),
        }

    def profiles(self):
        with self.lock:
            state = self._read()
            profiles = [dict(p, source="saved") for p in state["profiles"]] + [
                self._host()
            ]
            return {
                "active_id": state["active_id"],
                "profiles": [
                    {
                        "id": p["id"],
                        "name": p["name"],
                        "base_url": p["base_url"],
                        "configured": bool(p["api_key"]),
                        "source": p["source"],
                    }
                    for p in profiles
                ],
            }

    def _selected(self, state):
        if state["active_id"] == "host":
            return self._host()
        return dict(self._find(state, state["active_id"]), source="saved")

    @staticmethod
    def _find(state, profile_id):
        for profile in state["profiles"]:
            if profile["id"] == profile_id:
                return profile
        raise ValueError(
            "API provider profile no longer exists. Select a profile in Settings."
        )

    def status(self):
        with self.lock:
            profile = self._selected(self._read())
            return {"configured": bool(profile["api_key"]), "source": profile["source"]}

    def save_profile(
        self, name, base_url, api_key=None, profile_id=None, activate=False
    ):
        name = name.strip()
        if not 1 <= len(name) <= 80 or any(ord(c) < 32 for c in name):
            raise ValueError("Enter a provider name with 1–80 characters.")
        base_url = validate_base_url(base_url)
        with self.lock:
            state = self._read()
            existing = self._find(state, profile_id) if profile_id else None
            key = (
                validate_key(api_key)
                if api_key and api_key.strip()
                else (existing["api_key"] if existing else "")
            )
            if not key:
                raise ValueError("Enter an API key for the new provider profile.")
            profile = {
                "id": profile_id or str(uuid4()),
                "name": name,
                "base_url": base_url,
                "api_key": key,
            }
            state["profiles"] = [
                profile if p["id"] == profile_id else p for p in state["profiles"]
            ]
            if not existing:
                state["profiles"].append(profile)
            if activate:
                state["active_id"] = profile["id"]
            self._write(state)
            return self.profiles()

    def activate(self, profile_id):
        with self.lock:
            state = self._read()
            if profile_id != "host":
                self._find(state, profile_id)
            state["active_id"] = profile_id
            self._write(state)
            return self.profiles()

    def delete_profile(self, profile_id):
        with self.lock:
            state = self._read()
            self._find(state, profile_id)
            state["profiles"] = [p for p in state["profiles"] if p["id"] != profile_id]
            if state["active_id"] == profile_id:
                state["active_id"] = "host"
            self._write(state)
            return self.profiles()

    def save(self, value):
        """Compatibility for older clients using the single-key endpoint."""
        value = validate_key(value)
        with self.lock:
            state = self._read()
            profile = self._selected(state)
            self.save_profile(
                profile["name"] if profile["id"] != "host" else "OpenAI",
                profile["base_url"],
                value,
                profile_id=profile["id"] if profile["id"] != "host" else None,
                activate=True,
            )

    def remove(self):
        with self.lock:
            active = self._read()["active_id"]
            if active != "host":
                self.delete_profile(active)

    def connection(self):
        """Resolve key and URL together; retain only in trusted worker memory."""
        with self.lock:
            profile = self._selected(self._read())
            if not profile["api_key"]:
                raise ValueError(
                    "Add an API provider and key in Settings to use Codex generation"
                )
            return {"api_key": profile["api_key"], "base_url": profile["base_url"]}

    def openai_key(self):
        return self.connection()["api_key"]

    def configured(self):
        return self.status()["configured"]
