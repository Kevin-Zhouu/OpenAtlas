import http.server
import json
import threading
from contextlib import contextmanager
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from generation.broker import Relay


@contextmanager
def server(handler):
    instance = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=instance.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{instance.server_port}"
    finally:
        instance.shutdown()
        instance.server_close()
        worker.join()


def test_relay_routes_custom_base_paths_auth_and_errors(monkeypatch):
    received = []

    class Provider(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            received.append(
                (
                    self.path,
                    self.headers["Authorization"],
                    json.loads(self.rfile.read(int(self.headers["Content-Length"]))),
                )
            )
            self.send_response(429 if self.path.endswith("/compact") else 200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Retry-After", "7")
            self.send_header("x-request-id", "fixture-request")
            self.end_headers()
            self.wfile.write(
                b'{"error":{"message":"fixture quota"}}'
                if self.path.endswith("/compact")
                else b'{"ok":true}'
            )

    with server(Provider) as provider, server(Relay) as relay:
        monkeypatch.setenv("INFERENCE_BASE_URL", provider + "/gateway/v2/")
        monkeypatch.setenv("OPENAI_API_KEY", "custom-provider-token")
        monkeypatch.setenv("RELAY_TOKEN", "job-token")

        def call(path, token="job-token"):
            return urlopen(
                Request(
                    relay + path,
                    data=b'{"model":"vendor/model:latest"}',
                    headers={"Authorization": "Bearer " + token},
                ),
                timeout=5,
            )

        with call("/v1/responses") as response:
            assert json.load(response) == {"ok": True}
            assert response.headers["x-request-id"] == "fixture-request"
        with pytest.raises(HTTPError) as error:
            call("/v1/responses/compact")
        assert error.value.code == 429
        assert error.value.headers["Retry-After"] == "7"
        assert b"fixture quota" in error.value.read()
        assert received == [
            (
                "/gateway/v2/responses",
                "Bearer custom-provider-token",
                {"model": "vendor/model:latest"},
            ),
            (
                "/gateway/v2/responses/compact",
                "Bearer custom-provider-token",
                {"model": "vendor/model:latest"},
            ),
        ]
        for path, token in [
            ("/v1/responses", "wrong-token"),
            ("/v1/models", "job-token"),
            ("/v1/responses?url=elsewhere", "job-token"),
        ]:
            with pytest.raises(HTTPError) as denied:
                call(path, token)
            assert denied.value.code == 403
        assert len(received) == 2


def test_relay_does_not_follow_provider_redirects(monkeypatch):
    received = []

    class Target(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            received.append(self.headers.get("Authorization"))

        def do_POST(self):
            received.append(self.headers.get("Authorization"))

    with server(Target) as target:

        class Redirect(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(302)
                self.send_header("Location", target + "/collect")
                self.end_headers()

        with server(Redirect) as provider, server(Relay) as relay:
            monkeypatch.setenv("INFERENCE_BASE_URL", provider)
            monkeypatch.setenv("OPENAI_API_KEY", "private-provider-key")
            monkeypatch.setenv("RELAY_TOKEN", "job-token")
            with pytest.raises(HTTPError) as error:
                urlopen(
                    Request(
                        relay + "/v1/responses",
                        data=b'{"model":"test"}',
                        headers={"Authorization": "Bearer job-token"},
                    ),
                    timeout=5,
                )
            assert error.value.code == 302
            assert error.value.headers.get("Location") is None
            assert received == []
