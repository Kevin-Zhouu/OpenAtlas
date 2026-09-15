"""Deterministic HTTP provider fixture exercising the real SDK stream/tool loop."""
import asyncio
import http.server
import json
import sys
import threading

sys.path.insert(0, '/opt')
import planner

CALLS = []
BRIEF = 'Build a token journey: manipulate input text to reveal token boundaries and watch the corresponding GPU work and streamed output. Research factual details before implementation.'

class Provider(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert body['model'] == 'fixture-model'
        assert body['stream'] is True
        CALLS.append(body)
        calls = [
            ('list_resources', {}),
            ('read_resource', {'path': 'local--fixture/SKILL.md', 'offset': 0}),
            ('read_resource', {'path': 'local--fixture/notes.md', 'offset': 0}),
            ('read_resource', {'path': '../../etc/passwd', 'offset': 0}),
            ('read_resource', {'path': 'references/goldens/CATALOG.json', 'offset': 0}),
            ('read_resource', {'path': 'references/goldens/chernobyl-atlas-1575d13d/principles.md', 'offset': 0}),
            ('read_resource', {'path': 'references/../../etc/passwd', 'offset': 0}),
        ]
        index = len(CALLS) - 1
        if index < len(calls):
            name, args = calls[index]
            output = [{'type': 'function_call', 'id': 'fc'+str(index), 'call_id': 'call'+str(index), 'name': name, 'arguments': json.dumps(args), 'status': 'completed'}]
        else:
            output = [{'type': 'message', 'id': 'msg1', 'role': 'assistant', 'status': 'completed', 'content': [{'type': 'output_text', 'text': BRIEF, 'annotations': []}]}]
        response = {'id': 'resp'+str(index), 'object': 'response', 'created_at': 1, 'model': 'fixture-model', 'status': 'completed', 'output': output, 'parallel_tool_calls': True, 'tool_choice': 'auto', 'tools': [], 'temperature': 1, 'top_p': 1, 'usage': {'input_tokens': 10, 'output_tokens': 10, 'total_tokens': 20, 'input_tokens_details': {'cached_tokens': 0, 'cache_write_tokens': 0}, 'output_tokens_details': {'reasoning_tokens': 0}}}
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        event = {'type': 'response.completed', 'sequence_number': index, 'response': response}
        self.wfile.write(('data: '+json.dumps(event)+'\n\n').encode())

server = http.server.ThreadingHTTPServer(('127.0.0.1', 9001), Provider)
threading.Thread(target=server.serve_forever, daemon=True).start()
real_client = planner.AsyncOpenAI
planner.AsyncOpenAI = lambda **kwargs: real_client(api_key=kwargs['api_key'], base_url='http://127.0.0.1:9001/v1')
sys.argv = ['planner', 'fixture-model', 'Read all skills and relevant resources; return a creative brief.', 'Explain LLM inference with 3D GPU work']
asyncio.run(planner.main())
assert len(CALLS) == 8
inputs = json.dumps(CALLS[-1]['input'])
assert 'fixture supporting notes' in inputs
assert 'Make visibility, cuts and disassembly reversible' in inputs
assert 'Resource outside selected skills' in inputs
assert 'root:x:' not in inputs
server.shutdown()
