import { useEffect, useState } from 'react';

type Message = { id: string; message: string; status: string };
type Controls = { messages: Message[]; preview: { revision: string; entrypoint: string } | null };

export function JobControls({ jobId, stage, running, codex }: {
  jobId: string; stage: string; running: boolean; codex: boolean;
}) {
  const [data, setData] = useState<Controls | null>(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  const [skipped, setSkipped] = useState(false);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/controls`, { cache: 'no-store' });
        if (!response.ok) throw new Error('Could not load generation controls.');
        const result = await response.json();
        if (active && Array.isArray(result.messages)) setData(result);
      } catch (e) { if (active) setError(String(e)); }
      if (active) timer = setTimeout(poll, 2000);
    }
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [jobId]);
  async function act(action: string) {
    setBusy(true); setError('');
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/${action}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        ...(action === 'steer' ? { body: JSON.stringify({ message }) } : {}),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Could not update generation.');
      if (action === 'steer') { setData(old => ({ preview: old?.preview || null, messages: result })); setMessage(''); }
      else { setData(result); setSkipped(true); setShowPreview(true); }
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  const preview = data?.preview;
  const src = preview ? `/previews/${encodeURIComponent(jobId)}/${encodeURIComponent(preview.revision)}/${preview.entrypoint.split('/').map(encodeURIComponent).join('/')}` : '';
  return <section className="job-controls" aria-label="Generation controls">
    {error && <p role="alert">{error}</p>}
    {stage === 'building' && codex && <>
      <div className="steering-heading"><h4>Guide the build</h4><span>Codex</span></div>
      {!!data?.messages.length && <ol className="steering-messages" aria-label="Your instructions">
        {data.messages.map(m => <li key={m.id}><p>{m.message}</p><small>{({ queued: running ? 'Queued for next turn' : 'Not applied — generation stopped', applying: running ? 'Applying' : 'Interrupted', applied: 'Applied', failed: 'Could not apply' } as Record<string, string>)[m.status] || m.status}</small></li>)}
      </ol>}
      {running && <form className="steering-composer" onSubmit={e => { e.preventDefault(); void act('steer'); }}>
        <label className="sr-only" htmlFor="agent-message">Message to Codex</label>
        <textarea id="agent-message" rows={2} maxLength={8000} value={message} onChange={e => setMessage(e.target.value)} placeholder="Ask for a change…" />
        <div className="steering-composer-footer"><span>Applied on the next coding turn</span><button type="submit" aria-label="Send instruction" disabled={busy || !message.trim()}>{busy ? 'Sending…' : 'Send ↑'}</button></div>
      </form>}
    </>}
    {stage === 'validating' && <>
      <div className="phone-actions">
        <button className="quiet" disabled={!preview} onClick={() => setShowPreview(!showPreview)}>{showPreview ? 'Hide preview' : 'Preview current build'}</button>
        {running && !skipped && <button className="quiet" disabled={busy || !preview} onClick={() => void act('skip-validation')}>Skip checks & preview</button>}
      </div>
      <p className="hint">{skipped ? 'Checks stopped. Draft retained; use Resume validation to check this build and publish.' : 'Preview is an unvalidated draft. Skipping stops remaining checks after the current browser operation and retains the draft without publishing.'}</p>
    </>}
    {showPreview && preview && <div className="draft-preview">
      <h4>Draft preview · unvalidated</h4>
      <iframe title="Unvalidated Notebook preview" sandbox="allow-scripts" src={src} />
    </div>}
  </section>;
}
