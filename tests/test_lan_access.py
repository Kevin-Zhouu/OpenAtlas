import json
import pytest
from fastapi.testclient import TestClient
from openatlas.api import create_app
from openatlas.repository import Repository
from scripts import lan_access as setup


def test_phone_login_and_origin_boundary(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENATLAS_LAN_URL', 'http://192.168.1.9:8000')
    monkeypatch.setenv('OPENATLAS_ALLOWED_HOSTS', 'localhost,192.168.1.9')
    monkeypatch.setenv('OPENATLAS_ACCESS_TOKEN', 'test-token')
    c = TestClient(create_app(Repository(tmp_path)), base_url='http://192.168.1.9:8000')
    assert c.get('/api/phone').status_code == 401
    assert c.post('/api/session', json={'token': 'wrong'}).status_code == 403
    assert c.post('/api/session', json={'token': 'test-token'}).status_code == 200
    response = c.get('/api/phone')
    assert response.json()['pairing_url'] == 'http://192.168.1.9:8000/#access_token=test-token'
    assert response.headers['cache-control'] == 'no-store'
    assert c.get('/api/notebooks').status_code == 200
    assert c.post('/api/jobs', json={'prompt': 'Demo trees'}, headers={'Origin': 'http://evil.example'}).status_code == 403
    assert c.get('/', headers={'Host': 'evil.example'}).status_code == 400
    artifact = c.get('/artifacts/book/version/index.html')
    assert 'http://192.168.1.9:8000/artifacts/book/version/' in artifact.headers['content-security-policy']
    assert 'sandbox allow-scripts' in artifact.headers['content-security-policy']


def test_phone_disabled(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENATLAS_LAN_URL', raising=False)
    c = TestClient(create_app(Repository(tmp_path)), base_url='http://localhost')
    assert c.get('/api/phone').json() == {'enabled': False, 'url': '', 'pairing_url': ''}


@pytest.mark.parametrize('host', ['127.0.0.1', '0.0.0.0', '8.8.8.8', '169.254.1.1', 'evil.example'])
def test_reject_non_lan_hosts(host):
    with pytest.raises(ValueError):
        setup.configuration(host, 'token')


def test_lan_requires_auth(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENATLAS_LAN_URL', 'http://192.168.1.9:8000')
    monkeypatch.delenv('OPENATLAS_ACCESS_TOKEN', raising=False)
    with pytest.raises(ValueError):
        create_app(Repository(tmp_path))


def test_setup_preserves_key_on_restart_and_only_restarts_app(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, 'PRIVATE', tmp_path)
    monkeypatch.setattr(setup, 'OVERRIDE', tmp_path / 'compose.json')
    monkeypatch.setattr(setup.subprocess, 'check_output', lambda *a, **k: json.dumps({'services': {'app': {
        'ports': [{'host_ip': '127.0.0.1'}], 'environment': {'OPENATLAS_ACCESS_TOKEN': 'saved-token'}}}}))
    commands = []
    monkeypatch.setattr(setup.subprocess, 'run', lambda args, **kw: commands.append(args))
    setup.main('enable', '192.168.1.9')
    setup.main('enable', '192.168.1.10')
    config = json.loads(setup.OVERRIDE.read_text())['services']['app']
    assert config['ports'] == ['192.168.1.10:8000:8000']
    assert config['environment']['OPENATLAS_ACCESS_TOKEN'] == 'saved-token'
    assert all(c[-4:] == ['up', '-d', '--no-build', 'app'] for c in commands)
    setup.main('disable')
    assert str(setup.OVERRIDE) not in commands[-1]


def test_failed_binding_restores_localhost(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, 'PRIVATE', tmp_path)
    monkeypatch.setattr(setup, 'OVERRIDE', tmp_path / 'compose.json')
    monkeypatch.setattr(setup.subprocess, 'check_output', lambda *a, **k: json.dumps({'services': {'app': {'ports': [{'host_ip': '127.0.0.1'}]}}}))
    calls = []
    def restart(enabled=True):
        calls.append(enabled)
        if enabled:
            raise setup.subprocess.CalledProcessError(1, 'docker')
    monkeypatch.setattr(setup, 'compose', restart)
    with pytest.raises(ValueError, match='localhost has been restored'):
        setup.main('enable', '192.168.1.9')
    assert calls == [True, False]
