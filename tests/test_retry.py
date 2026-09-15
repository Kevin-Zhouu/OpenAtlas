import pytest
from fastapi.testclient import TestClient
from openatlas.api import create_app
from openatlas.artifacts import ArtifactStore
from openatlas.repository import Repository
from openatlas.runner import Runner
from openatlas.demo import generate


def test_retry_preserves_request_and_prevents_duplicate_attempts(tmp_path):
    repo = Repository(tmp_path)
    store = ArtifactStore(tmp_path)
    c = TestClient(create_app(repo, store=store), base_url='http://localhost')
    original = c.post('/api/jobs', json={'prompt':'Explain memory','skills_enabled':False,'reading_minutes':35}).json()
    assert c.post('/api/jobs/'+original['id']+'/retry', json={'mode':'rerun'}).status_code == 409
    repo.claim(2)
    repo.fail(original['id'], 'No credits')
    assert c.post('/api/jobs/'+original['id']+'/retry', json={'mode':'continue'}).status_code == 409
    rerun = c.post('/api/jobs/'+original['id']+'/retry', json={'mode':'rerun'})
    assert rerun.status_code == 202
    job = rerun.json()
    assert job['id'] != original['id'] and job['notebook_id'] == original['notebook_id']
    assert job['request'] == dict(original['request'], retry_of=original['id'])
    assert c.post('/api/jobs/'+original['id']+'/retry', json={'mode':'rerun'}).status_code == 409
    assert repo.job(original['id'])['status'] == 'failed'
    Runner(repo, store).process(repo.claim(2))
    assert repo.job(job['id'])['status'] == 'succeeded'
    assert len(repo.library()) == 1


def test_continue_seeds_checkpoint_and_publishes_after_validation(tmp_path):
    repo = Repository(tmp_path/'data'); store = ArtifactStore(repo.data)
    c = TestClient(create_app(repo, store=store), base_url='http://localhost')
    original = c.post('/api/jobs', json={'prompt':'Explain caching','provider':'codex','skills_enabled':False}).json()
    workspace = tmp_path/'partial'; workspace.mkdir()
    generate(workspace, original['request'], lambda _: None)
    (workspace/'source'/'unfinished.txt').write_text('existing work')
    assert store.checkpoint(original['id'], workspace)
    repo.claim(2)
    attempt = repo.start_plan(original['id'], original['request'])
    repo.finish_plan(original['id'], attempt, 'Build a caching lesson showing cache hits and misses with an explorable request stream.')
    repo.fail(original['id'], 'No credits')
    assert c.get('/api/jobs').json()[0]['can_continue']
    continued = c.post('/api/jobs/'+original['id']+'/retry', json={'mode':'continue'}).json()
    class Agent:
        def run(self, root, request, progress):
            assert (root/'source'/'unfinished.txt').read_text() == 'existing work'
            assert request['continue_job'] == original['id']
            assert request['model'] == original['request']['model']
            if request.get('execution_stage') == 'reviewing':
                return {'verdict':'pass','summary':'Fixture review of continued work'}
    Runner(repo, store, executor=Agent()).process(repo.claim(2))
    assert repo.job(continued['id'])['status'] == 'succeeded'
    assert Repository(repo.data).job(original['id'])['status'] == 'failed'
    assert ArtifactStore(repo.data).checkpoint_path(original['id'])


def test_checkpoint_rejects_links(tmp_path):
    store = ArtifactStore(tmp_path/'data')
    work = tmp_path/'partial'; (work/'source').mkdir(parents=True)
    (work/'source'/'secret').symlink_to('/etc/passwd')
    from uuid import uuid4
    with pytest.raises(ValueError): store.checkpoint(str(uuid4()), work)


def test_failed_docker_generation_retains_partial_source(tmp_path):
    import os
    if os.getenv('OPENATLAS_DOCKER_TEST') != '1': pytest.skip('Opt-in Docker test')
    from uuid import uuid4
    from openatlas.execution import DockerExecutor
    class Credential:
        def connection(self): return {'api_key': 'test-no-inference', 'base_url': 'https://api.openai.com/v1'}
    class FailingAgent:
        def command(self, request):
            return ['sh','-c','mkdir -p source/node_modules; echo partial > source/lesson.txt; echo ignored > source/node_modules/dependency; exit 1']
    store = ArtifactStore(tmp_path/'data')
    workspace = tmp_path/'workspace'; (workspace/'source').mkdir(parents=True); (workspace/'dist').mkdir()
    job_id = str(uuid4())
    with pytest.raises(ValueError, match='Codex exited'):
        DockerExecutor(Credential(), adapter=FailingAgent(), checkpoint_store=store).run(workspace, {'job_id':job_id}, lambda _:None)
    checkpoint = store.checkpoint_path(job_id)
    assert (checkpoint/'source/lesson.txt').read_text().strip() == 'partial'
    assert not (checkpoint/'source/node_modules').exists()
    assert not (checkpoint/'manifest.json').exists()
