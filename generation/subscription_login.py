"""Headless login using Codex's documented account RPC; never print tokens."""

import json
import os
import subprocess
from pathlib import Path


def emit(kind, **fields):
    print(json.dumps({"type": kind, **fields}), flush=True)


def main():
    Path(os.environ["CODEX_HOME"]).mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        [
            "codex",
            "app-server",
            "-c",
            'cli_auth_credentials_store="file"',
            "-c",
            'forced_login_method="chatgpt"',
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    def send(method, params, request_id=None):
        payload = {"method": method, "params": params}
        if request_id is not None:
            payload["id"] = request_id
        process.stdin.write(json.dumps(payload) + "\n")
        process.stdin.flush()

    try:
        send("initialize", {"clientInfo": {"name": "openatlas", "version": "0.1.0"}}, 1)
        login_id = None
        for line in process.stdout:
            event = json.loads(line)
            if event.get("error"):
                raise ValueError("Login request failed")
            if event.get("id") == 1:
                send("initialized", {})
                send("account/login/start", {"type": "chatgptDeviceCode"}, 2)
            elif event.get("id") == 2:
                result = event["result"]
                login_id = result["loginId"]
                emit(
                    "login.waiting",
                    verification_url=result["verificationUrl"],
                    user_code=result["userCode"],
                )
            elif event.get("method") == "account/login/completed":
                result = event["params"]
                if result.get("loginId") != login_id:
                    continue
                if not result.get("success"):
                    raise ValueError("Login was not completed")
                send("account/read", {"refreshToken": False}, 3)
            elif event.get("id") == 3:
                account = event["result"].get("account") or {}
                if account.get("type") != "chatgpt":
                    raise ValueError("Expected a ChatGPT account")
                emit(
                    "login.completed",
                    email=account.get("email"),
                    plan=account.get("planType"),
                )
                # Keep tmpfs available until the trusted worker copies the cache.
                process.wait(timeout=900)
                return
        raise ValueError("Login service stopped")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        emit("login.error")
        raise SystemExit(1)
