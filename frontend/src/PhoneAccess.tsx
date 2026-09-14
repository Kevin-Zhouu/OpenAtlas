import { useEffect, useState } from 'react';
import QRCode from 'qrcode';

type Phone = { enabled: boolean; url: string; pairing_url: string };
export function PhoneAccess() {
  const [phone, setPhone] = useState<Phone | null>(null);
  const [qr, setQr] = useState('');
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    let active = true;
    fetch('/api/phone').then(async response => {
      if (!response.ok) throw new Error('Could not load phone access. Close Settings and try again.');
      const data: Phone = await response.json();
      if (!active) return;
      setPhone(data);
      if (data.enabled) {
        const image = await QRCode.toDataURL(data.pairing_url, {
          width: 240, margin: 4, errorCorrectionLevel: 'M',
          color: { dark: '#103f30', light: '#ffffff' },
        });
        if (active) setQr(image);
      }
    }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, []);
  return <details className="phone-access">
    <summary>Open on your phone <span>Same Wi-Fi</span></summary>
    {error ? <p role="alert">{error}</p> : !phone ? <p className="hint">Loading phone access…</p> : phone.enabled ? <>
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
      <details><summary>Can’t connect?</summary><p className="hint">Avoid guest Wi-Fi and check your firewall allows port 8000. If your computer’s address changes, run the setup command again and scan the updated code.</p></details>
    </> : <>
      <p>Enable Wi-Fi access once on the computer running OpenAtlas. No account or extra app needed.</p>
      <code className="phone-command">python3 scripts/lan_access.py enable</code>
      <p className="hint">Run this in the OpenAtlas folder, then run <code>python3 scripts/lan_access.py open</code> to sign in here and see your QR code. On Windows, use <code>python</code> instead of <code>python3</code>.</p>
    </>}
  </details>;
}
