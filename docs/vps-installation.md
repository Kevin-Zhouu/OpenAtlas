# Private VPS installation (preview)

This is a **single-owner, private-network deployment**, not public hosting.
The installer is implemented but still needs a clean Linux VM installation,
reboot and external network acceptance test before a supported release.
Read [the security review](security-review.md) before putting sensitive data here.

## What you need

- A dedicated Ubuntu 22.04/24.04 or Debian 12/13 VPS, amd64 or arm64, with SSH and sudo/root access.
- Allow room for the application, Chromium, generation images, and your library.
  Start with 4 vCPUs, 8 GB RAM and 40 GB disk; actual generation needs vary.
- A Tailscale account and Tailscale on the devices you will use to open OpenAtlas.
  Protect the account with MFA and restrict tailnet membership/access rules.
- Internet access from the VPS for signed package repositories, image downloads,
  model requests, and Tailscale. No domain purchase is needed.

## Guided setup

For a reviewed local checkout containing this installer:

```sh
sudo bash install.sh --source "$PWD"
```

The installer explains its changes, installs missing dependencies from official
signed apt repositories, asks you to sign in to Tailscale, offers boot startup,
builds the app and generation image, and configures private HTTPS. Approve the
Tailscale HTTPS account setting using its printed link if requested.

This wizard uses fixed, reviewable commands. It does not send host configuration
or secrets to an LLM and does not give an LLM root shell control. Model setup is
available in the existing web Settings once you have signed in. Demo remains
explicit until you choose a real provider; installation makes no paid model calls.

The source is copied into `/opt/openatlas/app`; only application build inputs are
copied. Your checkout's `.env`, `.data`, local library and node_modules are excluded.
Runtime configuration is root-readable at `/etc/openatlas/compose.json`. The
Compose project is `openatlas-vps`; its library and skills use separate named
volumes. Existing desktop Compose deployments are not migrated or overwritten.

### Release distribution

A maintainer must first publish and test a commit containing these changes.
The bootstrap accepts `--ref FULL_REVIEWED_COMMIT_SHA` and fetches that exact
commit from `Kevin-Zhouu/OpenAtlas`. It rejects moving branches. For a future
release, the download command can use that same SHA in GitHub's raw file URL:

```sh
# Replace this placeholder with a published, reviewed release commit.
OPENATLAS_RELEASE_COMMIT=FULL_REVIEWED_COMMIT_SHA
curl --proto '=https' --tlsv1.2 -fsSL \
  "https://raw.githubusercontent.com/Kevin-Zhouu/OpenAtlas/$OPENATLAS_RELEASE_COMMIT/install.sh" \
  -o openatlas-install.sh
less openatlas-install.sh
sudo bash openatlas-install.sh --ref "$OPENATLAS_RELEASE_COMMIT"
```

Piped installation also works (`curl … | sudo bash -s -- --ref …`); prompts read
from the terminal. Download-and-review makes the privileged commands inspectable.
There is currently no published OpenAtlas install.sh domain endpoint promised by
this change. HTTPS and an exact commit pin reduce risks but do not replace release
signing, dependency review, or trust in the source and package repositories.

## Open your library

```sh
sudo openatlas token
```

Open the printed private link on a device connected to your tailnet. The secret
is in a URL fragment (`#access_token=…`), which the existing frontend removes
before exchanging it for an HttpOnly session cookie. It is not put in the HTTP
query string. Treat the link as an administrator password: browser history,
clipboard tools, screenshots or browser extensions can still expose it.
Anyone with the link **and network access** can control this single-owner library.

## Everyday commands

```sh
sudo openatlas start
sudo openatlas shutdown
sudo openatlas status
sudo openatlas doctor
sudo openatlas autostart on
sudo openatlas autostart off
sudo openatlas rotate-token
sudo openatlas token
```

`shutdown` stops app and runner with a grace period and retains the entire library.
Avoid stopping during paid generation: jobs can be interrupted and require recovery
on the next start. Temporary generation containers may remain until the runner's
cleanup resumes. It does not shut down the VPS or stop unrelated Docker services.
With autostart on, the systemd unit starts the app at the next boot, including
after a manual shutdown. Autostart off also removes container restart policies;
it does not disable Docker or Tailscale for other applications. Boot policy changes
update existing containers without restarting running jobs.

`rotate-token` restarts only the HTTP app and invalidates old pairing links and
all old browser sessions. Sessions expire server-side after 30 days. Rotation is
the supported all-device revocation operation; there is no per-device session list.

## Ports and firewall, in plain language

**Do not open public port 8000.** The app listens on `127.0.0.1:8000`, reachable
only from this VPS. Tailscale provides access from your private network over HTTPS.
There is no public Tailscale Funnel, router forwarding, or public HTTP listener.

In your VPS provider's firewall page, retain your SSH rule (usually TCP 22,
preferably restricted to your administrator IP). Do not add inbound 8000, 80 or
443 for OpenAtlas. Tailscale can use outbound relay connections without an inbound
application rule. Existing unrelated services may have their own requirements.
The installer preserves all firewall rules to avoid locking you out of SSH.

The `doctor` command checks actual Docker port bindings, API login enforcement,
and saved Serve configuration. It cannot inspect your VPS provider's firewall or
prove external reachability. From a device **outside your tailnet**, check that
`http://YOUR_VPS_PUBLIC_IP:8000` cannot connect. Repeat for IPv6 if your VPS has it.
Then confirm the private HTTPS URL works on your own Tailscale-connected device.
Do not change Docker's firewall settings to force connectivity; published ports
can bypass UFW rules. See [Docker's firewall documentation](https://docs.docker.com/engine/network/packet-filtering-firewalls/).

## If setup stops

- Before application containers have started: `sudo openatlas setup` resumes with
  the saved secret/configuration and rebuilds missing images.
- After containers start, if HTTPS account approval was needed:
  `sudo openatlas connect`, then `sudo openatlas doctor`.
- Use `sudo openatlas status` for container state. `doctor` deliberately does not
  dump Docker environment values or the private configuration.
- Another application's Serve configuration is never overwritten. Use a dedicated
  VPS or configure a separate service manually.
- Keep `/etc/openatlas` and the Docker library volume backed up with restricted
  access. Secrets are permission-protected, not encrypted at rest. Updating or
  removing the installation is a deliberate maintenance operation; there is no
  automatic source updater or destructive uninstall command in this preview.

References: [Tailscale Linux installation](https://tailscale.com/docs/install/linux),
[Serve](https://tailscale.com/docs/reference/tailscale-cli/serve),
[Docker Ubuntu installation](https://docs.docker.com/engine/install/ubuntu/).
