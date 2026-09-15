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


@pytest.mark.parametrize("action", ["continue", "resume"])
def test_continue_seeds_checkpoint_and_publishes_after_validation(tmp_path, action):
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
    continued = c.post('/api/jobs/'+original['id']+('/resume' if action == 'resume' else '/retry'),
                       json={'stage':'building'} if action == 'resume' else {'mode':'continue'}).json()
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


def saved_resume_job(tmp_path, provider='codex'):
    repo = Repository(tmp_path/'data')
    store = ArtifactStore(repo.data)
    client = TestClient(create_app(repo, store=store), base_url='http://localhost')
    job = client.post('/api/jobs', json={'prompt': 'Explain caching', 'provider': provider,
                                      'skills_enabled': False}).json()
    repo.claim(2)
    work = tmp_path/'saved'; work.mkdir()
    generate(work, job['request'], lambda _: None)
    (work/'source'/'saved.txt').write_text('latest implementation')
    store.checkpoint(job['id'], work)
    repo.stage(job['id'], 'validating')
    repo.fail(job['id'], 'Stopped during validation')
    return repo, store, client, job, work


def test_resume_validation_skips_implementation_but_requires_review(tmp_path):
    repo, store, client, original, work = saved_resume_job(tmp_path)
    calls = []
    class ReviewOnly:
        def run(self, root, request, progress):
            calls.append(request.get('execution_stage'))
            assert request.get('execution_stage') == 'reviewing'
            assert (root/'source'/'saved.txt').read_text() == 'latest implementation'
            return {'verdict': 'pass', 'summary': 'Fixture independent review'}
    listed = client.get('/api/jobs').json()[0]
    assert listed['stopped_stage'] == 'validating'
    assert 'validating' in listed['resume_stages']
    result = client.post(f"/api/jobs/{original['id']}/resume", json={'stage': 'validating'})
    assert result.status_code == 202
    resumed = result.json()
    assert client.post(f"/api/jobs/{original['id']}/resume", json={'stage': 'validating'}).status_code == 409
    Runner(repo, store, executor=ReviewOnly(), planner=ReviewOnly()).process(repo.claim(2))
    assert repo.job(resumed['id'])['status'] == 'succeeded'
    assert calls == ['reviewing']
    assert repo.job(original['id'])['status'] == 'failed'
    assert not repo.rows("SELECT 1 FROM job_events WHERE job_id=:id AND stage='building'", id=resumed['id'])


def test_resume_validation_failure_never_starts_repairs(tmp_path):
    repo, store, client, original, work = saved_resume_job(tmp_path)
    html = work/'dist'/'index.html'
    html.write_text(html.read_text().replace('</body>', '<script>console.error("Broken fixture")</script></body>'))
    store.checkpoint(original['id'], work)
    class NoAgent:
        def run(self, *args):
            pytest.fail('Validation resume must not invoke implementation/repair')
    resumed = client.post(f"/api/jobs/{original['id']}/resume", json={'stage': 'validating'}).json()
    Runner(repo, store, executor=NoAgent(), planner=NoAgent()).process(repo.claim(2))
    failed = repo.job(resumed['id'])
    assert failed['status'] == 'failed'
    assert failed['stopped_stage'] == 'validating'
    assert 'Broken fixture' in failed['error']
    assert store.can_validate_checkpoint(resumed['id'])


