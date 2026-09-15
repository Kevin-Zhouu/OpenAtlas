import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { JobControls } from './JobControls';
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('queues follow-up instructions and shows their status', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ messages: [], preview: null }) })
    .mockResolvedValueOnce({ ok: true, json: async () => [{ id: 'message', message: 'Larger labels', status: 'queued' }] });
  vi.stubGlobal('fetch', fetcher);
  render(<JobControls jobId="job" stage="building" running codex />);
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));
  fireEvent.change(screen.getByLabelText('Message to Codex'), { target: { value: 'Larger labels' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send instruction' }));
  expect(await screen.findByText('Queued for next turn')).toBeInTheDocument();
  expect(screen.getByLabelText('Message to Codex')).toHaveValue('');
  expect(fetcher).toHaveBeenLastCalledWith('/api/jobs/job/steer', expect.objectContaining({ body: JSON.stringify({ message: 'Larger labels' }) }));
});

it('preserves an instruction after a rejected send', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({ok:true,json:async()=>({messages:[],preview:null})})
    .mockResolvedValueOnce({ ok: false, json: async () => ({ detail: 'Implementation already finished' }) }));
  render(<JobControls jobId="job" stage="building" running codex />);
  fireEvent.change(screen.getByLabelText('Message to Codex'), {target:{value:'Keep my message'}});
  fireEvent.click(screen.getByRole('button', {name:'Send instruction'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Implementation already finished');
  expect(screen.getByLabelText('Message to Codex')).toHaveValue('Keep my message');
});

it('previews without stopping checks, then skips checks on explicit request', async () => {
  const state = { messages: [], preview: { revision: 'rev', entrypoint: 'chapter/index.html' } };
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => state });
  vi.stubGlobal('fetch', fetcher);
  render(<JobControls jobId="job" stage="validating" running codex />);
  const preview = screen.getByRole('button', { name: 'Preview current build' });
  await waitFor(() => expect(preview).toBeEnabled());
  fireEvent.click(preview);
  const frame = screen.getByTitle('Unvalidated Notebook preview');
  expect(frame).toHaveAttribute('sandbox', 'allow-scripts');
  expect(frame).toHaveAttribute('src', '/previews/job/rev/chapter/index.html');
  expect(fetcher).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button', { name: 'Skip checks & preview' }));
  expect(await screen.findByText(/Checks stopped/)).toBeInTheDocument();
  expect(fetcher).toHaveBeenLastCalledWith('/api/jobs/job/skip-validation', expect.objectContaining({ method: 'POST' }));
});
