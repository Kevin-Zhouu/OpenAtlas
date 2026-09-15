# OpenAtlas on your phone

On the host computer, open **Settings → Open on your phone → Enable phone access**.
Scan the QR with the camera on a phone connected to the same trusted home Wi-Fi.
No account, phone app, token typing, or per-phone terminal commands are needed.
The computer must stay awake. This does not provide access over mobile data.

Localhost opens directly without a token in the desktop installation. Settings
also provides **Disable phone access** and **Reset phone link**. Disable blocks
LAN requests, including artifact requests. Reset invalidates previous QR links
and phone sessions. Sharing state and the current phone token survive restarts.
The QR is generated locally; no external QR service receives it.

## Starting the desktop installation

After the normal Docker Compose build/install, launch **OpenAtlas.command** on
macOS or **OpenAtlas.cmd** on Windows. On Linux, or from any terminal, use
`python3 scripts/start.py` (`python` on Windows). This detects the host adapter,
prepares a loopback-only phone socket and a background host relay, and opens the desktop UI. Phone access starts
off until enabled in Settings. The launcher can also accept `--host <private-ip>`
when a VPN or multiple adapters make automatic detection ambiguous. This pins the relay to that address; omit `--host` to follow network changes automatically.

The underlying Docker mapping must exist before a browser can accept incoming
phone connections; it is prepared at application startup, not by granting Docker
control to the web API. Plain `docker compose up` remains a localhost-only mode;
use the desktop launcher for UI-controlled phone sharing. Only the app service
is recreated by the launcher; generation workers are not restarted. Docker must
already be running and the application image built.

The host relay checks the current private address every two seconds and rebinds
when it changes. Settings refreshes the URL and locally generated QR every three
seconds, and on focus or reconnection. No app or worker restart is needed for
network changes. Scan the current code after switching networks. The token and
sharing preference remain unchanged. During disconnection, binding failure, or a
stale relay heartbeat, the link is unavailable rather than advertising an old IP.
A delayed heartbeat does not revoke existing authenticated phone sessions. Only
disabling sharing produces “Phone access is off”; an unavailable relay address
produces a temporary-connection response.
The detached relay survives closing the launcher; `lan_access.py disable` stops it.

To install this update on an older installation, rebuild the app image once and
run the desktop launcher once. Subsequent network changes are automatic.

## Network and privacy

Use a trusted home network: this local connection uses HTTP. The QR grants full
workspace access, including generation and settings, so share it only with people
you trust. The token is a URL fragment, removed immediately and exchanged for an
HttpOnly session cookie. Do not forward this port onto the public internet.
Published artifact URLs retain their existing unguessable-URL model and sandbox;
while sharing is enabled, artifact URLs are not individually authenticated.

If the phone cannot connect, avoid isolated guest Wi-Fi, check both devices are
on the same network, and allow TCP port 8000 on the host's private-network firewall.
No router port forwarding is necessary.

## Host relay

The relay runs on macOS, Windows or Linux with Python's standard library. It binds
only the detected RFC1918 address on port 8000 and forwards raw connections to
`127.0.0.1:8001`. Docker no longer needs to bind a changing Wi-Fi address, including
on Colima. Keep local port 8001 free. The relay publishes a non-secret status file
in `.lan/network`, mounted read-only into the application. The API accepts only a
fresh private address from that file. The status directory contains no pairing token.

## Socket boundary

One FastAPI/Uvicorn process accepts two internal sockets. Docker maps host
`127.0.0.1:8000` to the desktop socket and `127.0.0.1:8001` to the phone socket.
The host relay maps `<current-private-ip>:8000` to the latter.
Both use the same user-facing port, UI, API, database, and artifact server. The
accepted socket, not client-supplied Host or forwarded headers, identifies desktop
access. Cross-origin desktop API access is rejected. Never publish the desktop
socket on an external interface or route an external proxy to it. Do not combine
the desktop LAN override with the optional Tailscale setup.

Phone sign-in is remembered for 30 days in an HttpOnly cookie, including after
closing and reopening the browser. Resetting the phone link still invalidates old
sessions immediately. Returning from a Notebook or restoring a cached Safari page
rechecks the session automatically. If cookies were cleared or the link was reset,
scan the current QR again; manual token entry is only an advanced fallback.
