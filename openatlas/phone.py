"""Small persistent owner-controlled LAN sharing state."""
import json
import os
from pathlib import Path
import secrets
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
