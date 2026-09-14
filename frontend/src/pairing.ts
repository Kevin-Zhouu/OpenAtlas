// Consume the fragment once, including under React StrictMode. Never persist it
// in localStorage, browser history, server access logs, or an external QR service.
let pending: Promise<void> | undefined;
export function pairFromFragment(): Promise<void> {
  const token = new URLSearchParams(window.location.hash.slice(1)).get('access_token');
  if (!token) return pending || Promise.resolve();
  window.history.replaceState(null, '', window.location.pathname + window.location.search);
  pending = fetch('/api/session', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  }).then(response => {
    if (!response.ok) throw new Error('This phone link is no longer valid. Scan a fresh code from Settings on your computer.');
  }).finally(() => { pending = undefined; });
  return pending;
}
