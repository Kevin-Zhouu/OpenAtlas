"""Local Responses fixture for real CLI/SDK requests through the production relay."""

import http.server
import json

RECEIVED = []
BRIEF = "Build a flagellar motor lesson with an interactive rotor and stator diagram. Explain how ion flow drives rotation, with a speed control and readable labels."


class Provider(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps(RECEIVED).encode())

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        RECEIVED.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "model": body["model"],
                "stream": body.get("stream"),
            }
        )
        if self.path not in ("/provider-a/v2/responses", "/provider-b/v1/responses"):
            self.send_error(404)
            return
        message = {
            "id": "msg_fixture",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": BRIEF, "annotations": []}],
        }
        response = {
            "id": "resp_fixture",
            "object": "response",
            "created_at": 1,
            "model": body["model"],
            "status": "completed",
            "output": [message],
            "parallel_tool_calls": True,
            "tool_choice": "auto",
            "tools": [],
            "temperature": 1,
            "top_p": 1,
            "usage": {
                "input_tokens": 10,
                "output_tokens": 10,
                "total_tokens": 20,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            },
        }
        events = [
            {
                "type": "response.created",
                "response": dict(response, status="in_progress", output=[]),
            },
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": dict(message, status="in_progress", content=[]),
            },
            {
                "type": "response.content_part.added",
                "item_id": message["id"],
                "output_index": 0,
                "content_index": 0,
                "part": {"type": "output_text", "text": "", "annotations": []},
            },
            {
                "type": "response.output_text.delta",
                "item_id": message["id"],
                "output_index": 0,
                "content_index": 0,
                "delta": BRIEF,
            },
            {
                "type": "response.output_text.done",
                "item_id": message["id"],
                "output_index": 0,
                "content_index": 0,
                "text": BRIEF,
            },
            {
                "type": "response.content_part.done",
                "item_id": message["id"],
                "output_index": 0,
                "content_index": 0,
                "part": message["content"][0],
            },
            {"type": "response.output_item.done", "output_index": 0, "item": message},
            {"type": "response.completed", "response": response},
        ]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for index, event in enumerate(events):
            event["sequence_number"] = index
            self.wfile.write(
                (
                    "event: " + event["type"] + "\ndata: " + json.dumps(event) + "\n\n"
                ).encode()
            )
            self.wfile.flush()


http.server.ThreadingHTTPServer(("0.0.0.0", 9010), Provider).serve_forever()
