# Private phone access with Tailscale Serve

OpenAtlas can stay on your home computer while you use it from your phone over
mobile data or another Wi-Fi network. Tailscale Serve provides a private HTTPS
address; OpenAtlas and Docker continue running on the home computer. The computer
must stay awake, online, and running Docker. This does not upload your library.

## Set up

1. Install [Tailscale](https://tailscale.com/download) on the host and phone.
   Sign both into the same private network (tailnet). On macOS the standalone
   app is recommended; `brew install --cask tailscale-app` installs it and may
   request your administrator password. Approve the app's system/network setup.
2. Start OpenAtlas with the normal Compose instructions and build the current
   app image: `docker compose build app`.
3. From this repository on the host, run:

   ```sh
   python3 scripts/remote_access.py enable
   ```

   On Windows use `py scripts/remote_access.py enable`. The script uses only
   Python's standard library. Docker Compose and the Tailscale client must run
   on the host; Tailscale is not installed in generated Notebook containers.
4. If Tailscale asks you to enable HTTPS, follow its account setup instructions
   and rerun the command. HTTPS certificates expose the machine's certificate
   name in public certificate transparency logs; access to the service itself
   remains private to permitted tailnet members.
5. Open the printed `https://<machine>.<tailnet>.ts.net` URL on your phone with
   Tailscale connected. Get the **OpenAtlas host access token** by running this
   command in an interactive terminal on the host:

   ```sh
   python3 scripts/remote_access.py token
   ```

   Enter that token into OpenAtlas's access dialog. It is separate from the
   OpenAI API key. The same host token also protects the local library API.
6. Open a saved Notebook and try an interaction. To verify access away from home,
   disable Wi-Fi on the phone, keep Tailscale connected, and reload over mobile data.

The generated `.remote/compose.json` stores the URL and a random host access token
(or preserves the existing Compose token). It is ignored by Git and written with
owner-only file permissions on Unix. Protect this directory with your OS user
permissions on Windows. Never share or commit it. It overrides only the app;
existing library volumes and running generation workers remain in place.

## Status, restart, and disable

```sh
python3 scripts/remote_access.py status
# Apply the saved remote configuration after rebuilding an app image:
docker compose -f compose.yaml -f .remote/compose.json up -d --no-build app
# Remove only OpenAtlas's Serve listener and restore normal local Compose:
python3 scripts/remote_access.py disable
```

Serve uses background mode so its configuration survives Tailscale restarts.
Running plain `docker compose up` later omits the remote override; use the combined
command above while remote access is enabled. `disable` retains the private file
so re-enabling can reuse the same token. Your original `.env` is never rewritten.

The helper refuses to overwrite an existing Serve/Funnel configuration owned by
another application. It also refuses to disable a configuration that changed
outside the helper. For shared Tailscale hosts, configure a separate listener or
host manually using the official documentation; do not reset other services.

## Boundaries and troubleshooting

- OpenAtlas's host port remains bound to `127.0.0.1:8000`. No router forwarding,
  public Funnel, or changes to tailnet access rules are made.
- Tailnet policy decides which devices can connect. Anyone with network access
  and the OpenAtlas host token can manage this single-owner installation.
- `OPENATLAS_PUBLIC_ORIGIN` is the exact HTTPS origin, without a path. It requires
  a host access token. Add that exact hostname to `OPENATLAS_ALLOWED_HOSTS`.
  These settings are supplied by the generated override.
- OpenAtlas uses that canonical origin for remote CSRF checks, Secure login
  cookies and Notebook resource CSP. It does not accept arbitrary forwarded host
  or scheme headers as authority. Keep the underlying port on loopback.
- HTTP localhost access continues to work with its own same-origin checks.
- A 400 response usually indicates the wrong allowed host or an omitted override;
  a 401 asks for the host token; a 403 on writes may indicate a mismatched origin.
- Artifacts retain the opaque-origin iframe sandbox. As in local mode, artifact
  URLs themselves are unguessable identifiers rather than per-reader permissions;
  the API is token-protected. This setup is intended for your private tailnet,
  not a public multi-user hosting service.

References: [Serve](https://tailscale.com/docs/features/tailscale-serve),
[Serve CLI](https://tailscale.com/docs/reference/tailscale-cli/serve),
[macOS installation](https://tailscale.com/docs/install/mac).
