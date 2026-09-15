"""Opt-in real Docker boundary test; no inference or real API key is used."""

import os
import shutil
from uuid import uuid4

import pytest

from openatlas.artifacts import validate
from openatlas.debug import DebugStore
from openatlas.demo import generate
from openatlas.execution import DockerExecutor
from openatlas.references import stage_references
from openatlas.skills import SkillCatalog


@pytest.mark.skipif(os.getenv('OPENATLAS_DOCKER_TEST') != '1', reason='Requires built planner image')
def test_planner_stream_error_reports_actionable_cause(tmp_path):
    from pathlib import Path

    class Credential:
        def connection(self):
            return {'api_key': 'test-not-a-real-key', 'base_url': 'https://api.openai.com/v1'}

    class Adapter:
        def command(self, request):
            return ['/opt/planner/bin/python', '/workspace/error_test.py']

    (tmp_path / 'error_test.py').write_text(
        (Path(__file__).parent / 'fixtures/planner_error.py').read_text())
    request = {'job_id': str(uuid4()), 'execution_stage': 'planning', 'skills': []}
    with pytest.raises(ValueError, match='APIError: You have no credits remaining'):
        DockerExecutor(Credential(), adapter=Adapter()).run(tmp_path, request, lambda _: None)


@pytest.mark.skipif(
    os.getenv("OPENATLAS_DOCKER_TEST") != "1",
    reason="Set OPENATLAS_DOCKER_TEST=1 with the generation image built",
)
def test_disposable_docker_roundtrip(tmp_path):
    import docker

    class FakeCredential:
        def connection(self):
            return {"api_key": "test-credential-not-for-inference", "base_url": "https://api.openai.com/v1"}

    class FileEditingAgent:
        def command(self, request):
            return [
                "python3",
                "-c",
                "import os, pathlib, subprocess; assert os.getuid()!=0; assert pathlib.Path('/sys/fs/cgroup/pids.max').read_text().strip() == '512'; pathlib.Path('/workspace/source/deleted.txt').unlink(); pathlib.Path('/workspace/dist/deleted.txt').unlink(); assert pathlib.Path('/workspace/references/goldens/CATALOG.json').is_file(); assert pathlib.Path('/workspace/references/goldens/chernobyl-atlas-1575d13d/contact-sheet.jpg').is_file(); assert 'OPENAI_API_KEY' not in os.environ; assert not pathlib.Path('/var/run/docker.sock').exists(); p=pathlib.Path('/workspace/source/index.html'); p.write_text(p.read_text().replace('Remember the work.','Remember the previous work.')); subprocess.run(['python3','source/build.py'],check=True)",
            ]

    request = {
        "prompt": "Container roundtrip",
        "job_id": str(uuid4()),
        "skills": SkillCatalog().resolve(["builtin:visual-explainer"]),
    }
    stage_references(tmp_path)
    generate(tmp_path, request, lambda _: None)
    shutil.rmtree(tmp_path / "dist")
    (tmp_path / "dist").mkdir()
    (tmp_path / "source/deleted.txt").write_text("obsolete source")
    (tmp_path / "dist/deleted.txt").write_text("obsolete build")
    SkillCatalog().stage(request["skills"], tmp_path / "skills")
    debug = DebugStore(tmp_path / "diagnostics")
    DockerExecutor(FakeCredential(), adapter=FileEditingAgent(), debug=debug).run(
        tmp_path, request, lambda _: None
    )
    assert "Remember the previous work." in (tmp_path / "source/index.html").read_text()
    assert "Remember the previous work." in (tmp_path / "dist/index.html").read_text()
    assert not (tmp_path / "source/deleted.txt").exists()
    assert not (tmp_path / "dist/deleted.txt").exists()
    assert validate(tmp_path)["title"]
    client = docker.from_env()
    assert (
        client.containers.list(all=True, filters={"label": "openatlas.job=docker-test"})
        == []
    )
    client.close()

    snapshots = debug.read(request["job_id"])["containers"]
    assert len(snapshots) == 2
    assert {s["role"] for s in snapshots} == {"agent", "relay"}
    assert all(s["status"] == "removed" for s in snapshots)

@pytest.mark.skipif(os.getenv('OPENATLAS_DOCKER_TEST') != '1', reason='Requires built planner image')
def test_real_agents_sdk_planner_stream_and_isolation(tmp_path):
    from pathlib import Path
    from openatlas.planning import PlannerAdapter
    stage_references(tmp_path)
    class Credential:
        def connection(self): return {'api_key': 'test-not-a-real-key', 'base_url': 'https://api.openai.com/v1'}
    class FixtureAdapter(PlannerAdapter):
        def command(self, request):
            return ['/opt/planner/bin/python', '/workspace/sdk_test.py']
    (tmp_path/'sdk_test.py').write_text((Path(__file__).parent/'fixtures/planner_provider.py').read_text())
    skill = tmp_path/'skills/local--fixture'
    skill.mkdir(parents=True)
    (skill/'SKILL.md').write_text('Read notes.md to plan token explanations.')
    (skill/'notes.md').write_text('fixture supporting notes')
    request = {'job_id': str(uuid4()), 'execution_stage': 'planning', 'planner_model': 'fixture-model', 'skills': []}
    debug = DebugStore(tmp_path/'debug')
    result = DockerExecutor(Credential(), adapter=FixtureAdapter(), debug=debug).run(tmp_path, request, lambda _: None)
    assert 'token boundaries' in result
    assert 'references/goldens/chernobyl-atlas-1575d13d/principles.md — offset 0' in result
    snapshots = debug.read(request['job_id'])['containers']
    assert len(snapshots) == 2 and all(c['status'] == 'removed' for c in snapshots)
    agent = next(c for c in snapshots if c['role'] == 'agent')
    assert agent['stage'] == 'planning'
    assert 'planner.resource_read' in agent['agent_log'] and 'notes.md' in agent['agent_log']
    assert 'test-not-a-real-key' not in str(snapshots)

@pytest.mark.skipif(os.getenv('OPENATLAS_DOCKER_TEST') != '1', reason='Requires built planner image')
@pytest.mark.parametrize('cancel', [False, True])
def test_planner_failure_and_cancellation_remove_containers(tmp_path, cancel):
    import docker
    class Credential:
        def connection(self): return {'api_key': 'test-not-a-real-key', 'base_url': 'https://api.openai.com/v1'}
    class Adapter:
        def command(self, request):
            return ['python3', '-c', 'import time; time.sleep(30)' if cancel else 'raise SystemExit(1)']
    debug = DebugStore(tmp_path/'debug')
    request = {'job_id': str(uuid4()), 'execution_stage': 'planning', 'skills': []}
    calls = []
    def cancelled(request):
        calls.append(True)
        return cancel and len(calls) > 2
    with pytest.raises(ValueError, match='cancelled|Planner exited'):
        DockerExecutor(Credential(), adapter=Adapter(), debug=debug, cancelled=cancelled).run(tmp_path, request, lambda _: None)
    client = docker.from_env()
    try:
        assert not client.containers.list(all=True, filters={'label': 'openatlas.job='+request['job_id']})
    finally:
        client.close()
    assert all(c['status'] == 'removed' for c in debug.read(request['job_id'])['containers'])
