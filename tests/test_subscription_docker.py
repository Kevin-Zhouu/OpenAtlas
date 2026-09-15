import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from openatlas.credentials import Credentials
from openatlas.debug import DebugStore
from openatlas.execution import DockerExecutor
from openatlas.subscription import SubscriptionStore

pytestmark = pytest.mark.skipif(
    os.getenv("OPENATLAS_DOCKER_TEST") != "1", reason="Requires generation image"
)


def test_subscription_sdk_tools_refresh_and_isolation(tmp_path):
    credentials = Credentials(tmp_path / "data")
    credentials.save("must-not-be-used-api-key")
    subscription = SubscriptionStore(tmp_path / "data")
    subscription.start()
    epoch = subscription._read()["epoch"]
    subscription.update(
        epoch,
        status="signed_in",
        auth={
            "auth_mode": "chatgpt",
            "tokens": {
                "access_token": "initial-fixture-access",
                "refresh_token": "fixture-refresh",
                "id_token": "fixture-id",
            },
        },
    )
    workspace = tmp_path / "workspace"
    (workspace / "skills/fixture").mkdir(parents=True)
    (workspace / "skills/fixture/SKILL.md").write_text("fixture teaching instruction")
    (workspace / "references/goldens").mkdir(parents=True)
    (workspace / "references/goldens/CATALOG.json").write_text('{"references": []}')
    (workspace / "fixture.py").write_text(
        (Path(__file__).parent / "fixtures/subscription_planner.py").read_text()
    )

    class Adapter:
        def command(self, request):
            assert request["inference_auth"] == "chatgpt"
            return ["/opt/planner/bin/python", "/workspace/fixture.py"]

    debug = DebugStore(tmp_path / "data")
    job = {"job_id": str(uuid4()), "execution_stage": "planning", "skills": []}
    result = DockerExecutor(credentials, adapter=Adapter(), debug=debug).run(
        workspace, job, lambda _: None, connection=subscription.session()
    )
    assert "flagellar motor" in result and "Resource access record" in result
    assert (
        subscription.session()["auth"]["tokens"]["access_token"]
        == "refreshed-fixture-access"
    )
    snapshot = debug.read(job["job_id"])
    assert len(snapshot["containers"]) == 1  # no API-key relay in subscription mode
    assert snapshot["containers"][0]["status"] == "removed"
    assert "planner.started" in snapshot["containers"][0]["agent_log"]
    retained = debug.trace(job["job_id"], snapshot["containers"][0]["id"])
    assert retained["retention"] == "complete"
    assert "planner.codex_event" in retained["agent_log"]
    text = json.dumps(snapshot)
    for secret in (
        "initial-fixture-access",
        "refreshed-fixture-access",
        "fixture-refresh",
        "must-not-be-used-api-key",
    ):
        assert secret not in text


def test_installed_cli_uses_subscription_auth_without_api_key():
    import docker

    from openatlas.agents import CodexAdapter

    adapter = CodexAdapter()
    adapter.prompt = lambda request: "Reply with a short greeting. Do not use tools."
    command = adapter.command({"model": "gpt-6-astra", "inference_auth": "chatgpt"})
    script = """
import base64, datetime, http.server, json, os, pathlib, subprocess, threading
root=pathlib.Path('/tmp/home/.codex'); root.mkdir(parents=True)
def jwt(payload):
    encode=lambda data: base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip('=')
    return encode({'alg':'none'})+'.'+encode(payload)+'.fixture-signature'
claims={'email':'fixture@example.com','https://api.openai.com/auth':{'chatgpt_account_id':'fixture-account','chatgpt_plan_type':'pro'}}
access=jwt(claims)
(root/'auth.json').write_text(json.dumps({'auth_mode':'chatgpt','OPENAI_API_KEY':None,'tokens':{'id_token':access,'access_token':access,'refresh_token':'fixture-refresh','account_id':'fixture-account'},'last_refresh':datetime.datetime.now(datetime.timezone.utc).isoformat()}))
received=[]
class Endpoint(http.server.BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        self.send_response(200); self.send_header('Content-Type','application/json'); self.end_headers(); self.wfile.write(b'{"models":[]}')
    def do_POST(self):
        size=int(self.headers.get('Content-Length','0'))
        body=self.rfile.read(size)
        if self.path.endswith('/responses'): received.append((self.path,self.headers.get('Authorization'),self.headers.get('ChatGPT-Account-Id')))
        self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.end_headers()
        item={'id':'msg_test','type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':'Hello from the subscription fixture.','annotations':[]}]}
        response={'id':'resp_test','object':'response','created_at':1,'model':'gpt-6-astra','status':'completed','output':[item],'usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2,'input_tokens_details':{'cached_tokens':0},'output_tokens_details':{'reasoning_tokens':0}}}
        for i,event in enumerate([{'type':'response.created','response':dict(response,status='in_progress',output=[])},{'type':'response.output_item.done','output_index':0,'item':item},{'type':'response.completed','response':response}]):
            event['sequence_number']=i
            self.wfile.write(('event: '+event['type']+'\\ndata: '+json.dumps(event)+'\\n\\n').encode()); self.wfile.flush()
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Endpoint)
threading.Thread(target=server.serve_forever,daemon=True).start()
(root/'config.toml').write_text('chatgpt_base_url="http://127.0.0.1:'+str(server.server_port)+'"\\n')
assert 'CODEX_API_KEY' not in os.environ and 'OPENAI_API_KEY' not in os.environ
try:
    command=COMMAND
    command[command.index('model_provider="openai"')]='model_provider="fixture"'
    command=command[:-1]+['-c','model_providers.fixture={name="Subscription fixture",base_url="http://127.0.0.1:'+str(server.server_port)+'",wire_api="responses",requires_openai_auth=true}', '-c', 'features.remote_plugin=false', '-c', 'features.plugins=false', '-c', 'analytics.enabled=false']+command[-1:]
    result=subprocess.run(command,capture_output=True,text=True,timeout=30)
except subprocess.TimeoutExpired as error:
    raise AssertionError(str([(x[0], bool(x[1]), x[2]) for x in received])+str(error.stdout)+str(error.stderr)) from None
assert received, result.stdout+result.stderr
assert all(row[1]=='Bearer '+access and row[2]=='fixture-account' for row in received)
assert result.returncode==0, result.stdout+result.stderr
assert 'Hello from the subscription fixture' in result.stdout, result.stdout
print('PASS: installed CLI uses ChatGPT auth and consumes a successful local stream')
""".replace("COMMAND", repr(command))
    client = docker.from_env()
    try:
        output = client.containers.run(
            "openatlas-generation:local",
            ["python3", "-c", script],
            remove=True,
            network_mode="none",
            read_only=True,
            tmpfs={
                "/tmp": "rw,nosuid,size=128m,uid=1000,gid=1000",
                "/workspace": "rw,nosuid,size=32m,uid=1000,gid=1000",
            },
            environment={"HOME": "/tmp/home", "CODEX_HOME": "/tmp/home/.codex"},
        )
        assert b"PASS:" in output
    finally:
        client.close()
