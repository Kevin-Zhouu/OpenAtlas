import pytest
from fastapi.testclient import TestClient
from openatlas.api import create_app
from openatlas.repository import Repository
from scripts.remote_access import configuration, hostname


def test_remote_https_origin_login_and_csrf(tmp_path, monkeypatch):
    host = 'atlas.example.ts.net'
    monkeypatch.setenv('OPENATLAS_PUBLIC_ORIGIN', 'https://' + host)
    monkeypatch.setenv('OPENATLAS_ALLOWED_HOSTS', 'localhost,' + host)
    monkeypatch.setenv('OPENATLAS_ACCESS_TOKEN', 'test-host-token')
    app = create_app(Repository(tmp_path))
    # HTTP transport behind Serve, with the original Host and HTTPS Origin.
    c = TestClient(app, base_url='http://' + host)
    assert c.get('/api/notebooks').status_code == 401
    login = c.post('/api/session', json={'token': 'test-host-token'}, headers={'Origin': 'https://' + host})
    assert login.status_code == 200
    assert 'Secure' in login.headers['set-cookie']
    assert 'HttpOnly' in login.headers['set-cookie']
    auth = {'Cookie': 'openatlas_session=test-host-token', 'Origin': 'https://' + host}
    assert c.post('/api/jobs', json={'prompt': 'Teach memory'}, headers=auth).status_code == 202
    auth['Origin'] = 'https://attacker.example'
    assert c.post('/api/jobs', json={'prompt': 'Teach memory'}, headers=auth).status_code == 403
    asset = c.get('/artifacts/book/version/index.html')
    assert 'https://' + host + '/artifacts/book/version/' in asset.headers['content-security-policy']
    assert c.get('/', headers={'Host': 'attacker.example'}).status_code == 400
    local = TestClient(app, base_url='http://localhost')
    assert local.post('/api/session', json={'token':'test-host-token'}, headers={'Origin':'http://localhost'}).status_code == 200
    assert local.post('/api/jobs', json={'prompt':'Teach trees'}, headers={'Origin':'https://attacker.example','X-Forwarded-Host':'attacker.example','X-Forwarded-Proto':'https'}).status_code == 403


def test_remote_setup_validation():
    assert hostname({'BackendState':'Running','Self':{'DNSName':'atlas.example.ts.net.'}}) == 'atlas.example.ts.net'
    with pytest.raises(ValueError):
        hostname({'BackendState':'NeedsLogin'})
    with pytest.raises(ValueError):
        hostname({'BackendState':'Running','Self':{'DNSName':'attacker.example'}})
    env = configuration('atlas.example.ts.net','secret')['services']['app']['environment']
    assert env['OPENATLAS_PUBLIC_ORIGIN'] == 'https://atlas.example.ts.net'
    assert '*' not in env['OPENATLAS_ALLOWED_HOSTS']


def test_remote_requires_auth(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENATLAS_PUBLIC_ORIGIN','https://atlas.example.ts.net')
    monkeypatch.delenv('OPENATLAS_ACCESS_TOKEN', raising=False)
    with pytest.raises(ValueError):
        create_app(Repository(tmp_path))


def test_setup_refuses_existing_service(monkeypatch, tmp_path):
    from scripts import remote_access as setup
    monkeypatch.setattr(setup, 'OWNED', tmp_path / 'owned.json')
    monkeypatch.setattr(setup, 'tailscale', lambda: 'tailscale')
    monkeypatch.setattr(setup, 'run', lambda *args: '{"Web":{"another-app":{}}}')
    with pytest.raises(ValueError, match='leaving it unchanged'):
        setup.main('enable')
    with pytest.raises(ValueError, match='leaving it unchanged'):
        setup.main('disable')


def test_setup_preserves_token_and_only_restarts_app(monkeypatch, tmp_path):
    import json
    from scripts import remote_access as setup
    monkeypatch.setattr(setup, 'PRIVATE', tmp_path)
    monkeypatch.setattr(setup, 'OVERRIDE', tmp_path / 'compose.json')
    monkeypatch.setattr(setup, 'OWNED', tmp_path / 'serve.json')
    monkeypatch.setattr(setup, 'tailscale', lambda: 'tailscale')
    commands = []
    monkeypatch.setattr(setup.subprocess, 'run', lambda args, **kw: commands.append(args))
    def read(*args):
        if args[0] == 'docker':
            return json.dumps({'services':{'app':{'ports':[{'host_ip':'127.0.0.1'}], 'environment':{'OPENATLAS_ACCESS_TOKEN':'existing-token'}}}})
        if args[1] == 'status':
            return json.dumps({'BackendState':'Running', 'Self':{'DNSName':'atlas.example.ts.net.'}})
        return '{}'
    monkeypatch.setattr(setup, 'run', read)
    setup.main('enable')
    env = json.loads(setup.OVERRIDE.read_text())['services']['app']['environment']
    assert env['OPENATLAS_ACCESS_TOKEN'] == 'existing-token'
    assert commands[0][-4:] == ['up', '-d', '--no-build', 'app']
    assert commands[1] == ['tailscale','serve','--bg','--https=443','http://127.0.0.1:8000']
