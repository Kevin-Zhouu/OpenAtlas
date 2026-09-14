import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import QRCode from 'qrcode';
import { PhoneAccess } from './PhoneAccess';
vi.mock('qrcode', () => ({ default: { toDataURL: vi.fn().mockResolvedValue('data:image/png;base64,test') } }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it('shows local setup when Wi-Fi access is off', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ enabled: false }) }));
  render(<PhoneAccess />);
  fireEvent.click(screen.getByText('Open on your phone'));
  expect(await screen.findByText('python3 scripts/lan_access.py enable')).toBeInTheDocument();
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
