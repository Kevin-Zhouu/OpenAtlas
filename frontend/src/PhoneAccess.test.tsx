import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import QRCode from 'qrcode';
import { PhoneAccess } from './PhoneAccess';
vi.mock('qrcode', () => ({ default: { toDataURL: vi.fn().mockResolvedValue('data:image/png;base64,test') } }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
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
