import hashlib
import re
import shutil
from pathlib import Path

import yaml

from . import config

CORE_SKILLS = ("builtin:openatlas-core", "builtin:blender")

MAX_SKILL_BYTES = 20 * 1024 * 1024


def inspect_tree(root):
    total = 0
    digest = hashlib.sha256()
    if root.is_symlink():
        raise ValueError("Symbolic links are not supported")
    for p in sorted(root.rglob("*")):
        if p.is_symlink() or not (p.is_file() or p.is_dir()):
            raise ValueError("Skill contains links or special files")
        if p.is_file():
            total += p.stat().st_size
            if total > MAX_SKILL_BYTES:
                raise ValueError("Skill exceeds 20 MB")
            digest.update(str(p.relative_to(root)).encode())
            digest.update(p.read_bytes())
    return digest.hexdigest()


class SkillCatalog:
    def __init__(self, directory=None):
        self.directory = Path(directory or config.SKILLS)

    def discover(self):
        result = []
        for prefix, root in [
            ("builtin", config.ROOT / "builtins"),
            ("local", self.directory),
        ]:
            if not root.exists():
                continue
            for folder in sorted(root.iterdir()):
                if folder.name.startswith(".") or not folder.is_dir():
                    continue
                if prefix == "builtin":
                    override = self.directory / ".builtin-overrides" / folder.name
                    if override.exists():
                        folder = override
                record = {
                    "id": prefix + ":" + folder.name,
                    "name": folder.name,
                    "description": "",
                    "required": prefix + ":" + folder.name in CORE_SKILLS,
                    "path": str(folder),
                    "valid": False,
                }
                try:
                    if (
                        not re.fullmatch(
                            r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?", folder.name
                        )
                        or "--" in folder.name
                    ):
                        raise ValueError(
                            "Use a lowercase, hyphenated skill folder name"
                        )
                    if (
                        prefix == "builtin"
                        and (self.directory / ".builtin-overrides").is_symlink()
                    ):
                        raise ValueError("Symbolic links are not supported")
                    digest = inspect_tree(folder)
                    raw = (folder / "SKILL.md").read_text()
                    if len(raw) > 100000 or not raw.startswith("---\n"):
                        raise ValueError("Expected YAML frontmatter in SKILL.md")
                    header = re.match(r"\A---\n(.*?)\n---(?:\n|$)", raw, re.S)
                    if not header:
                        raise ValueError(
                            "SKILL.md needs a closing frontmatter delimiter"
                        )
                    meta = yaml.safe_load(header.group(1))
                    if (
                        not isinstance(meta, dict)
                        or meta.get("name") != folder.name
                        or not isinstance(meta.get("description"), str)
                        or not meta["description"].strip()
                        or len(meta["description"]) > 1024
                    ):
                        raise ValueError(
                            "Frontmatter needs matching name and a description"
                        )
                    metadata = meta.get("metadata") or {}
                    record.update(
                        name=meta["name"],
                        description=meta["description"],
                        version=str(metadata.get("version", ""))
                        if isinstance(metadata, dict)
                        else "",
                        sha256=digest,
                        valid=True,
                    )
                except (ValueError, OSError, yaml.YAMLError, IndexError) as e:
                    record["error"] = str(e)
                result.append(record)
        return result

    def resolve(self, ids):
        catalog = {s["id"]: s for s in self.discover()}
        chosen = list(dict.fromkeys(list(CORE_SKILLS) + ids))
        output = []
        for id in chosen:
            s = catalog.get(id)
            if not s or not s["valid"]:
                raise ValueError("Skill unavailable or malformed: " + id)
            output.append({k: v for k, v in s.items() if k not in ("path", "error")})
        return output

    def stage(self, selected, destination):
        catalog = {s["id"]: s for s in self.discover()}
        for s in selected:
            current = catalog.get(s["id"])
            if not current or not current["valid"] or current["sha256"] != s["sha256"]:
                raise ValueError(
                    "Selected skill changed or was removed; submit again: " + s["id"]
                )
            target = destination / s["id"].replace(":", "--")
            shutil.copytree(current["path"], target)
            if inspect_tree(target) != s["sha256"]:
                raise ValueError("Skill changed while copying")

    def snapshot(self, selected, cache):
        """Retain immutable inputs privately for later prompt builds, never publish them."""
        import tempfile

        cache = Path(cache)
        cache.mkdir(parents=True, exist_ok=True, mode=0o700)
        for skill in selected:
            target = cache / skill["sha256"]
            if target.exists() and inspect_tree(target) == skill["sha256"]:
                continue
            with tempfile.TemporaryDirectory(dir=cache) as tmp:
                self.stage([skill], Path(tmp))
                folder = Path(tmp) / skill["id"].replace(":", "--")
                try:
                    folder.rename(target)
                except OSError:
                    if inspect_tree(target) != skill["sha256"]:
                        raise ValueError("Invalid skill snapshot")

    def stage_snapshots(self, selected, cache, destination):
        for skill in selected:
            source = Path(cache) / skill["sha256"]
            if not source.is_dir() or inspect_tree(source) != skill["sha256"]:
                raise ValueError("Saved skill snapshot unavailable: " + skill["id"])
            shutil.copytree(source, destination / skill["id"].replace(":", "--"))
