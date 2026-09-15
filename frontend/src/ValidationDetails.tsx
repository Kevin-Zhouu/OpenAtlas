export type ValidationRound = {
  round: number;
  status: string;
  legacy?: boolean;
  reason?: string;
  started_at?: string;
  finished_at?: string;
  checks: {
    id: string; title: string; status: string; expected: string; reason?: string;
    duration_ms?: number; before_text?: string; after_text?: string; observed?: string;
    diagnostics?: string[]; definition?: Record<string, unknown>;
  }[];
};
const statusName = (value: string) => ({ passed: 'Passed', failed: 'Failed', running: 'Running', not_run: 'Not run', interrupted: 'Interrupted' }[value] || value);
export function ValidationDetails({ rounds }: { rounds: ValidationRound[] }) {
  return <section className="validation-details" aria-label="Validation results">
    <h4>Validation rounds</h4>
    <p className="hint">Each round checks the packaged files, browser rendering, and interactions declared by the Notebook. These automated checks do not verify every interaction or factual claim. Repairs are followed by a new round.</p>
    {rounds.map(round => <article className="validation-round" key={round.round}>
      <header><h4>Round {round.round}</h4><span className={`validation-status validation-${round.status}`}>{statusName(round.status)}</span>
        {round.started_at && <time dateTime={round.started_at}>{new Date(round.started_at).toLocaleTimeString()}</time>}
      </header>
      {round.reason && (round.legacy || !round.checks.some(check => check.status === "failed")) && <p className="validation-reason">{round.reason}</p>}
      {round.legacy ? <p className="hint">This round ran before detailed reporting was available. Only its retained summary is shown.</p> : <>
        <p className="hint">{round.checks.filter(c => c.status === 'passed').length} passed · {round.checks.filter(c => c.status === 'failed').length} failed · {round.checks.filter(c => c.status === 'not_run').length} not run</p>
        {round.checks.map(check => <details className="validation-check" key={check.id} open={check.status === 'failed'}>
          <summary><span className={`validation-status validation-${check.status}`}>{statusName(check.status)}</span><strong>{check.title}</strong>
            {check.duration_ms !== undefined && <span className="hint">{(check.duration_ms / 1000).toFixed(2)} s</span>}
          </summary>
          <dl>
            <dt>Expected</dt><dd>{check.expected}</dd>
            {check.definition && Object.entries(check.definition).map(([key, value]) => <div className="validation-definition" key={key}><dt>{({selector:'Control selector', expect_selector:'Feedback selector', action:'Action', value:'Input value', expect_text:'Expected text'} as Record<string,string>)[key] || key}</dt><dd><code>{typeof value === 'string' ? value : JSON.stringify(value)}</code></dd></div>)}
            {check.observed && <><dt>Observed</dt><dd>{check.observed}</dd></>}
            {check.before_text !== undefined && <><dt>Text before action</dt><dd className="validation-evidence">{check.before_text || '(empty or not visible)'}</dd></>}
            {check.after_text !== undefined && <><dt>Text after action</dt><dd className="validation-evidence">{check.after_text || '(empty or not visible)'}</dd></>}
            <dt>Result</dt><dd className="validation-evidence">{check.reason || (check.status === 'not_run' ? (round.status === 'running' ? 'Waiting for earlier checks.' : 'Not reached because validation stopped before this check.') : check.status === 'running' ? 'Check is in progress.' : 'No additional evidence recorded.')}</dd>
            {!!check.diagnostics?.length && <><dt>Browser diagnostics</dt><dd className="validation-evidence">{check.diagnostics.join('\n')}</dd></>}
          </dl>
        </details>)}
      </>}
    </article>)}
  </section>;
}
