"""Trusted, job-scoped provider relay. Runs in a separate container without mounts."""

import http.server
import os
import json
import re
import urllib.error
import urllib.request


def report_model(label, value):
    # Whitelist a model identifier only; never log response text or credentials.
    if isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9._-]{1,120}", value):
        print(json.dumps({"type": "model_verification", label: value}), flush=True)


class ModelObserver:
    def __init__(self):
        self.buffer = b""
        self.discarding = False
        self.reported = False

    def feed(self, chunk):
        if self.reported:
            return
        for part in chunk.splitlines(keepends=True):
            if not self.discarding:
                self.buffer += part
            if len(self.buffer) > 65536:
                self.buffer = b""
                self.discarding = True
            if part.endswith(b"\n"):
                if not self.discarding and self.buffer.startswith(b"data: "):
                    try:
                        event = json.loads(self.buffer[6:])
                        model = (event.get("response") or {}).get("model")
                        if model:
                            report_model("response_model", model)
                            self.reported = True
                    except (ValueError, TypeError, AttributeError):
                        pass
                self.buffer = b""
                self.discarding = False


class Relay(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        if (
            self.path not in ("/v1/responses", "/v1/responses/compact")
            or self.headers.get("Authorization")
            != "Bearer " + os.environ["RELAY_TOKEN"]
        ):
            self.send_error(403)
            return
        size = int(self.headers.get("Content-Length", "0"))
        if not 0 < size <= 20 * 1024 * 1024:
            self.send_error(413)
            return
        body = self.rfile.read(size)
        try:
            report_model("requested_model", json.loads(body).get("model"))
        except (ValueError, AttributeError):
            self.send_error(400, "Invalid request JSON")
            return
        request = urllib.request.Request(
            "https://api.openai.com" + self.path,
            data=body,
            headers={
                "Authorization": "Bearer " + os.environ["OPENAI_API_KEY"],
                "Content-Type": "application/json",
                "Accept": self.headers.get("Accept", "application/json"),
            },
            method="POST",
        )
        try:
            response = urllib.request.urlopen(request, timeout=300)
        except urllib.error.HTTPError as e:
            response = e
        except Exception:
            self.send_error(502, "Provider connection failed")
            return
        with response:
            self.send_response(response.status)
            self.send_header(
                "Content-Type", response.headers.get("Content-Type", "application/json")
            )
            self.send_header("Connection", "close")
            self.end_headers()
            observer = ModelObserver()
            while True:
                chunk = response.read1(8192)
                if not chunk:
                    break
                observer.feed(chunk)
                self.wfile.write(chunk)
                self.wfile.flush()
        self.close_connection = True


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("0.0.0.0", 9000), Relay).serve_forever()
