"""Actual SDK loop with a deterministic Codex subprocess; no account required."""
import json
import os
import pathlib
import sys
import asyncio

sys.path.insert(0, '/opt')
import planner

bin_dir = pathlib.Path('/tmp/fixture-bin')
bin_dir.mkdir()
script = bin_dir / 'codex'
script.write_text('''#!/opt/planner/bin/python
import json, os, pathlib, sys, traceback
sys.excepthook = lambda kind, error, tb: print(json.dumps({"type": "error", "message": "Fixture failure at line " + str(traceback.extract_tb(tb)[-1].lineno) + ": " + str(error)}))
assert "CODEX_API_KEY" not in os.environ and "OPENAI_API_KEY" not in os.environ
assert 'forced_login_method="chatgpt"' in sys.argv
assert 'model_provider="openai"' in sys.argv
assert 'features.shell_tool=false' in sys.argv
assert '--sandbox' in sys.argv and 'read-only' in sys.argv
payload = json.loads(sys.stdin.read().split("\\n", 1)[1])
assert payload["instructions"]
assert {t["name"] for t in payload["tools"]} == {"list_resources", "read_resource"}
count_path = pathlib.Path("/tmp/codex-fixture-count")
count = int(count_path.read_text()) if count_path.exists() else 0
count_path.write_text(str(count + 1))
actions = [("list_resources", {}), ("read_resource", {"path": "fixture/SKILL.md"}),
           ("read_resource", {"path": "references/goldens/CATALOG.json"})]
if count < len(actions):
    name, args = actions[count]
    result = {"text": "", "tool_calls": [{"name": name, "arguments": json.dumps(args)}]}
else:
    assert "fixture teaching instruction" in json.dumps(payload["conversation"])
    result = {"text": "Build a flagellar motor lesson explaining ion flow with an interactive rotor, stator and direction control.", "tool_calls": []}
if count == 1:
    # A valid model turn may include progress text and a batch of more than 8 reads.
    result["text"] = "I am reviewing the resources before writing the brief."
    result["tool_calls"] *= 12
pathlib.Path(sys.argv[sys.argv.index("--output-last-message")+1]).write_text(json.dumps(result))
auth = pathlib.Path(os.environ["CODEX_HOME"]) / "auth.json"
cache = json.loads(auth.read_text())
cache["tokens"]["access_token"] = "refreshed-fixture-access"
auth.write_text(json.dumps(cache))
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 10}}))
''')
script.chmod(0o700)
os.environ['PATH'] = str(bin_dir) + ':' + os.environ['PATH']
sys.argv = ['planner', 'gpt-6-astra', 'Read the skill and catalog before planning.', 'Explain a flagellar motor']
real_create = asyncio.create_subprocess_exec
async def capture_process(*args, **kwargs):
    kwargs['stderr'] = open('/tmp/fixture-stderr.log', 'wb')
    assert args[0] == 'codex'
    return await real_create('/opt/planner/bin/python', str(script), *args[1:], **kwargs)
asyncio.create_subprocess_exec = capture_process
try:
    asyncio.run(planner.main())
except Exception:
    print(json.dumps({'type': 'error', 'message': pathlib.Path('/tmp/fixture-stderr.log').read_text()}))
    raise
assert pathlib.Path('/tmp/codex-fixture-count').read_text() == '4'
