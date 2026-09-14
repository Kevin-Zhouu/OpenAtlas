# OpenAtlas on your phone (same Wi-Fi)

No signup, tunnel, domain, router forwarding, or phone app is needed. Your phone and the computer running OpenAtlas must be on the same trusted home network. The computer must stay awake with Docker running. This does not provide access over mobile data or from outside your home.

From the OpenAtlas directory, after the normal Docker Compose installation:

```sh
docker compose build app
python3 scripts/lan_access.py enable
python3 scripts/lan_access.py open
```

On Windows use `python` instead of `python3`. The second command detects the computer's private IPv4 address, preserves the localhost port, adds a binding for that specific network address, and enables host-token authentication. Only the web service restarts; running generation workers continue. The third command opens a signed-in browser on the computer. In **Settings → Open on your phone**, scan the QR with your phone camera. Or copy the phone sign-in link. Your existing Notebooks and generation settings are available immediately.

The QR is generated locally in the browser. It grants full access to this local workspace, including generating Notebooks and changing settings. Keep it private. The token travels in the URL fragment (not HTTP access logs) and is immediately removed from browser history and exchanged for an HttpOnly session cookie. This is a trusted-LAN HTTP feature, not an encrypted public hosting solution. Generated Notebook artifacts retain their existing opaque sandbox and unguessable URLs; artifact URLs themselves are not authenticated. Do not port-forward this service onto the internet.

## Restart and disable

The configuration and access token are saved in the ignored `.lan/compose.json` file. Docker restarts retain them. To apply updates or bring the app back after `down`, use:

```sh
python3 scripts/lan_access.py enable
```

The same address and token produce the same QR. If DHCP changes the computer's address, run enable again and scan the new code. A router DHCP reservation is optional if you want the address to stay fixed. Existing sign-in cookies are browser sessions; scan again if needed. `python3 scripts/lan_access.py open` always signs in on the host without printing the token.

To return to localhost-only access:

```sh
python3 scripts/lan_access.py disable
```

Plain `docker compose up` also uses the default localhost configuration; use the helper when Wi-Fi access is desired. Do not combine the LAN and Tailscale overrides. The helper does not manage or stop independently configured tunnels.

## Connection trouble

- Use the same Wi-Fi, not an isolated guest network. Routers with client isolation prevent device-to-device connections.
- Allow inbound TCP port 8000 through your computer's firewall on the private/home network. Do not add router port forwarding.
- With a VPN or multiple adapters, explicitly choose your Wi-Fi/Ethernet IPv4 address: `python3 scripts/lan_access.py enable --host 192.168.1.20`. Find it in your operating system's network settings. The helper accepts RFC1918 private IPv4 addresses only.
- The helper supports the standard Docker Compose installation on macOS, Windows, and Linux. Docker must support publishing on your selected host address. If an address changed, enable again.

For native development, set `OPENATLAS_LAN_URL=http://<private-ip>:8000`, `OPENATLAS_ALLOWED_HOSTS=localhost,127.0.0.1,<private-ip>`, and a strong `OPENATLAS_ACCESS_TOKEN` in the API environment, then bind Uvicorn to the chosen interface. Settings reads the explicit host URL because addresses detected inside Docker belong to its virtual network.

### Colima on macOS

Colima's VM must recognize host adapter addresses before Docker can bind them.
If setup reports `cannot assign requested address`, the helper restores localhost
access. When no generation or other Docker workload is running, enable Colima's
built-in host-address forwarding once:

```sh
colima stop
colima start --network-host-addresses
python3 scripts/lan_access.py enable
```

This setting persists in Colima. It requires no extra service or account; stopping
Colima briefly stops all containers, so wait for active work to finish first.
