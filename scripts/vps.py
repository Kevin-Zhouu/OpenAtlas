"""Guided private VPS deployment. Standard library only; run as root on Linux."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path('/opt/openatlas/app')
STATE = Path('/etc/openatlas')
CONFIG = STATE / 'compose.json'
UNIT = Path('/etc/systemd/system/openatlas.service')


def run(*args, capture=False):
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None).stdout


def save(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(value)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def configuration(root, host, token, boot):
    # Do not inherit .env, desktop/LAN overrides, credentials, or library volumes.
    restart = 'unless-stopped' if boot else 'no'
    common = {'image': 'openatlas-vps:local', 'restart': restart,
              'security_opt': ['no-new-privileges:true'], 'cap_drop': ['ALL'],
              'logging': {'driver': 'json-file', 'options': {'max-size': '10m', 'max-file': '3'}}}
    return {'name': 'openatlas-vps', 'services': {
        'app': {**common, 'build': str(root), 'ports': ['127.0.0.1:8000:8000'],
                'environment': {'OPENATLAS_ACCESS_TOKEN': token,
                                'OPENATLAS_ALLOWED_HOSTS': 'localhost,127.0.0.1,' + host,
                                'OPENATLAS_PUBLIC_ORIGIN': 'https://' + host},
                'volumes': ['library:/data', 'skills:/skills']},
        'runner': {**common, 'command': ['python', '-m', 'openatlas.runner'],
                   'environment': {'OPENATLAS_GENERATION_IMAGE': 'openatlas-generation:local'},
                   'volumes': ['library:/data', 'skills:/skills:ro',
                               '/var/run/docker.sock:/var/run/docker.sock']},
        'generation-image': {'profiles': ['build'], 'image': 'openatlas-generation:local',
                             'build': {'context': str(root), 'dockerfile': 'generation/Dockerfile'},
                             'entrypoint': ['true']},
    }, 'volumes': {'library': {}, 'skills': {}}}


def compose(*args, capture=False):
    return run('docker', 'compose', '--project-name', 'openatlas-vps', '--env-file', '/dev/null',
               '-f', str(CONFIG), *args, capture=capture)


def prompt(message, default=True):
    # Works when the bootstrap script came from a pipe.
    with open('/dev/tty', 'r+') as tty:
        tty.write(message + (' [Y/n] ' if default else ' [y/N] '))
        tty.flush()
        answer = tty.readline().strip().lower()
    return default if not answer else answer in ('y', 'yes')


def current():
    return json.loads(CONFIG.read_text())


def set_boot(enabled):
    config = current()
    for service in ('app', 'runner'):
        config['services'][service]['restart'] = 'unless-stopped' if enabled else 'no'
    save(CONFIG, json.dumps(config, indent=2))
    # Update existing containers in place, without restarting paid jobs.
    ids = compose('ps', '--all', '--quiet', 'app', 'runner', capture=True).split()
    if ids:
        run('docker', 'update', '--restart=' + ('unless-stopped' if enabled else 'no'), *ids, capture=True)
    run('systemctl', 'enable' if enabled else 'disable', 'openatlas.service')


def setup():
    # -I excludes the script directory; add this root-owned installation only.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from remote_access import hostname
    run('docker', 'compose', 'version', capture=True)
    version = run('docker', 'version', '--format', '{{.Server.Version}}', capture=True).strip()
    if int(version.split('.')[0]) < 28:
        raise ValueError('Docker Engine 28 or newer is required for hardened loopback port publishing.')
    status = json.loads(run('tailscale', 'status', '--json', capture=True))
    if status.get('BackendState') != 'Running':
        print('Sign in to your private network using the link Tailscale prints.')
        run('tailscale', 'up')
        status = json.loads(run('tailscale', 'status', '--json', capture=True))
    host = hostname(status)
    if not CONFIG.exists() and json.loads(run('tailscale', 'serve', 'status', '--json', capture=True)):
        raise ValueError('Tailscale already serves another application. Use a dedicated VPS; nothing was replaced.')
    if CONFIG.exists():
        if compose('ps', '--quiet', 'runner', capture=True).strip():
            raise ValueError('Runner is already running. Use openatlas connect or doctor to finish network setup. Setup will not restart active work.')
        boot = current()['services']['app']['restart'] == 'unless-stopped'
        print('Resuming setup with saved configuration and token.')
    else:
        boot = prompt('Start OpenAtlas automatically when this VPS boots?')
        save(CONFIG, json.dumps(configuration(ROOT, host, secrets.token_urlsafe(32), boot), indent=2))
    save(UNIT, '[Unit]\nDescription=OpenAtlas private learning server\nRequires=docker.service tailscaled.service\nAfter=docker.service tailscaled.service network-online.target\n\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/usr/local/bin/openatlas start\nExecStop=/usr/local/bin/openatlas shutdown\nTimeoutStartSec=300\nTimeoutStopSec=180\n\n[Install]\nWantedBy=multi-user.target\n')
    UNIT.chmod(0o644)
    run('systemctl', 'daemon-reload')
    run('systemctl', 'enable' if boot else 'disable', 'openatlas.service')
    if boot:
        run('systemctl', 'enable', 'docker.service', 'tailscaled.service')
    print('Building the application and generation sandbox. This can take several minutes.')
    compose('--profile', 'build', 'build')
    compose('up', '-d', '--no-build', 'app', 'runner')
    print('Enabling private HTTPS. If Tailscale asks, enable HTTPS using its link, then run openatlas connect.')
    connect()
    print('Install Tailscale on your phone/computer and sign in to the same account.')
    print('No public app port is needed. Keep inbound 8000 CLOSED in the VPS firewall.')
    print('Keep your existing SSH rule. Do not disable SSH until you have tested a second connection.')
    print('Run sudo openatlas token for your private sign-in link. Add your model provider in Settings.')
    for attempt in range(30):
        try:
            doctor()
            break
        except urllib.error.URLError:
            if attempt == 29:
                raise
            time.sleep(1)


def connect():
    owned = STATE / 'serve.json'
    status = json.loads(run('tailscale', 'serve', 'status', '--json', capture=True))
    if status and (not owned.exists() or status != json.loads(owned.read_text())):
        raise ValueError('Existing Serve configuration is not owned by OpenAtlas; left unchanged.')
    run('tailscale', 'serve', '--bg', '--https=443', 'http://127.0.0.1:8000')
    save(owned, run('tailscale', 'serve', 'status', '--json', capture=True))


def doctor():
    config = current()
    app = config['services']['app']
    if app['ports'] != ['127.0.0.1:8000:8000'] or not app['environment']['OPENATLAS_ACCESS_TOKEN']:
        raise ValueError('Unsafe configuration: expected loopback-only port and an owner token.')
    # Inspect the running container, not just the intended Compose file.
    ids = compose('ps', '--quiet', 'app', capture=True).split()
    if len(ids) != 1:
        raise ValueError('Application is not running. Run openatlas start.')
    ports = json.loads(run('docker', 'inspect', '--format', '{{json .NetworkSettings.Ports}}', ids[0], capture=True))
    if ports != {'8000/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8000'}]}:
        raise ValueError('Unexpected live container port bindings. Close public access and inspect your deployment.')
    try:
        urllib.request.urlopen('http://127.0.0.1:8000/api/notebooks', timeout=10)
    except urllib.error.HTTPError as error:
        if error.code != 401:
            raise ValueError('Application authentication check failed.') from None
    else:
        raise ValueError('Application API accepted an unauthenticated request.')
    status = json.loads(run('tailscale', 'serve', 'status', '--json', capture=True))
    owned = STATE / 'serve.json'
    if not owned.exists() or not status or status != json.loads(owned.read_text()):
        raise ValueError('Private HTTPS configuration is missing or changed. Run openatlas connect.')
    print('Verified: live port bound to loopback, API requires login, private Serve configuration matches.')
    print('OpenAtlas URL: ' + app['environment']['OPENATLAS_PUBLIC_ORIGIN'])
    print('External firewall, tailnet membership, host patches and backups require separate checks.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['setup', 'start', 'shutdown', 'status', 'doctor', 'connect', 'token', 'rotate-token', 'autostart'])
    parser.add_argument('value', nargs='?', choices=['on', 'off'])
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Use sudo openatlas ' + args.action)
    if args.action == 'setup':
        setup()
    elif args.action == 'start':
        compose('up', '-d', '--no-build', 'app', 'runner')
    elif args.action == 'shutdown':
        # Retain all library volumes. The runner recovers interrupted jobs on start.
        compose('stop', '--timeout', '120', 'runner', 'app')
    elif args.action == 'status':
        compose('ps', 'app', 'runner')
    elif args.action == 'doctor':
        doctor()
    elif args.action == 'connect':
        connect()
    elif args.action == 'autostart':
        if args.value is None:
            parser.error('Use openatlas autostart on or off')
        set_boot(args.value == 'on')
    elif args.action == 'rotate-token':
        config = current()
        config['services']['app']['environment']['OPENATLAS_ACCESS_TOKEN'] = secrets.token_urlsafe(32)
        save(CONFIG, json.dumps(config, indent=2))
        compose('up', '-d', '--no-build', 'app')
        print('Owner token rotated; previous links and browser sessions are invalid. Run openatlas token.')
    elif args.action == 'token':
        if not sys.stdout.isatty():
            raise ValueError('Show sign-in links only in an interactive terminal.')
        env = current()['services']['app']['environment']
        print('Keep this link private; anyone with it and tailnet access controls your library.\n' +
              env['OPENATLAS_PUBLIC_ORIGIN'] + '/#access_token=' + env['OPENATLAS_ACCESS_TOKEN'])


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        # Captured Docker/Serve output may contain secrets; never echo it.
        print(str(error) if isinstance(error, ValueError) else
              'Could not complete this step. Check Docker/Tailscale, then use openatlas status or doctor. Configuration and library were retained.', file=sys.stderr)
        sys.exit(1)
