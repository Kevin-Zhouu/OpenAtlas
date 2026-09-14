import { useEffect, useState } from 'react';
import QRCode from 'qrcode';

type Phone = { enabled: boolean; available: boolean; desktop: boolean; url: string; pairing_url: string };
export function PhoneAccess() {
  const [phone, setPhone] = useState<Phone | null>(null);
  const [qr, setQr] = useState('');
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    fetch('/api/phone').then(async response => {
      if (!response.ok) throw new Error('Could not load phone access. Close Settings and try again.');
      const data: Phone = await response.json();
      if (active) setPhone(data);
    }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    let active = true;
    setQr('');
    if (phone?.enabled) QRCode.toDataURL(phone.pairing_url, {
      width: 240, margin: 4, errorCorrectionLevel: 'M',
      color: { dark: '#103f30', light: '#ffffff' },
    }).then(image => { if (active) setQr(image); }).catch(() => {
      if (active) setError('Could not draw the QR code. Use the phone link below.');
    });
    return () => { active = false; };
  }, [phone]);
  async function update(enabled: boolean, rotate = false) {
    setBusy(true); setError(''); setCopied(false);
    try {
      const response = await fetch('/api/phone', { method: 'PUT',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled, rotate }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not update phone access. Try again.');
      setPhone(data);
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not update phone access.'); }
    finally { setBusy(false); }
  }
  return <details className="phone-access">
    <summary>Open on your phone <span>Same Wi-Fi</span></summary>
    {error && <p role="alert">{error}</p>}
    {!phone ? <p className="hint">Loading phone access…</p> : phone.enabled ? <>
      <div className="phone-pairing">
        {qr && <img src={qr} width="240" height="240" alt="Scan to sign in to OpenAtlas on your phone" />}
        <div><h3>Keep learning, anywhere at home.</h3>
          <p>Connect your phone to the same Wi-Fi, then scan with its camera to open your library.</p>
          <a href={phone.url}>{phone.url}</a>
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
      <details><summary>Can’t connect?</summary><p className="hint">Avoid guest Wi-Fi and check your firewall allows port 8000. If your computer’s address changes, restart OpenAtlas and scan the updated code.</p></details>
      {phone.desktop && <div className="phone-actions">
        <button type="button" className="quiet" disabled={busy} onClick={() => update(false)}>Disable phone access</button>
        <button type="button" className="quiet" disabled={busy} onClick={() => update(true, true)}>Reset phone link</button>
      </div>}
      {phone.desktop && <p className="hint">Resetting the link disconnects previously signed-in phones.</p>}
    </> : <>
      <p>Open your library on another device at home. Enable access, then scan the QR with your phone camera.</p>
      {phone.available && phone.desktop ? <button type="button" className="primary" disabled={busy} onClick={() => update(true)}>{busy ? 'Enabling…' : 'Enable phone access'}</button> :
        <p className="hint">Phone sharing is available in the desktop installation. Start OpenAtlas with its desktop launcher to connect your Wi-Fi adapter.</p>}
      <p className="hint">No account or extra phone app. This computer stays accessible without a token at localhost.</p>
    </>}
  </details>;
}
