from generation.broker import ModelObserver, report_model
from openatlas.agents import CodexAdapter


def test_model_passed_explicitly(monkeypatch):
    adapter = CodexAdapter()
    monkeypatch.setattr(adapter, 'prompt', lambda request: 'test')
    command = adapter.command({'model': 'gpt-6-astra'})
    assert command[command.index('-m') + 1] == 'gpt-6-astra'


def test_model_stream_split_and_no_content_leak(capsys):
    observer = ModelObserver()
    observer.feed(b'data: {"response":{"mod')
    observer.feed(b'el":"gpt-6-astra","output":"private text"}}\n\n')
    observer.feed(b'data: {"response":{"model":"gpt-6-astra"}}\n\n')
    output = capsys.readouterr().out
    assert output.count('response_model') == 1
    assert 'gpt-6-astra' in output
    assert 'private text' not in output


def test_observer_bounds_and_rejects_unsafe_identifiers(capsys):
    observer = ModelObserver()
    observer.feed(b'data: ' + b'x' * 70000)
    assert len(observer.buffer) == 0
    observer.feed(b'\ndata: {"response":{"model":"gpt-6-astra"}}\n')
    report_model('response_model', 'bad\nsecret')
    assert 'bad' not in capsys.readouterr().out


def test_installed_codex_astra_catalog_and_request():
    """Opt-in: real CLI against a local rejecting endpoint; no model inference."""
    import os
    import pytest
    if os.getenv('OPENATLAS_DOCKER_TEST') != '1':
        pytest.skip('Enable Docker tests with the built generation image')
    import docker
    import json
    adapter = CodexAdapter()
    adapter.prompt = lambda request: 'Reply OK. Do not use tools.'
    command = adapter.command({'model':'gpt-6-astra'})
    script = '''
import http.server, json, os, subprocess, threading
models=[]
os.makedirs('/tmp/.codex', exist_ok=True)
class Endpoint(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        models.append(json.loads(self.rfile.read(int(self.headers['Content-Length'])))['model'])
        self.send_response(401); self.send_header('Content-Type','application/json'); self.end_headers()
        self.wfile.write(b'{"error":{"message":"Intentional local test rejection","type":"authentication_error"}}')
server=http.server.ThreadingHTTPServer(('127.0.0.1',9000),Endpoint)
threading.Thread(target=server.serve_forever,daemon=True).start()
result=subprocess.run(COMMAND,capture_output=True,text=True,timeout=45)
assert models and all(model=='gpt-6-astra' for model in models), (models, result.stdout, result.stderr)
assert 'Model metadata for' not in result.stdout+result.stderr
assert result.returncode != 0
print('PASS: real CLI sends gpt-6-astra, recognizes metadata, and surfaces endpoint failures without model fallback')
'''.replace('COMMAND', repr(command))
    client = docker.from_env()
    try:
        output = client.containers.run('openatlas-generation:local', ['python3','-c',script],
            remove=True, network_mode='none', read_only=True,
            tmpfs={'/tmp':'rw,nosuid,size=128m,uid=1000,gid=1000', '/workspace':'rw,nosuid,size=32m,uid=1000,gid=1000'},
            environment={'HOME':'/tmp', 'CODEX_HOME':'/tmp/.codex', 'CODEX_API_KEY':'test-only'})
        assert b'PASS:' in output
    finally:
        client.close()
