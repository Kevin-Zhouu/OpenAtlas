"""Bounded, expiring browser credentials, distinct from the owner pairing secret."""
import hashlib
import hmac
import secrets
import time
from collections import deque
from threading import Lock

SESSION_SECONDS = 30 * 24 * 60 * 60


def equal_secret(left, right):
    try:
        return hmac.compare_digest(left.encode('utf-8'), right.encode('utf-8'))
    except UnicodeError:
        return False


def issue_session(key, now=None):
    now = int(time.time() if now is None else now)
    payload = f'v1.{now + SESSION_SECONDS}.{secrets.token_hex(16)}'
    signature = hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return payload + '.' + signature


def valid_session(value, key, now=None):
    if not key or len(value) > 256:
        return False
    try:
        version, expires, nonce, signature = value.split('.')
        now = time.time() if now is None else now
        if version != 'v1' or not now < int(expires) <= now + SESSION_SECONDS:
            return False
        payload = f'{version}.{expires}.{nonce}'
        expected = hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return equal_secret(signature, expected)
    except (ValueError, UnicodeError):
        return False


class LoginLimiter:
    """Global per-process budget; proxy/client headers cannot mint new buckets.

    This single-owner app intentionally trades login availability under attack
    for bounded work. An upstream access gateway is still needed on the Internet.
    """
    def __init__(self, limit=30, window=60):
        self.limit, self.window = limit, window
        self.attempts = deque()
        self.lock = Lock()

    def allow(self):
        with self.lock:
            now = time.monotonic()
            while self.attempts and self.attempts[0] <= now - self.window:
                self.attempts.popleft()
            if len(self.attempts) >= self.limit:
                return False
            self.attempts.append(now)
            return True
