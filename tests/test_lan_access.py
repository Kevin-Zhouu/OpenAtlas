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
    assert c.get('/api/phone').json() == {'enabled': False, 'url': '', 'pairing_url': '', 'available': False, 'desktop': False}


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
    monkeypatch.setattr(setup, 'start_monitor', lambda host=None: None)
    monkeypatch.setattr(setup, 'PRIVATE', tmp_path)
    monkeypatch.setattr(setup, 'OVERRIDE', tmp_path / 'compose.json')
    monkeypatch.setattr(setup.subprocess, 'check_output', lambda *a, **k: json.dumps({'services': {'app': {
        'ports': [{'host_ip': '127.0.0.1'}], 'environment': {'OPENATLAS_ACCESS_TOKEN': 'saved-token'}}}}))
    commands = []
    monkeypatch.setattr(setup.subprocess, 'run', lambda args, **kw: commands.append(args))
    setup.main('enable', '192.168.1.9')
    setup.main('enable', '192.168.1.10')
    config = json.loads(setup.OVERRIDE.read_text())['services']['app']
    assert config['ports'] == ['127.0.0.1:8001:8001']
    assert config['environment']['OPENATLAS_LAN_STATE'] == '/run/openatlas-lan/status.json'
    assert config['environment']['OPENATLAS_ACCESS_TOKEN'] == 'saved-token'
    assert all(c[-4:] == ['up', '-d', '--no-build', 'app'] for c in commands)
    setup.main('disable')
    assert str(setup.OVERRIDE) not in commands[-1]


def test_failed_binding_restores_localhost(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, 'start_monitor', lambda host=None: None)
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


