#!/usr/bin/env bash
# Private VPS bootstrap. Review this file before executing it as root.
set -euo pipefail
umask 077

die() { echo "OpenAtlas: $*" >&2; exit 1; }
usage() {
  echo 'Usage: sudo bash install.sh --ref <reviewed-40-character-commit>'
  echo 'Development: sudo bash install.sh --source /path/to/reviewed/checkout'
  echo 'Supports dedicated Ubuntu 22.04/24.04 or Debian 12/13 VPS with systemd.'
}

main() {
  local ref='' source_dir='' answer distro codename arch install_tmp
  while (($#)); do
    case "$1" in
      --ref) [[ $# -ge 2 ]] || die 'Missing commit'; ref=$2; shift 2 ;;
      --source) [[ $# -ge 2 ]] || die 'Missing source directory'; source_dir=$2; shift 2 ;;
      --help|-h) usage; return ;;
      *) usage; die 'Unknown argument' ;;
    esac
  done
  [[ -n "$ref" || -n "$source_dir" ]] || { usage; die 'Choose a reviewed commit or local checkout.'; }
  [[ -z "$ref" || "$ref" =~ ^[0-9a-f]{40}$ ]] || die 'Use a full lowercase commit SHA, not a moving branch.'
  [[ -z "$ref" || -z "$source_dir" ]] || die 'Choose only one source.'
  [[ $(uname -s) == Linux ]] || die 'This installer is for Linux VPS hosts.'
  [[ $EUID == 0 ]] || die 'Run with sudo bash install.sh (or sudo bash -s -- when using a pipe).'
  [[ -d /run/systemd/system ]] || die 'A running systemd host is required.'
  [[ ! -e /opt/openatlas && ! -L /opt/openatlas ]] || die '/opt/openatlas already exists; use the installed openatlas command. No files changed.'
  [[ ! -e /etc/openatlas && ! -L /etc/openatlas ]] || die '/etc/openatlas already exists; preserve it and use openatlas commands.'
  [[ ! -e /usr/local/bin/openatlas && ! -L /usr/local/bin/openatlas ]] || die 'An openatlas command already exists.'
  [[ ! -e /etc/systemd/system/openatlas.service ]] || die 'An openatlas systemd unit already exists.'
  # /etc/os-release is supplied by the trusted host OS.
  . /etc/os-release
  distro=$ID; codename=$VERSION_CODENAME
  case "$distro:$VERSION_ID" in
    ubuntu:22.04|ubuntu:24.04|debian:12|debian:13) ;;
    *) die 'Supported: Ubuntu 22.04/24.04 and Debian 12/13.' ;;
  esac
  arch=$(dpkg --print-architecture)
  [[ "$arch" == amd64 || "$arch" == arm64 ]] || die 'Use an amd64 or arm64 VPS.'
  echo 'OpenAtlas private VPS setup'
  echo 'This installs Docker and Tailscale if missing, builds OpenAtlas, and registers its command.'
  echo 'You will sign in to Tailscale. Your other devices must use the same private network.'
  echo 'No public application port will be opened. Existing SSH/firewall rules are preserved.'
  printf 'Continue on this dedicated VPS? [y/N] ' >/dev/tty
  read -r answer </dev/tty
  [[ "$answer" == y || "$answer" == Y || "$answer" == yes ]] || die 'Cancelled.'
  apt-get update
  apt-get install -y ca-certificates curl git python3
  if ! command -v docker >/dev/null; then
    [[ ! -e /etc/apt/sources.list.d/docker.sources && ! -e /etc/apt/sources.list.d/docker.list ]] || die 'Existing Docker repository: install Docker using that configuration, then retry.'
    install -d -m 0755 /etc/apt/keyrings
    curl --proto '=https' --tlsv1.2 -fsSL "https://download.docker.com/linux/$distro/gpg" -o /etc/apt/keyrings/openatlas-docker.asc
    chmod 0644 /etc/apt/keyrings/openatlas-docker.asc
    printf 'deb [arch=%s signed-by=/etc/apt/keyrings/openatlas-docker.asc] https://download.docker.com/linux/%s %s stable\n' "$arch" "$distro" "$codename" >/etc/apt/sources.list.d/openatlas-docker.list
    chmod 0644 /etc/apt/sources.list.d/openatlas-docker.list
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  fi
  if ! command -v tailscale >/dev/null; then
    [[ ! -e /etc/apt/sources.list.d/tailscale.list ]] || die 'Existing Tailscale repository: install Tailscale using that configuration, then retry.'
    curl --proto '=https' --tlsv1.2 -fsSL "https://pkgs.tailscale.com/stable/$distro/$codename.noarmor.gpg" -o /usr/share/keyrings/openatlas-tailscale.gpg
    chmod 0644 /usr/share/keyrings/openatlas-tailscale.gpg
    printf 'deb [signed-by=/usr/share/keyrings/openatlas-tailscale.gpg] https://pkgs.tailscale.com/stable/%s %s main\n' "$distro" "$codename" >/etc/apt/sources.list.d/openatlas-tailscale.list
    chmod 0644 /etc/apt/sources.list.d/openatlas-tailscale.list
    apt-get update
    apt-get install -y tailscale
  fi
  systemctl start docker tailscaled
  docker compose version >/dev/null
  install_tmp=$(mktemp -d)
  trap "rm -rf -- '$install_tmp'" EXIT
  if [[ -n "$ref" ]]; then
    git -C "$install_tmp" init -q
    git -C "$install_tmp" remote add origin https://github.com/Kevin-Zhouu/OpenAtlas.git
    git -C "$install_tmp" fetch -q --depth 1 origin "$ref"
    [[ $(git -C "$install_tmp" rev-parse FETCH_HEAD) == "$ref" ]] || die 'Fetched commit does not match.'
    git -C "$install_tmp" checkout -q --detach FETCH_HEAD
    source_dir=$install_tmp
  fi
  [[ -f "$source_dir/scripts/vps.py" ]] || die 'Selected source does not contain the VPS installer.'
  # Copy only application inputs; never copy .env, .data, auth, or a local library.
  install -d -m 0700 /opt/openatlas
  python3 - "$source_dir" <<'PY'
import pathlib, shutil, sys
source = pathlib.Path(sys.argv[1]).resolve()
target = pathlib.Path('/opt/openatlas/app')
target.mkdir(mode=0o700)
for name in ('Dockerfile', 'requirements.lock', 'openatlas', 'builtins', 'frontend', 'generation', 'scripts'):
    src, dst = source / name, target / name
    if src.is_dir():
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns('node_modules', '__pycache__', '.env', 'dist', '.data', '*.pyc'))
    else:
        shutil.copyfile(src, dst)
PY
  # Copied files belong to root; user-editable boot commands are never installed.
  chmod -R go-rwx /opt/openatlas
  cat >/usr/local/bin/openatlas <<'SH'
#!/bin/sh
# Drop caller-controlled Python and Docker/Compose settings in privileged commands.
exec /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin HOME=/root /usr/bin/python3 -I /opt/openatlas/app/scripts/vps.py "$@"
SH
  chmod 0755 /usr/local/bin/openatlas
  echo 'Command installed. If setup stops, resume with sudo openatlas setup.'
  /usr/local/bin/openatlas setup
}

main "$@"
