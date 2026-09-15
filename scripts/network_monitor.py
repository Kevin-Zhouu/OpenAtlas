"""Host-side LAN relay: follow address changes without restarting Docker or the app."""
import argparse
import ipaddress
import json
import select
import socket
import socketserver
import threading
import time
from pathlib import Path


def private_host(host):
    address = ipaddress.IPv4Address(host)
    if not any(address in ipaddress.ip_network(net) for net in
               ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')):
        raise ValueError('No private Wi-Fi/Ethernet IPv4 address is available')
    return str(address)


def detect_host():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(('192.0.2.1', 9))
        return private_host(probe.getsockname()[0])


def write_status(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value), encoding='utf-8')
    temporary.replace(path)


class Forwarder(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            with socket.create_connection(self.server.upstream, timeout=5) as upstream:
                self.request.settimeout(5)
                upstream.settimeout(5)
                while not self.server.stopping.is_set():
                    readable, _, _ = select.select([self.request, upstream], [], [], 1)
                    for source in readable:
                        data = source.recv(65536)
                        if not data:
                            return
                        (upstream if source is self.request else self.request).sendall(data)
        except OSError:
            return


class Relay(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, upstream=('127.0.0.1', 8001)):
        self.upstream = upstream
        self.stopping = threading.Event()
        super().__init__(address, Forwarder)

    def close(self):
        self.stopping.set()
        self.shutdown()
        self.server_close()


class NetworkMonitor:
    def __init__(self, status, detect=detect_host, factory=Relay):
        self.status = status
        self.detect = detect
        self.factory = factory
        self.relay = None
        self.host = ''

    def close(self):
        if self.relay:
            self.relay.close()
        self.relay = None
        self.host = ''

    def refresh(self):
        try:
            host = private_host(self.detect())
        except (OSError, ValueError):
            host = ''
        if host != self.host:
            self.close()
            if host:
                try:
                    self.relay = self.factory((host, 8000))
                    threading.Thread(target=self.relay.serve_forever, daemon=True).start()
                    self.host = host
                except OSError:
                    self.close()
        write_status(self.status, {'url': f'http://{self.host}:8000' if self.host else '',
                                   'updated_at': time.time()})


def run(directory, run_id, host=None):
    control = directory / 'control.json'
    monitor = NetworkMonitor(directory / 'status.json', (lambda: host) if host else detect_host)
    try:
        while json.loads(control.read_text()).get('run_id') == run_id:
            monitor.refresh()
            time.sleep(2)
    except (OSError, ValueError):
        pass
    finally:
        monitor.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('run_id')
    parser.add_argument('--host')
    args = parser.parse_args()
    run(args.directory, args.run_id, args.host)
