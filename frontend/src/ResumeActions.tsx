import { useState } from 'react';

export type ResumeStage = 'planning' | 'building' | 'validating' | 'publishing';
export const stageNames: Record<ResumeStage, string> = {
  planning: 'planning', building: 'implementation', validating: 'validation', publishing: 'publishing',
};
export const resumeLabels: Record<ResumeStage, string> = {
  planning: 'Resume planning', building: 'Resume implementation',
  validating: 'Resume validation', publishing: 'Resume publishing',
};
export function ResumeActions({ stages, onResume }: {
  stages: ResumeStage[]; onResume: (stage: ResumeStage) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function resume(stage: ResumeStage) {
    setBusy(true); setError('');
    try { await onResume(stage); }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not resume this stage.'); }
    finally { setBusy(false); }
  }
  return <>
    <div className="job-retry-actions">
      {stages.map(stage => <button key={stage} className="quiet" disabled={busy}
        onClick={() => void resume(stage)}>{resumeLabels[stage]}</button>)}
      {busy && <span role="status">Queueing…</span>}
    </div>
    {stages.includes('validating') && <p className="hint">Validation uses the saved build and required review. It does not run implementation or automatic repairs. AI review may use credits.</p>}
    {error && <p role="alert">{error}</p>}
  </>;
}
