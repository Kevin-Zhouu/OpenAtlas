# Security review: VPS access

Status: code review and regression hardening, September 2026. **Not a penetration
test, independent audit, certification, or guarantee.** The repository contains
concurrent local changes; verification applies to the working tree tested.

## Decision

Do not advertise the current application as safe to expose directly to the public
Internet using only a secret URL. The implemented VPS installer uses private
Tailscale HTTPS plus a random owner token. This reduces exposure; it does not make
untrusted generation, the host, or the software supply chain risk-free.

## Findings and disposition

| Finding | Impact | Disposition |
| --- | --- | --- |
| Artifact and draft assets do not require an authenticated session (`api.py` artifact/preview routes) | Anyone who can reach the server and obtains an asset URL can read it; a leaked path is not revocable reader permission | Still present. Private network required; not approved for direct public exposure |
| Browser cookie was the permanent owner token | A stolen cookie was a reusable login secret; server did not enforce expiration | Fixed: distinct HMAC-signed session with random nonce, server-checked expiry, and invalidation when the owner token rotates. Existing users must sign in again |
| Sign-in had no attempt budget | Unbounded online attempts and unnecessary request work | Added global 30 attempts/minute per app process, independent of spoofable forwarded headers. This is not a distributed DoS defense; an attacker can temporarily exhaust sign-in availability |
| URL token grants whole-library authority | Leaked link permits reads, writes, deletion and paid jobs | Fragment exchange retained; installer generates 256-bit token and exposes links only on explicit interactive command. No role separation or MFA in the app |
| Generation network access is unrestricted bridge egress (`execution.py`) | Malicious code/dependencies may probe private services or cloud metadata; browser validation also processes untrusted output | Unresolved public/hostile-workload blocker. Use a dedicated VPS without other secrets/services; disable or restrict cloud metadata credentials at the provider. A tested egress boundary needs separate work |
| Trusted runner controls Docker socket | Runner compromise is effectively host compromise | Existing architectural trust boundary. Socket absent from app and generation containers. Dedicated host, patched daemon, trusted administrators required |
| Subscription mode transfers its auth cache into the job sandbox | Untrusted generated commands can access those credentials in that mode | Existing documented limitation; API-key relay provides a narrower credential boundary. No claim that subscription credentials are hidden from the builder |
| Secrets and library persist on disk | Host administrators, volume backups and Docker administrators can read them | Owner-only installer config; permissions are not encryption. Protect backups and host accounts |
| Package/images/toolchain change over time | Compromised or vulnerable upstream dependencies affect the trusted runtime and installer | Exact application commit required for remote bootstrap; official signed apt repositories. Full release signing, image digest pinning and continuous vulnerability scanning remain release work |

## Existing defenses retained

- Host allowlist and canonical HTTPS origin, with no trust in arbitrary proxy headers.
- Same-origin checks on API writes and stricter desktop-origin checks.
- HttpOnly, SameSite=Strict cookies, Secure on canonical HTTPS.
- Opaque reader iframe (`sandbox="allow-scripts"`), artifact CSP, path containment,
  immutable publications and retained validation receipts.
- Disposable generation containers with non-root commands, no host workspace or
  Docker socket mounts, dropped capabilities, no-new-privileges, read-only root
  filesystems, and CPU/memory/process limits.
- Credentials behind the existing relay in API-key mode; redacted diagnostics.

These controls mitigate specific threats. Browser validation demonstrates tested
behavior, not the absence of malicious code or kernel/browser vulnerabilities.

## Before supporting public browser-only access

Planned, **not implemented** in this change:

1. Choose a tested authentication design covering **all** Notebook and preview
   resources. Opaque iframe subresources cannot simply be gated on the normal
   SameSite cookie without breaking the reader. Evaluate short-lived scoped
   artifact capabilities or a separately authenticated serving architecture.
2. Terminate HTTPS at a maintained proxy, keep the application port private,
   constrain request sizes/timeouts/concurrency, and add identity/MFA and abuse
   controls appropriate for public access. Test IPv4 and IPv6 paths.
3. Block generation/validation access to host networks, cloud metadata and other
   tenants while preserving explicitly permitted model and dependency traffic.
   Test DNS resolution, redirects, IPv6 and alternative address representations.
4. Review browser validation isolation, Docker/runner privilege separation,
   supply-chain updates, disk/queue exhaustion, backup recovery and session revocation.
5. Perform an independent penetration test and clean-VPS installation/reboot/
   external access acceptance tests. Publish supported OS versions only after
   those checks pass; maintain a vulnerability reporting and patching process.

The optional idea of an LLM explaining installation steps should remain an
explanation layer over fixed commands. Giving a model unrestricted root control
would add an avoidable trust boundary and is not implemented by this installer.

## Verification

Regression tests cover session tampering, expiry, token rotation semantics,
Unicode login rejection, rate-limit recovery and forwarded-header spoofing;
existing LAN/remote login and CSRF workflows; installer configuration permissions;
preservation of unrelated Serve state; boot policy updates without restarts; and
rejection of live public port bindings or unauthenticated API access.

Clean Ubuntu/Debian install, real Tailscale account setup, provider firewall checks,
reboot persistence and external penetration testing require a disposable Linux VPS
and account access. Local unit tests do not establish those outcomes.

References: [OWASP session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html),
[OWASP authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html),
[Docker firewall behavior](https://docs.docker.com/engine/network/packet-filtering-firewalls/).
