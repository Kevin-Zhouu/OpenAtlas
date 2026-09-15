import { useState } from 'react';

export function DeleteNotebook({ target, onClose, onDeleted }: {
  target: { kind: 'jobs' | 'notebooks'; id: string; title: string };
  onClose: () => void;
  onDeleted: (notebookId: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function remove() {
    setBusy(true); setError('');
    try {
      const response = await fetch(`/api/${target.kind}/${encodeURIComponent(target.id)}`, {method:'DELETE'});
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Could not delete. Please try again.');
      onDeleted(result.notebook_id);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); setBusy(false); }
  }
  return <div className="modal-backdrop"><section className="modal delete-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-title">
    <h2 id="delete-title">Permanently delete this Notebook?</h2>
    <p className="delete-subject">{target.title}</p>
    <p>This removes the Notebook, every version and related job, saved source, prompts, messages, previews, logs and diagnostics. Active work will stop. There is no undo.</p>
    <p className="hint">Deletion finishes after generation workers stop. Copies you downloaded or sent to an AI provider are outside this local library.</p>
    {error && <p role="alert">{error}</p>}
    <div className="delete-actions"><button className="quiet" autoFocus disabled={busy} onClick={onClose}>Keep Notebook</button><button className="danger-button" disabled={busy} onClick={() => void remove()}>{busy ? 'Deleting…' : 'Delete permanently'}</button></div>
  </section></div>;
}
