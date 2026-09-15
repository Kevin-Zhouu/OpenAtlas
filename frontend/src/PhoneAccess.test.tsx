import { act, cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import QRCode from 'qrcode';
import { PhoneAccess } from './PhoneAccess';
vi.mock('qrcode', () => ({ default: { toDataURL: vi.fn().mockResolvedValue('data:image/png;base64,test') } }));
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
it('enables phone access from the desktop UI', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ enabled: false, available: true, desktop: true }) })
    .mockResolvedValueOnce({ ok: true, json: async () => ({ enabled: true, available: true, desktop: true, url:'http://192.168.1.9:8000', pairing_url:'http://192.168.1.9:8000/#access_token=test' }) });
  vi.stubGlobal('fetch', fetcher);
  render(<PhoneAccess />);
  fireEvent.click(screen.getByText('Open on your phone'));
  fireEvent.click(await screen.findByRole('button', {name:'Enable phone access'}));
  expect(await screen.findByAltText('Scan to sign in to OpenAtlas on your phone')).toBeInTheDocument();
  expect(fetcher).toHaveBeenLastCalledWith('/api/phone', expect.objectContaining({method:'PUT', body:JSON.stringify({enabled:true,rotate:false})}));
  expect(screen.queryByText('python3 scripts/lan_access.py enable')).not.toBeInTheDocument();
});

it('renders a locally generated sign-in QR and selectable phone link', async () => {
  const pairing = 'http://192.168.1.9:8000/#access_token=test';
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ enabled: true, url: 'http://192.168.1.9:8000', pairing_url: pairing }) }));
  render(<PhoneAccess />);
  fireEvent.click(screen.getByText('Open on your phone'));
  expect(await screen.findByAltText('Scan to sign in to OpenAtlas on your phone')).toHaveAttribute('src', 'data:image/png;base64,test');
  expect(QRCode.toDataURL).toHaveBeenCalledWith(pairing, expect.any(Object));
  expect(screen.getByLabelText('Phone sign-in link')).toHaveValue(pairing);
});

it('refreshes the URL and QR after network changes and clears them while offline', async () => {
  let url = 'http://192.168.1.9:8000';
  const fetcher = vi.fn().mockImplementation(async () => ({ ok: true, json: async () => ({
    enabled: !!url, available: !!url, desktop: true, url, pairing_url: url ? url + '/#access_token=test' : '',
  }) }));
  vi.stubGlobal('fetch', fetcher);
  vi.useFakeTimers();
  await act(async () => { render(<PhoneAccess />); });
  expect(screen.getByLabelText('Phone sign-in link')).toBeInTheDocument();
  url = 'http://10.1.2.3:8000';
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(screen.getByLabelText('Phone sign-in link')).toHaveValue(url + '/#access_token=test');
  expect(QRCode.toDataURL).toHaveBeenLastCalledWith(url + '/#access_token=test', expect.any(Object));
  expect(screen.getByRole('link')).toHaveAttribute('href', url + '/#access_token=test');
  url = '';
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
  expect(screen.queryByLabelText('Phone sign-in link')).not.toBeInTheDocument();
  expect(screen.queryByRole('img')).not.toBeInTheDocument();
  expect(screen.getByText(/Waiting for a private/)).toBeInTheDocument();
  url = 'http://192.168.2.4:8000';
  await act(async () => { window.dispatchEvent(new Event('online')); });
  expect(screen.getByLabelText('Phone sign-in link')).toHaveValue(url + '/#access_token=test');
  cleanup();
  const calls = fetcher.mock.calls.length;
  await vi.advanceTimersByTimeAsync(6000);
  expect(fetcher).toHaveBeenCalledTimes(calls);
  vi.useRealTimers();
});

it('does not restore an old token when a refresh finishes after resetting the link', async () => {
  const state = (token: string) => ({ enabled: true, available: true, desktop: true,
    url: 'http://192.168.1.9:8000', pairing_url: 'http://192.168.1.9:8000/#access_token=' + token });
  let resolveRefresh: (value: unknown) => void = () => {};
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => state('old') })
    .mockImplementationOnce(() => new Promise(resolve => { resolveRefresh = resolve; }))
    .mockResolvedValueOnce({ ok: true, json: async () => state('new') }));
  render(<PhoneAccess />);
  await screen.findByLabelText('Phone sign-in link');
  await act(async () => { window.dispatchEvent(new Event('focus')); });
  fireEvent.click(screen.getByRole('button', {name: 'Reset phone link'}));
  await waitFor(() => expect(screen.getByLabelText('Phone sign-in link')).toHaveValue(state('new').pairing_url));
  await act(async () => { resolveRefresh({ ok: true, json: async () => state('old') }); });
  expect(screen.getByLabelText('Phone sign-in link')).toHaveValue(state('new').pairing_url);
});
