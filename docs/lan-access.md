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
prepares Docker's LAN port mapping, and opens the desktop UI. Phone access starts
off until enabled in Settings. The launcher can also accept `--host <private-ip>`
when a VPN or multiple adapters make automatic detection ambiguous.

The underlying Docker mapping must exist before a browser can accept incoming
phone connections; it is prepared at application startup, not by granting Docker
control to the web API. Plain `docker compose up` remains a localhost-only mode;
use the desktop launcher for UI-controlled phone sharing. Only the app service
is recreated by the launcher; generation workers are not restarted. Docker must
already be running and the application image built.

The phone link remains the same across restarts while the host IP and token stay
the same. If DHCP changes the address, restart with the launcher and scan the new
QR. An optional DHCP reservation in your router can keep the IP stable.

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

## Colima on macOS

Colima must recognize host adapter addresses. If startup reports `cannot assign
requested address`, localhost is restored. Once, while all Docker work is idle:

```sh
colima stop
colima start --network-host-addresses
```

Then reopen OpenAtlas. This Colima setting persists. Docker Desktop and native
Linux Docker do not need this Colima-specific step. macOS/Windows/Linux launchers
are provided; Windows and Linux have not been physically tested in this change.

## Socket boundary

One FastAPI/Uvicorn process accepts two internal sockets. Docker maps host
`127.0.0.1:8000` to the desktop socket and `<private-ip>:8000` to the phone socket.
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
