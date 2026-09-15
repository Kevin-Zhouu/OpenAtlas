"""Trusted capture of artifact identity and successful image-returning tool calls."""

import hashlib
import json
from pathlib import Path

root = Path("/workspace")
hash_value = hashlib.sha256()
for path in sorted((root / "dist").rglob("*")) + [root / "manifest.json"]:
    if path.is_symlink():
        raise ValueError("Artifact contains a link")
    if path.is_file():
        hash_value.update(str(path.relative_to(root)).encode())
        hash_value.update(b"\0")
        hash_value.update(path.read_bytes())
calls = 0
log = Path("/tmp/codex-output.log")
if log.exists():
    for line in log.open():
        try:
            event = json.loads(line)
            item = event.get("item", {})
            if (
                event.get("type") == "item.completed"
                and item.get("type") == "mcp_tool_call"
                and item.get("tool") == "browser_take_screenshot"
                and not item.get("error")
                and item.get("status") != "failed"
            ):
                # The tool must actually return image content, not just a file path.
                content = (item.get("result") or {}).get("content", [])
                if any(block.get("type") == "image" for block in content):
                    calls += 1
        except (ValueError, AttributeError):
            continue
print(
    json.dumps({"artifact_sha256": hash_value.hexdigest(), "screenshot_calls": calls})
)
