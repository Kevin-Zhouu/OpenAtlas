"""Write-only local credential configuration shared by the trusted API and runner.

Keys stay outside SQLite, Notebook artifacts and generation containers. Local
storage is permission-restricted, not encrypted; host administrators are trusted.
"""

import os
import tempfile
from pathlib import Path

from . import config


class Credentials:
    def __init__(self, data=None):
        self.directory = Path(data or config.DATA) / "private"
        self.path = self.directory / "openai-key"

    def status(self):
        if self.path.is_file():
            return {"configured": True, "source": "saved"}
        filename = os.getenv("OPENATLAS_OPENAI_KEY_FILE")
        if filename and Path(filename).is_file():
            return {"configured": True, "source": "file"}
        if os.getenv("OPENAI_API_KEY", "").strip():
            return {"configured": True, "source": "environment"}
        return {"configured": False, "source": "none"}

    def save(self, value):
        value = value.strip()
        if (
            not value.startswith("sk-")
            or not 16 <= len(value) <= 512
            or any(c.isspace() for c in value)
            or not value.isascii()
        ):
            raise ValueError("Enter a valid OpenAI API key beginning with sk-.")
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        fd, temporary = tempfile.mkstemp(prefix=".openai-", dir=self.directory)
        try:
            with os.fdopen(fd, "w") as file:
                file.write(value)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def remove(self):
        self.path.unlink(missing_ok=True)

    def openai_key(self):
        if self.path.is_file():
            value = self.path.read_text().strip()
        else:
            filename = os.getenv("OPENATLAS_OPENAI_KEY_FILE")
            value = (
                Path(filename).read_text().strip()
                if filename
                else os.getenv("OPENAI_API_KEY", "").strip()
            )
        if not value:
            raise ValueError(
                "Add an OpenAI API key in Settings to use Codex generation"
            )
        return value

    def configured(self):
        return self.status()["configured"]
