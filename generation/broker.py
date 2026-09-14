"""Trusted, job-scoped provider relay. Runs in a separate container without mounts."""

import http.server
import os
import urllib.error
import urllib.request


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
        request = urllib.request.Request(
            "https://api.openai.com" + self.path,
            data=self.rfile.read(size),
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
            while True:
                chunk = response.read1(8192)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        self.close_connection = True


http.server.ThreadingHTTPServer(("0.0.0.0", 9000), Relay).serve_forever()
