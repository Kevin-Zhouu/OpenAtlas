"""Exercise the planner's CLI handler with a real SDK streaming API error."""
import http.server
import json
import runpy
import sys
import threading

import openai


class Provider(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers['Content-Length']))
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        event = {'error': {'type': 'insufficient_quota', 'code': 'insufficient_quota',
                          'message': 'You have no credits remaining. Add credits to continue.'}}
        self.wfile.write(('data: ' + json.dumps(event) + '\n\n').encode())


server = http.server.ThreadingHTTPServer(('127.0.0.1', 9001), Provider)
threading.Thread(target=server.serve_forever, daemon=True).start()
original = openai.AsyncOpenAI
openai.AsyncOpenAI = lambda **kwargs: original(
    **dict(kwargs, base_url='http://127.0.0.1:9001/v1'))
sys.argv = ['/opt/planner.py', 'fixture-model', 'Plan a notebook.', 'Flagellar motor']
runpy.run_path('/opt/planner.py', run_name='__main__')
