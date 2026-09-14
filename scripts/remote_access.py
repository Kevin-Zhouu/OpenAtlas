"""Host-side Tailscale Serve setup for the standard Docker Compose installation."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / '.remote'
OVERRIDE = PRIVATE / 'compose.json'
OWNED = PRIVATE / 'serve.json'


def run(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True, stderr=subprocess.PIPE)


def tailscale():
    candidates = [shutil.which('tailscale'), '/Applications/Tailscale.app/Contents/MacOS/Tailscale',
                  os.path.join(os.environ.get('ProgramFiles', 'C:/Program Files'), 'Tailscale', 'tailscale.exe')]
    for path in candidates:
        if path and Path(path).is_file():
            return path
    raise ValueError('Install Tailscale and sign in first: https://tailscale.com/download')


def hostname(status):
    if status.get('BackendState') != 'Running':
        raise ValueError('Open Tailscale and sign in on this computer, then run enable again.')
    host = status.get('Self', {}).get('DNSName', '').rstrip('.')
    if not re.fullmatch(r'[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+\.ts\.net', host):
        raise ValueError('Tailscale did not provide a valid ts.net hostname. Enable MagicDNS.')
    return host


def configuration(host, token):
    return {'services': {'app': {'environment': {
        'OPENATLAS_ALLOWED_HOSTS': 'localhost,127.0.0.1,' + host,
        'OPENATLAS_ACCESS_TOKEN': token,
        'OPENATLAS_PUBLIC_ORIGIN': 'https://' + host,
    }}}}


def save(path, value):
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    with open(path, 'w', opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
        json.dump(value, stream, indent=2)
    path.chmod(0o600)


def compose(remote=True):
    args = ['docker', 'compose', '-f', str(ROOT / 'compose.yaml')]
    if remote:
        args += ['-f', str(OVERRIDE)]
    # Only the HTTP service changes; never interrupt running generation workers.
    subprocess.run(args + ['up', '-d', '--no-build', 'app'], cwd=ROOT, check=True)


def main(action):
    if action == 'token':
        if not sys.stdout.isatty():
            raise ValueError('Show the access token only in an interactive terminal.')
        print(json.loads(OVERRIDE.read_text())['services']['app']['environment']['OPENATLAS_ACCESS_TOKEN'])
        return
    cli = tailscale()
    status = json.loads(run(cli, 'serve', 'status', '--json'))
    if action == 'status':
        print('OpenAtlas Serve enabled' if OWNED.exists() and status == json.loads(OWNED.read_text()) else 'OpenAtlas Serve is not enabled or its configuration has changed')
        if OVERRIDE.exists():
            print(json.loads(OVERRIDE.read_text())['services']['app']['environment']['OPENATLAS_PUBLIC_ORIGIN'])
        return
    owned = json.loads(OWNED.read_text()) if OWNED.exists() else None
    if status and status != owned:
        raise ValueError('Existing Tailscale Serve/Funnel configuration is not managed by OpenAtlas; leaving it unchanged. See docs/remote-access.md for manual setup.')
    if action == 'disable':
        if owned and status:
            run(cli, 'serve', '--https=443', 'off')
        if OWNED.exists():
            OWNED.unlink()
        compose(False)
        print('Remote forwarding disabled. OpenAtlas remains at http://localhost:8000.')
        return
    host = hostname(json.loads(run(cli, 'status', '--json')))
    if os.environ.get('OPENATLAS_BIND', '127.0.0.1') != '127.0.0.1':
        raise ValueError('Use OPENATLAS_BIND=127.0.0.1 for private Serve access.')
    # Check the resolved Compose configuration without displaying credentials.
    resolved = json.loads(run('docker', 'compose', 'config', '--format', 'json'))
    ports = resolved['services']['app'].get('ports', [])
    if any(p.get('host_ip') != '127.0.0.1' for p in ports):
        raise ValueError('Compose must bind the app port to 127.0.0.1; check OPENATLAS_BIND in .env.')
    old = json.loads(OVERRIDE.read_text()) if OVERRIDE.exists() else None
    token = (old['services']['app']['environment']['OPENATLAS_ACCESS_TOKEN'] if old else
             resolved['services']['app'].get('environment', {}).get('OPENATLAS_ACCESS_TOKEN') or secrets.token_urlsafe(32))
    save(OVERRIDE, configuration(host, token))
    compose()
    try:
        # Serve is private to the tailnet. Never enable Funnel or change network ACLs.
        subprocess.run([cli, 'serve', '--bg', '--https=443', 'http://127.0.0.1:8000'], check=True)
    except subprocess.CalledProcessError:
        print('App authentication is configured; Serve did not start. Complete any Tailscale HTTPS setup and retry enable.', file=sys.stderr)
        raise
    save(OWNED, json.loads(run(cli, 'serve', 'status', '--json')))
    print('OpenAtlas URL: https://' + host)
    print('On your phone, connect Tailscale to the same tailnet and open this URL.')
    print('Get your host access token in a terminal: python3 scripts/remote_access.py token')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['enable', 'disable', 'status', 'token'])
    try:
        main(parser.parse_args().action)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        # Do not dump captured process output: Compose configuration contains secrets.
        print(str(error) if isinstance(error, ValueError) else 'Setup could not complete. Check that Docker and Tailscale are running, then retry.', file=sys.stderr)
        sys.exit(1)
