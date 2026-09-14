"""One ASGI server, with separate internal sockets for desktop and LAN ingress.

Both Docker mappings use user-facing port 8000. Only the desktop socket is
published on host loopback. A phone cannot forge the accepted socket's port.
"""
import os
import socket
import uvicorn


def main():
    ports = [8000, 8001] if os.getenv('OPENATLAS_DESKTOP_PORT') == '8000' else [8000]
    sockets = []
    try:
        for port in ports:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('0.0.0.0', port))
            listener.listen(128)
            sockets.append(listener)
        # Do not allow forwarded headers to redefine the connection identity.
        uvicorn.Server(uvicorn.Config('openatlas.api:app', proxy_headers=False)).run(sockets=sockets)
    finally:
        for listener in sockets:
            listener.close()


if __name__ == '__main__':
    main()