def test_resume_publication_requires_unchanged_trusted_validation(tmp_path, monkeypatch):
    repo, store, client, original, work = saved_resume_job(tmp_path, 'demo')
    resumed = client.post(f"/api/jobs/{original['id']}/resume", json={'stage': 'validating'}).json()
    save = store.save
    def interrupted(*args):
        raise OSError('Disk interrupted')
    monkeypatch.setattr(store, 'save', interrupted)
    Runner(repo, store).process(repo.claim(2))
    assert repo.job(resumed['id'])['stopped_stage'] == 'publishing'
    assert store.publication_receipt(resumed['id'])
    monkeypatch.setattr(store, 'save', save)
    def no_validate(*args):
        pytest.fail('Publishing resume must reuse completed checks')
    monkeypatch.setattr('openatlas.runner.validate', no_validate)
    published = client.post(f"/api/jobs/{resumed['id']}/resume", json={}).json()
    assert published["request"]["resume_stage"] == "publishing"
    Runner(repo, store).process(repo.claim(2))
    assert repo.job(published['id'])['status'] == 'succeeded'
    path = store.checkpoint_path(resumed['id'])/'dist'/'index.html'
    path.write_text(path.read_text() + '<!-- changed -->')
    assert store.publication_receipt(resumed['id']) is None
    assert client.post(f"/api/jobs/{resumed['id']}/resume", json={'stage': 'publishing'}).status_code == 409


def test_resume_rejects_missing_artifact_and_active_jobs(tmp_path):
    repo, store, client, original, work = saved_resume_job(tmp_path)
    (store.checkpoint_path(original['id'])/'manifest.json').unlink()
    assert client.post(f"/api/jobs/{original['id']}/resume", json={'stage':'validating'}).status_code == 409
    assert client.post(f"/api/jobs/{original['id']}/resume", json={'stage':'publishing'}).status_code == 409
    resumed = client.post(f"/api/jobs/{original['id']}/resume", json={'stage':'building'})
    assert resumed.status_code == 202
    assert resumed.json()['request']['continue_job'] == original['id']
    assert client.post(f"/api/jobs/{resumed.json()['id']}/resume", json={'stage':'building'}).status_code == 409


def test_resume_planning_preserves_original_intent(tmp_path):
    repo = Repository(tmp_path/'data'); store = ArtifactStore(repo.data)
    client = TestClient(create_app(repo, store=store), base_url='http://localhost')
    original = client.post('/api/jobs', json={'prompt':'Explain caching','provider':'codex',
                                            'prompt_only':True,'skills_enabled':False}).json()
    repo.claim(2); repo.stage(original['id'], 'planning'); repo.fail(original['id'], 'Stopped')
    resumed = client.post(f"/api/jobs/{original['id']}/resume", json={'stage':'planning'})
    assert resumed.status_code == 202
    class Planner:
        def run(self, root, request, progress):
            assert request['execution_stage'] == 'planning'
            return 'Build an interactive explanation of caching with a visible cache hit and miss demonstration.'
    Runner(repo, store, planner=Planner()).process(repo.claim(2))
    assert repo.job(resumed.json()['id'])['status'] == 'succeeded'
    assert repo.job(resumed.json()['id'])['request']['build_prompt']


def test_stopped_stage_survives_cancel_and_expired_lease(tmp_path):
    from sqlalchemy import text
    repo = Repository(tmp_path)
    for action in ('cancel', 'expire'):
        job = repo.enqueue({'prompt':'Example','provider':'demo','skills':[]})
        repo.claim(2); repo.stage(job['id'], 'validating')
        if action == 'cancel':
            repo.cancel(job['id'])
        else:
            with repo.engine.begin() as connection:
                connection.execute(text('UPDATE jobs SET lease_until=0 WHERE id=:id'), {'id':job['id']})
            repo.claim(2)
        assert repo.job(job['id'])['stopped_stage'] == 'validating'


@pytest.mark.parametrize('stage', ['planning', 'building', 'validating', 'publishing'])
def test_single_resume_automatically_selects_stopped_stage(tmp_path, stage):
    repo, store, client, original, work = saved_resume_job(tmp_path)
    from sqlalchemy import text
    with repo.engine.begin() as connection:
        connection.execute(text('UPDATE jobs SET stopped_stage=:stage WHERE id=:id'),
                           {'stage':stage,'id':original['id']})
    # An old publishing failure has no trusted pass receipt; recheck its build.
    expected = 'validating' if stage == 'publishing' else stage
    result = client.post(f"/api/jobs/{original['id']}/resume", json={})
    assert result.status_code == 202
    assert result.json()['request']['resume_stage'] == expected
    assert client.get('/api/jobs').json()[1]['resume_stage'] == expected
