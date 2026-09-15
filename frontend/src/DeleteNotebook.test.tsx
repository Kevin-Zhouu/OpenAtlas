import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { DeleteNotebook } from './DeleteNotebook';
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it('requires confirmation and explains deletion includes every related job', async () => {
  const fetcher = vi.fn().mockResolvedValue({ok:true,json:async()=>({notebook_id:'book',status:'deleting'})});
  vi.stubGlobal('fetch',fetcher);
  const deleted=vi.fn();
  render(<DeleteNotebook target={{kind:'jobs',id:'job',title:'Private lesson'}} onClose={()=>{}} onDeleted={deleted} />);
  expect(fetcher).not.toHaveBeenCalled();
  expect(screen.getByText(/every version and related job/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Delete permanently'}));
  await vi.waitFor(()=>expect(deleted).toHaveBeenCalledWith('book'));
  expect(fetcher).toHaveBeenCalledWith('/api/jobs/job',{method:'DELETE'});
});
it('keeps the dialog open on failure and cancel does not delete', async () => {
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,json:async()=>({detail:'Unable to queue deletion'})}));
  const close=vi.fn(),deleted=vi.fn();
  render(<DeleteNotebook target={{kind:'notebooks',id:'book',title:'Lesson'}} onClose={close} onDeleted={deleted} />);
  fireEvent.click(screen.getByRole('button',{name:'Delete permanently'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Unable to queue deletion');
  expect(deleted).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Keep Notebook'}));
  expect(close).toHaveBeenCalled();
});
