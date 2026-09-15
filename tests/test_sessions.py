from fastapi.testclient import TestClient

from openatlas.api import create_app
from openatlas.repository import Repository
from openatlas.sessions import (
    SESSION_SECONDS,
    LoginLimiter,
    issue_session,
    valid_session,
)


def test_expiry_tampering_and_rotation():
    session = issue_session('owner-secret', now=100)
    assert 'owner-secret' not in session
    assert valid_session(session, 'owner-secret', now=101)
    assert not valid_session(session, 'rotated', now=101)
    assert not valid_session(session, 'owner-secret', now=100 + SESSION_SECONDS)
    assert not valid_session(session, 'owner-secret', now=99)
    assert not valid_session(session + 'x', 'owner-secret', now=101)
    assert not valid_session('owner-secret', 'owner-secret', now=101)
    assert not valid_session('v1.999999999999.nonce.signature', 'owner-secret', now=101)
    assert not valid_session('v1.101.nonce.☃', 'owner-secret', now=100)


def test_login_is_bounded_and_does_not_accept_raw_cookie(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENATLAS_ACCESS_TOKEN', 'owner-secret')
    client = TestClient(create_app(Repository(tmp_path)), base_url='http://localhost')
    assert client.get('/api/notebooks', headers={'Cookie': 'openatlas_session=owner-secret'}).status_code == 401
    assert client.post('/api/session', json={'token': '☃'}).status_code == 403
    login = client.post('/api/session', json={'token': 'owner-secret'})
    assert login.status_code == 200
    assert 'owner-secret' not in login.headers['set-cookie']
    assert client.get('/api/notebooks').status_code == 200
    for i in range(28):
        assert client.post('/api/session', json={'token': 'wrong'}, headers={'X-Forwarded-For': f'10.0.0.{i}'}).status_code == 403
    limited = client.post('/api/session', json={'token': 'owner-secret'})
    assert limited.status_code == 429
    assert limited.headers['retry-after'] == '60'
    # Existing sessions keep working during a sign-in flood.
    assert client.get('/api/notebooks').status_code == 200


def test_budget_recovers(monkeypatch):
    from openatlas import sessions
    monkeypatch.setattr(sessions.time, 'monotonic', lambda: 1)
    limiter = LoginLimiter(limit=2)
    assert limiter.allow() and limiter.allow()
    assert not limiter.allow()
    monkeypatch.setattr(sessions.time, 'monotonic', lambda: 61)
    assert limiter.allow()
