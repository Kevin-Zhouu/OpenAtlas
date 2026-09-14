"""Enable same-Wi-Fi access for the standard Docker Compose installation."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / '.lan'
OVERRIDE = PRIVATE / 'compose.json'


def validate_host(host):
    address = ipaddress.IPv4Address(host)
    if not any(address in ipaddress.ip_network(net) for net in
               ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')):
        raise ValueError('Choose the private IPv4 address of your Wi-Fi/Ethernet adapter.')
    return str(address)


def detect_host():
    # UDP connect chooses an interface without sending traffic or querying a service.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(('192.0.2.1', 9))
        return validate_host(probe.getsockname()[0])


def configuration(host, token):
    host = validate_host(host)
    return {'services': {'app': {
        # Compose merges this with the existing loopback mapping.
        'ports': [f'{host}:8000:8001'],
        'environment': {
            'OPENATLAS_ALLOWED_HOSTS': 'localhost,127.0.0.1,' + host,
            'OPENATLAS_ACCESS_TOKEN': token,
            'OPENATLAS_LAN_URL': f'http://{host}:8000',
            'OPENATLAS_PUBLIC_ORIGIN': '',
            'OPENATLAS_DESKTOP_PORT': '8000',
        },
    }}}


def compose(enabled=True):
    args = ['docker', 'compose', '-f', str(ROOT / 'compose.yaml')]
    if enabled:
        args += ['-f', str(OVERRIDE)]
    subprocess.run(args + ['up', '-d', '--no-build', 'app'], cwd=ROOT, check=True)


def main(action, host=None):
    if action in ('open', 'status'):
        env = json.loads(OVERRIDE.read_text())['services']['app']['environment']
        if action == 'open':
            webbrowser.open('http://localhost:8000/')
        else:
            print('Configured phone URL: ' + env['OPENATLAS_LAN_URL'])
            print('Run enable to apply this configuration; open to sign in on this computer.')
        return
    if action == 'disable':
        compose(False)
        print('Wi-Fi access disabled. OpenAtlas remains at http://localhost:8000.')
        return
    host = validate_host(host) if host else detect_host()
    resolved = json.loads(subprocess.check_output(
        ['docker', 'compose', '-f', str(ROOT / 'compose.yaml'), 'config', '--format', 'json'],
        cwd=ROOT, text=True, stderr=subprocess.PIPE))
    app = resolved['services']['app']
    if any(port.get('host_ip') != '127.0.0.1' for port in app.get('ports', [])):
        raise ValueError('Set OPENATLAS_BIND=127.0.0.1 first; the helper adds a separate Wi-Fi binding.')
    old = json.loads(OVERRIDE.read_text()) if OVERRIDE.exists() else None
    token = (old['services']['app']['environment']['OPENATLAS_ACCESS_TOKEN'] if old else
             app.get('environment', {}).get('OPENATLAS_ACCESS_TOKEN') or secrets.token_urlsafe(32))
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    with open(OVERRIDE, 'w', opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
        json.dump(configuration(host, token), stream, indent=2)
    OVERRIDE.chmod(0o600)
    try:
        compose()
    except subprocess.CalledProcessError:
        # Restore working localhost access if Docker cannot publish this adapter.
        compose(False)
        raise ValueError('Docker could not bind the Wi-Fi address; localhost has been restored. On Colima, enable --network-host-addresses (see docs/lan-access.md).')
    print(f'Phone URL: http://{host}:8000')
    print('Open http://localhost:8000 → Settings → Open on your phone → Enable phone access.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['enable', 'disable', 'status', 'open'])
    parser.add_argument('--host', help='Private IPv4 address if automatic detection chooses the wrong adapter')
    args = parser.parse_args()
    try:
        main(args.action, args.host)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        if isinstance(error, ValueError):
            print(str(error), file=sys.stderr)
        print('Wi-Fi setup failed. Check Docker is running and use --host with your private Wi-Fi IPv4 address. See docs/lan-access.md.', file=sys.stderr)
        sys.exit(1)
