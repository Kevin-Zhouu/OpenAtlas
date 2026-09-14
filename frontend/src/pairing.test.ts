import { afterEach, expect, it, vi } from 'vitest';
afterEach(() => { vi.unstubAllGlobals(); window.history.replaceState(null, '', '/'); vi.resetModules(); });
it('removes the credential from history before login and exchanges it only once', async () => {
  window.history.replaceState(null, '', '/#access_token=private-token');
  const fetcher = vi.fn().mockImplementation(async () => {
    expect(window.location.hash).toBe('');
    return { ok: true };
  });
  vi.stubGlobal('fetch', fetcher);
  const { pairFromFragment } = await import('./pairing');
  await Promise.all([pairFromFragment(), pairFromFragment()]);
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(fetcher).toHaveBeenCalledWith('/api/session', expect.objectContaining({ body: JSON.stringify({ token: 'private-token' }) }));
});
it('reports expired links without retaining the token', async () => {
  window.history.replaceState(null, '', '/#access_token=expired');
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false }));
  const { pairFromFragment } = await import('./pairing');
  await expect(pairFromFragment()).rejects.toThrow('no longer valid');
  expect(window.location.hash).toBe('');
});
