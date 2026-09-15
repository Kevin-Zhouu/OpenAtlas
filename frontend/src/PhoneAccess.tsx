import { useEffect, useRef, useState } from 'react';
import QRCode from 'qrcode';

type Phone = { enabled: boolean; available: boolean; desktop: boolean; url: string; pairing_url: string };
export function PhoneAccess() {
  const [phone, setPhone] = useState<Phone | null>(null);
  const [qr, setQr] = useState('');
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const requestVersion = useRef(0);
  const updating = useRef(false);
  useEffect(() => {
    let active = true;
    let loading = false;
    async function refresh() {
      if (loading || updating.current) return;
      loading = true;
      const version = ++requestVersion.current;
      try {
        const response = await fetch('/api/phone', { cache: 'no-store' });
        if (!response.ok) throw new Error('Could not refresh phone access. Retrying automatically…');
        const data: Phone = await response.json();
        if (active && version === requestVersion.current) { setPhone(data); setError(''); }
      } catch (e) {
        if (active && version === requestVersion.current) {
          setPhone(null);
          setError(e instanceof Error ? e.message : 'Could not refresh phone access.');
        }
      } finally { loading = false; }
    }
    void refresh();
    const timer = window.setInterval(refresh, 3000);
    const visible = () => { if (!document.hidden) void refresh(); };
    window.addEventListener('focus', visible);
    window.addEventListener('online', visible);
    document.addEventListener('visibilitychange', visible);
    return () => {
      active = false;
      window.clearInterval(timer);
      window.removeEventListener('focus', visible);
      window.removeEventListener('online', visible);
      document.removeEventListener('visibilitychange', visible);
    };
  }, []);
  useEffect(() => {
    let active = true;
    setQr('');
    setCopied(false);
    if (phone?.enabled) QRCode.toDataURL(phone.pairing_url, {
      width: 240, margin: 4, errorCorrectionLevel: 'M',
      color: { dark: '#103f30', light: '#ffffff' },
    }).then(image => { if (active) setQr(image); }).catch(() => {
      if (active) setError('Could not draw the QR code. Use the phone link below.');
    });
    return () => { active = false; };
  }, [phone?.enabled, phone?.pairing_url]);
  async function update(enabled: boolean, rotate = false) {
    updating.current = true;
    ++requestVersion.current;
    setBusy(true); setError(''); setCopied(false);
    try {
      const response = await fetch('/api/phone', { method: 'PUT',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled, rotate }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not update phone access. Try again.');
      setPhone(data);
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not update phone access.'); }
    finally { updating.current = false; setBusy(false); }
  }
  return <details className="phone-access">
    <summary>Open on your phone <span>Same Wi-Fi</span></summary>
    {error && <p role="alert">{error}</p>}
    {!phone ? <p className="hint">Loading phone access…</p> : phone.enabled ? <>
      <div className="phone-pairing">
        {qr && <img src={qr} width="240" height="240" alt="Scan to sign in to OpenAtlas on your phone" />}
        <div><h3>Keep learning, anywhere at home.</h3>
          <p>Connect your phone to the same Wi-Fi, then scan with its camera to open your library.</p>
          <a href={phone.pairing_url}>{phone.url}</a>
        </div>
      </div>
      <label>Phone sign-in link
        <input readOnly value={phone.pairing_url} onFocus={e => e.currentTarget.select()} />
      </label>
      {navigator.clipboard && <button type="button" className="quiet" onClick={async () => {
        try { await navigator.clipboard.writeText(phone.pairing_url); setCopied(true); }
        catch { setError('Select the phone sign-in link above and copy it manually.'); }
      }}>{copied ? 'Copied' : 'Copy phone link'}</button>}
      <p className="hint">This code grants access to your library and generation settings. Share it only with people you trust. Keep this computer awake. Use a trusted home network; this local connection uses HTTP.</p>
      <details><summary>Can’t connect?</summary><p className="hint">Avoid guest Wi-Fi and check your firewall allows port 8000. The link and QR update automatically when your computer’s network changes. Scan the current code after reconnecting.</p></details>
      {phone.desktop && <div className="phone-actions">
        <button type="button" className="quiet" disabled={busy} onClick={() => update(false)}>Disable phone access</button>
        <button type="button" className="quiet" disabled={busy} onClick={() => update(true, true)}>Reset phone link</button>
      </div>}
      {phone.desktop && <p className="hint">Resetting the link disconnects previously signed-in phones.</p>}
    </> : <>
      <p>Open your library on another device at home. Enable access, then scan the QR with your phone camera.</p>
      {phone.available && phone.desktop ? <button type="button" className="primary" disabled={busy} onClick={() => update(true)}>{busy ? 'Enabling…' : 'Enable phone access'}</button> :
        <p className="hint">{phone.desktop ? "Waiting for a private Wi-Fi or Ethernet connection. The phone link will appear automatically when the connection is ready." : "Wi-Fi sharing is not configured in this running installation. Start OpenAtlas with its desktop launcher, or run the setup command below from the OpenAtlas folder."}</p>}
      {!phone.desktop && !phone.available && <pre><code>python3 scripts/lan_access.py enable</code></pre>}
      <p className="hint">No account or extra phone app. This computer stays accessible without a token at localhost.</p>
    </>}
  </details>;
}
