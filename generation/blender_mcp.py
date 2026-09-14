"""Own a private Blender/display for this MCP session; stdout is MCP-only."""

import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


def main():
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENATLAS_ACCESS_TOKEN")
    }
    env.update(
        BLENDER_HOST="127.0.0.1",
        BLENDER_PORT="9876",
        BLENDER_MCP_DISABLE_TELEMETRY="1",
        LIBGL_ALWAYS_SOFTWARE="1",
        XDG_CACHE_HOME="/tmp/home/.cache",
        OMP_NUM_THREADS="2",
        OPENBLAS_NUM_THREADS="2",
        LP_NUM_THREADS="2",
    )
    Path(env.get("HOME", "/tmp/home")).mkdir(parents=True, exist_ok=True)
    children = []

    def stop(signum, frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        with open("/tmp/blender-output.log", "a") as log:
            blender = subprocess.Popen(
                [
                    "xvfb-run",
                    "-a",
                    "-s",
                    "-screen 0 1280x720x24 -nolisten tcp",
                    "blender",
                    "--threads",
                    "2",
                    "--factory-startup",
                    "-noaudio",
                    "--python",
                    "/opt/blender_startup.py",
                ],
                env=env,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
            children.append(blender)
            deadline = time.monotonic() + 75
            while True:
                if blender.poll() is not None:
                    raise RuntimeError(
                        "Blender startup failed; see /tmp/blender-output.log"
                    )
                try:
                    with socket.create_connection(("127.0.0.1", 9876), timeout=1):
                        break
                except OSError:
                    if time.monotonic() > deadline:
                        raise RuntimeError(
                            "Blender startup timed out; see /tmp/blender-output.log"
                        )
                    time.sleep(0.25)
            server = subprocess.Popen(
                ["/opt/blender-mcp/bin/python", "/opt/blender_server.py"],
                env=env,
                start_new_session=True,
            )
            children.append(server)
            return server.wait()
    except Exception:
        log_path = Path("/tmp/blender-output.log")
        if log_path.exists():
            print(log_path.read_text(errors="replace")[-8000:], file=sys.stderr)
        raise
    finally:
        for child in reversed(children):
            try:
                os.killpg(child.pid, signal.SIGTERM)
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            except ProcessLookupError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
