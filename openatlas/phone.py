"""Small persistent owner-controlled LAN sharing state."""
import json
import os
import secrets
from pathlib import Path
from threading import Lock


class PhoneAccess:
    def __init__(self, data, initial_token=''):
        self.path = Path(data) / 'private' / 'phone-access.json'
        self.lock = Lock()
        self.initial_token = initial_token

    def read(self):
        with self.lock:
            if self.path.exists():
                return json.loads(self.path.read_text())
            return {'enabled': False, 'token': self.initial_token or ''}

    def update(self, enabled, rotate=False):
        with self.lock:
            state = json.loads(self.path.read_text()) if self.path.exists() else {}
            token = state.get('token') or self.initial_token
            if rotate or not token:
                token = secrets.token_urlsafe(32)
            state = {'enabled': enabled, 'token': token}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix('.tmp')
            with open(temporary, 'w', opener=lambda name, flags: os.open(name, flags, 0o600)) as output:
                json.dump(state, output)
            temporary.chmod(0o600)
            temporary.replace(self.path)
            return state


def network_url(path, require_fresh=True):
    """Validate the relay address; freshness controls advertising, not session consent."""
    import ipaddress
    import time
    from urllib.parse import urlsplit

    try:
        state = json.loads(Path(path).read_text())
        age = time.time() - float(state['updated_at'])
        url = state['url']
        parsed = urlsplit(url)
        address = ipaddress.IPv4Address(parsed.hostname)
        private = any(address in ipaddress.ip_network(net) for net in
                      ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
        if (not require_fresh or -5 <= age <= 10) and private and url == f'http://{address}:8000':
            return url
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return ''


class NetworkTrustedHostMiddleware:
    """Keep Host validation aligned with the current relay address, not startup IP."""
    def __init__(self, app, allowed_hosts, state_path):
        self.app = app
        self.allowed_hosts = allowed_hosts
        self.state_path = state_path

    async def __call__(self, scope, receive, send):
        from urllib.parse import urlsplit

        from starlette.middleware.trustedhost import TrustedHostMiddleware

        url = network_url(self.state_path, require_fresh=False) if self.state_path else ''
        hosts = self.allowed_hosts + ([urlsplit(url).hostname] if url else [])
        await TrustedHostMiddleware(self.app, allowed_hosts=hosts)(scope, receive, send)
