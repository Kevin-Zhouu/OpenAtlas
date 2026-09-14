"""Bounded file management only: installed skill code is never executed here."""

import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import threading
import zipfile

from .skills import MAX_SKILL_BYTES, SkillCatalog, inspect_tree

_LOCK = threading.RLock()


def skill_name(name):
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?", name) or "--" in name:
        raise ValueError("Use a lowercase, hyphenated skill name (up to 64 characters)")
    return name


def relative_path(value):
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or "\\" in value
        or any(p in ("..", ".") or ":" in p for p in value.split("/"))
    ):
        raise ValueError("Use a relative file path inside the skill")
    return path


class SkillEditor:
    def __init__(self, catalog):
        self.catalog = catalog

    def root(self, identifier, writable=False):
        records = {s["id"]: s for s in self.catalog.discover()}
        record = records.get(identifier)
        if not record:
            raise ValueError("Skill not found")
        if (
            identifier.startswith("builtin:")
            and (self.catalog.directory / ".builtin-overrides").is_symlink()
        ):
            raise ValueError("Symbolic links are not supported")
        root = Path(record["path"])
        inspect_tree(root)
        if writable and identifier.startswith("builtin:"):
            target = (
                self.catalog.directory
                / ".builtin-overrides"
                / skill_name(record["name"])
            )
            if target.parent.is_symlink():
                raise ValueError("Symbolic links are not supported")
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(root, target)
            root = target
        return root

    def read(self, identifier, path=None):
        with _LOCK:
            root = self.root(identifier)
            if path is None:
                return {
                    "files": [
                        str(p.relative_to(root))
                        for p in sorted(root.rglob("*"))
                        if p.is_file()
                    ]
                }
            file = root / relative_path(path)
            if not file.is_file() or file.stat().st_size > 500000:
                raise ValueError("File missing or larger than the 500 KB editor limit")
            data = file.read_bytes()
            try:
                content = data.decode("utf-8")
                if "\x00" in content:
                    raise UnicodeError()
            except UnicodeError:
                raise ValueError(
                    "This is a binary asset; only UTF-8 text files can be edited"
                )
            return {"content": content, "revision": hashlib.sha256(data).hexdigest()}

    def save(self, identifier, path, content, revision=None):
        with _LOCK:
            root = self.root(identifier, writable=True)
            file = root / relative_path(path)
            data = content.encode("utf-8")
            if len(data) > 500000:
                raise ValueError("Text file exceeds 500 KB")
            if file.exists():
                if (
                    not file.is_file()
                    or revision != hashlib.sha256(file.read_bytes()).hexdigest()
                ):
                    raise ValueError(
                        "File changed since you opened it. Reopen it before saving."
                    )
            elif revision is not None:
                raise ValueError("File was removed. Reopen the skill before saving.")
            size = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
            if (
                size - (file.stat().st_size if file.exists() else 0) + len(data)
                > MAX_SKILL_BYTES
            ):
                raise ValueError("Skill exceeds 20 MB")
            file.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(dir=file.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                os.replace(temporary, file)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            return self.read(identifier, path)

    def create(self, name):
        name = skill_name(name)
        with _LOCK:
            root = self.catalog.directory / name
            root.mkdir(parents=True, exist_ok=False)
            (root / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: Guidance for creating interactive learning Notebooks.\n---\n\n# {name}\n\nDescribe when to use this skill and how it should guide generation.\n",
                encoding="utf-8",
            )
            return {"id": "local:" + name}

    def install(self, data):
        with _LOCK:
            self.catalog.directory.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(
                prefix=".install-", dir=self.catalog.directory
            ) as temp:
                stage = Path(temp)
                try:
                    with zipfile.ZipFile(io.BytesIO(data)) as archive:
                        entries = archive.infolist()
                        if (
                            len(entries) > 2000
                            or sum(e.file_size for e in entries) > MAX_SKILL_BYTES
                        ):
                            raise ValueError("Skill exceeds 20 MB or 2000 files")
                        for entry in entries:
                            path = relative_path(entry.filename.rstrip("/"))
                            mode = entry.external_attr >> 16
                            if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                                raise ValueError("ZIP contains links or special files")
                            target = stage / path
                            if entry.is_dir():
                                target.mkdir(parents=True, exist_ok=True)
                            else:
                                target.parent.mkdir(parents=True, exist_ok=True)
                                with target.open("xb") as stream:
                                    stream.write(archive.read(entry))
                                if mode & 0o111:
                                    target.chmod(0o755)
                except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as e:
                    raise ValueError("Unable to read ZIP: " + str(e))
                # A portable skill folder ZIP, with exactly one top-level folder.
                folders = list(stage.iterdir())
                if len(folders) != 1 or not folders[0].is_dir():
                    raise ValueError(
                        "ZIP must contain one skill folder with SKILL.md inside it"
                    )
                name = skill_name(folders[0].name)
                records = SkillCatalog(stage).discover()
                record = next((s for s in records if s["id"] == "local:" + name), None)
                if not record or not record["valid"]:
                    raise ValueError(
                        record.get("error", "Invalid skill")
                        if record
                        else "Invalid skill"
                    )
                destination = self.catalog.directory / name
                if destination.exists():
                    raise ValueError(
                        "A skill with this name already exists. Edit it or choose a different name."
                    )
                folders[0].rename(destination)
                return {"id": "local:" + name}
