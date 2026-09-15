import json
import os
from pathlib import Path
import subprocess
import urllib.error

import pytest

from scripts import vps


def test_private_config_and_compose_parser(tmp_path):
    config = vps.configuration(Path(__file__).resolve().parents[1], 'atlas.example.ts.net', 'test-secret', False)
    assert config['services']['app']['ports'] == ['127.0.0.1:8000:8000']
    assert config['services']['runner']['restart'] == 'no'
    assert '/var/run/docker.sock:/var/run/docker.sock' not in config['services']['app']['volumes']
    assert 'OPENAI_API_KEY' not in json.dumps(config)
    path = tmp_path / 'compose.json'
    vps.save(path, json.dumps(config))
    assert os.stat(path).st_mode & 0o777 == 0o600
    # Replacing the file also repairs overly broad permissions.
    path.chmod(0o644)
    vps.save(path, json.dumps(config))
    assert os.stat(path).st_mode & 0o777 == 0o600


def test_compose_ignores_ambient_env_file(monkeypatch):
    calls = []
    monkeypatch.setattr(vps, 'run', lambda *args, **kw: calls.append(args))
    vps.compose('stop', '--timeout', '120', 'runner', 'app')
    assert calls[0][:7] == ('docker', 'compose', '--project-name', 'openatlas-vps', '--env-file', '/dev/null', '-f')
    assert 'down' not in calls[0]


def test_boot_change_does_not_restart_workers(tmp_path, monkeypatch):
    path = tmp_path / 'compose.json'
    monkeypatch.setattr(vps, 'CONFIG', path)
    vps.save(path, json.dumps(vps.configuration(tmp_path, 'atlas.example.ts.net', 'secret', True)))
    monkeypatch.setattr(vps, 'compose', lambda *args, **kw: 'app-id\nrunner-id\n')
    calls = []
    monkeypatch.setattr(vps, 'run', lambda *args, **kw: calls.append(args))
    vps.set_boot(False)
    assert vps.current()['services']['runner']['restart'] == 'no'
    assert ('docker', 'update', '--restart=no', 'app-id', 'runner-id') in calls
    assert ('systemctl', 'disable', 'openatlas.service') in calls


def test_connect_does_not_overwrite_other_services(tmp_path, monkeypatch):
    monkeypatch.setattr(vps, 'STATE', tmp_path)
    calls = []
    def run(*args, **kw):
        calls.append(args)
        return '{"Web":{"unrelated":{}}}'
    monkeypatch.setattr(vps, 'run', run)
    with pytest.raises(ValueError, match='left unchanged'):
        vps.connect()
    assert calls == [('tailscale', 'serve', 'status', '--json')]


@pytest.mark.parametrize('binding', ['0.0.0.0', '::'])
def test_doctor_rejects_live_public_binding(binding, tmp_path, monkeypatch):
    monkeypatch.setattr(vps, 'current', lambda: vps.configuration(tmp_path, 'atlas.example.ts.net', 'secret', True))
    monkeypatch.setattr(vps, 'compose', lambda *args, **kw: 'app-id')
    monkeypatch.setattr(vps, 'run', lambda *args, **kw: json.dumps({'8000/tcp': [{'HostIp': binding, 'HostPort': '8000'}]}))
    with pytest.raises(ValueError, match='live container port'):
        vps.doctor()


def test_doctor_rejects_missing_auth(tmp_path, monkeypatch):
    monkeypatch.setattr(vps, 'current', lambda: vps.configuration(tmp_path, 'atlas.example.ts.net', 'secret', True))
    monkeypatch.setattr(vps, 'compose', lambda *args, **kw: 'app-id')
    monkeypatch.setattr(vps, 'run', lambda *args, **kw: json.dumps({'8000/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '8000'}]}))
    monkeypatch.setattr(vps.urllib.request, 'urlopen', lambda *args, **kw: None)
    with pytest.raises(ValueError, match='unauthenticated'):
        vps.doctor()


def test_bootstrap_help_and_ref_rejection():
    script = Path(__file__).resolve().parents[1] / 'install.sh'
    assert subprocess.run(['bash', str(script), '--help'], capture_output=True).returncode == 0
    rejected = subprocess.run(['bash', str(script), '--ref', 'main'], capture_output=True, text=True)
    assert rejected.returncode != 0
    assert 'full lowercase commit SHA' in rejected.stderr