def test_desktop_ui_controls_phone_access_without_local_token(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENATLAS_LAN_URL', 'http://192.168.1.9:8000')
    monkeypatch.setenv('OPENATLAS_ALLOWED_HOSTS', 'localhost,127.0.0.1,192.168.1.9')
    monkeypatch.setenv('OPENATLAS_DESKTOP_PORT', '8000')
    monkeypatch.setenv('OPENATLAS_ACCESS_TOKEN', 'initial-token')
    app = create_app(Repository(tmp_path))
    desktop = TestClient(app, base_url='http://localhost:8000')
    # TestClient's URL models the desktop socket. The phone's public port maps
    # to a different accepted socket inside Docker, independent of HTTP headers.
    async def lan_socket(scope, receive, send):
        scope = dict(scope, server=('0.0.0.0', 8001))
        await app(scope, receive, send)
    phone = TestClient(lan_socket, base_url='http://192.168.1.9:8000')
    assert desktop.get('/api/notebooks').status_code == 200
    assert desktop.get('/api/phone').json()['enabled'] is False
    assert phone.get('/api/notebooks').status_code == 403
    assert phone.get('/artifacts/book/version/index.html').status_code == 403
    assert desktop.get('/api/phone', headers={'Origin':'null'}).status_code == 403
    assert desktop.get('/api/phone', headers={'Sec-Fetch-Site':'cross-site'}).status_code == 403
    response = desktop.put('/api/phone', json={'enabled':True}, headers={'Origin':'http://localhost:8000'})
    assert response.status_code == 200
    assert response.json()['enabled'] is True
    assert phone.get('/api/notebooks').status_code == 401
    spoof = {'Host':'localhost:8000', 'X-Forwarded-For':'127.0.0.1', 'X-Forwarded-Host':'localhost:8000'}
    assert phone.get('/api/notebooks', headers=spoof).status_code == 401
    assert phone.put('/api/phone', json={'enabled':False}, headers=spoof).status_code == 401
    login = phone.post('/api/session', json={'token':'initial-token'})
    assert login.status_code == 200
    assert 'Max-Age=2592000' in login.headers['set-cookie']
    assert 'Path=/' in login.headers['set-cookie']
    assert 'HttpOnly' in login.headers['set-cookie']
    assert phone.get('/api/notebooks').status_code == 200
    assert phone.put('/api/phone', json={'enabled':False}).status_code == 403
    rotated = desktop.put('/api/phone', json={'enabled':True,'rotate':True}).json()
    assert 'initial-token' not in rotated['pairing_url']
    assert phone.get('/api/notebooks').status_code == 401
    assert phone.post('/api/session', json={'token':'initial-token'}).status_code == 403
    # Persistent state survives recreating the API; desktop never needs a cookie.
    restarted = TestClient(create_app(Repository(tmp_path)), base_url='http://localhost:8000')
    assert restarted.get('/api/phone').json() == rotated
    assert restarted.put('/api/phone', json={'enabled':False}).status_code == 200
    assert phone.get('/api/notebooks').status_code == 403
    assert desktop.get('/api/notebooks').status_code == 200


def test_network_change_updates_url_hosts_and_retains_consent(tmp_path, monkeypatch):
    import time
    status = tmp_path / 'network.json'
    def network(url):
        status.write_text(json.dumps({'url': url, 'updated_at': time.time()}))
    monkeypatch.setenv('OPENATLAS_LAN_STATE', str(status))
    monkeypatch.setenv('OPENATLAS_DESKTOP_PORT', '8000')
    monkeypatch.setenv('OPENATLAS_ACCESS_TOKEN', 'network-test-token')
    monkeypatch.setenv('OPENATLAS_ALLOWED_HOSTS', 'localhost,127.0.0.1')
    monkeypatch.delenv('OPENATLAS_LAN_URL', raising=False)
    app = create_app(Repository(tmp_path / 'data'))
    desktop = TestClient(app, base_url='http://localhost:8000')
    async def phone_socket(scope, receive, send):
        await app(dict(scope, server=('0.0.0.0', 8001)), receive, send)
    phone = TestClient(phone_socket, base_url='http://192.168.1.9:8000')
    network('http://192.168.1.9:8000')
    first = desktop.put('/api/phone', json={'enabled': True}).json()
    assert phone.post('/api/session', json={'token': 'network-test-token'}).status_code == 200
    assert phone.get('/api/notebooks').status_code == 200
    network('http://10.1.2.3:8000')
    changed = desktop.get('/api/phone').json()
    assert changed['pairing_url'] == first['pairing_url'].replace('192.168.1.9', '10.1.2.3')
    assert phone.get('/api/notebooks').status_code == 400  # Old Host is no longer trusted.
    fresh = TestClient(phone_socket, base_url='http://10.1.2.3:8000')
    assert fresh.get('/api/notebooks').status_code == 401
    assert fresh.post('/api/session', json={'token': 'network-test-token'}).status_code == 200
    assert fresh.put('/api/phone', json={'enabled': False}).status_code == 403
    assert fresh.get('/api/notebooks', headers={'Host': 'evil.example'}).status_code == 400
    network('')
    offline = desktop.get('/api/phone').json()
    assert not offline['available'] and not offline['pairing_url']
    assert fresh.get('/api/notebooks').status_code == 503
    network('http://10.1.2.3:8000')
    assert desktop.get('/api/phone').json() == changed  # No app recreation or re-enabling.
    status.write_text(json.dumps({'url': changed['url'], 'updated_at': time.time() - 30}))
    assert not desktop.get('/api/phone').json()['pairing_url']
    # Delayed discovery heartbeat must not revoke a valid phone session.
    assert fresh.get('/api/notebooks').status_code == 200
    assert desktop.put('/api/phone', json={'enabled': False}).status_code == 200
    off = fresh.get('/api/notebooks')
    assert off.status_code == 403 and 'Phone access is off' in off.json()['detail']


def test_network_monitor_rebinds_and_retries_without_compose(tmp_path):
    from scripts.network_monitor import NetworkMonitor
    class FakeRelay:
        def __init__(self, address):
            self.address = address
            self.closed = False
        def serve_forever(self): pass
        def close(self): self.closed = True
    relays = []
    def factory(address):
        if address[0] == '192.168.1.20' and not relays[-1].closed:
            raise AssertionError('Old listener must close before rebinding')
        relay = FakeRelay(address)
        relays.append(relay)
        return relay
    host = ['192.168.1.9']
    monitor = NetworkMonitor(tmp_path / 'status.json', lambda: host[0], factory)
    monitor.refresh()
    monitor.refresh()
    assert len(relays) == 1
    host[0] = '192.168.1.20'
    monitor.refresh()
    assert relays[0].closed and len(relays) == 2
    host[0] = ''
    monitor.refresh()
    assert relays[1].closed and json.loads(monitor.status.read_text())['url'] == ''
    host[0] = '192.168.1.9'
    attempts = []
    def retry(address):
        attempts.append(address)
        if len(attempts) == 1: raise OSError('adapter not ready')
        return factory(address)
    monitor.factory = retry
    monitor.refresh()
    assert json.loads(monitor.status.read_text())['url'] == ''
    monitor.refresh()
    assert json.loads(monitor.status.read_text())['url'] == 'http://192.168.1.9:8000'
    monitor.close()


def test_host_relay_forwards_to_phone_socket_and_closes_connections():
    import socket
    import socketserver
    import threading
    from scripts.network_monitor import Relay
    class Echo(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.sendall(self.request.recv(1024))
    upstream = socketserver.TCPServer(('127.0.0.1', 0), Echo)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    relay = Relay(('127.0.0.1', 0), upstream.server_address)
    threading.Thread(target=relay.serve_forever, daemon=True).start()
    try:
        with socket.create_connection(relay.server_address, timeout=2) as client:
            client.sendall(b'phone socket')
            assert client.recv(1024) == b'phone socket'
    finally:
        relay.close()
        upstream.shutdown()
        upstream.server_close()
