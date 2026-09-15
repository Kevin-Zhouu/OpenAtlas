import { useEffect, useState } from "react";

type Status = {
  status: "signed_out" | "pending" | "waiting" | "signed_in" | "error";
  runner_available: boolean;
  user_code?: string;
  verification_url?: string;
  email?: string;
  plan?: string;
  message?: string;
};

export function ChatGPTSubscription() {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const response = await fetch("/api/subscription");
        if (!response.ok) throw new Error("Could not check ChatGPT sign-in.");
        const result = await response.json();
        if (active) { setStatus(result); setError(""); }
      } catch (e) {
        if (active) setError(e instanceof Error ? e.message : "Could not check sign-in.");
      }
    };
    void refresh();
    const timer = window.setInterval(refresh, 2000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  async function action(signIn: boolean) {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(signIn ? "/api/subscription/login" : "/api/subscription", {
        method: signIn ? "POST" : "DELETE",
      });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Could not update ChatGPT sign-in.");
      setStatus(result);
    } catch (e) { setError(e instanceof Error ? e.message : "Could not update sign-in."); }
    finally { setBusy(false); }
  }

  const waiting = status?.status === "pending" || status?.status === "waiting";
  return <fieldset className="inference-profiles" disabled={busy}>
    <legend>ChatGPT subscription</legend>
    {error && <p role="alert">{error}</p>}
    <div role="status" aria-live="polite">
      {!status ? <p>Checking sign-in…</p> : status.status === "signed_in" ? <>
        <p>Signed in{status.email ? ` as ${status.email}` : " with ChatGPT"}{status.plan && status.plan !== "unknown" ? ` · ${status.plan}` : ""}</p>
        <button type="button" className="quiet" onClick={() => action(false)}>Sign out of ChatGPT</button>
      </> : waiting ? <>
        <p>{status.status === "pending" ? "Starting secure sign-in…" : "Complete sign-in on OpenAI’s website."}</p>
        {status.user_code && status.verification_url === "https://auth.openai.com/codex/device" && <>
          <p>Enter this one-time code: <strong className="device-code">{status.user_code}</strong></p>
          <a className="subscription-signin" href={status.verification_url} target="_blank" rel="noopener noreferrer">Open OpenAI sign-in ↗</a>
          <p className="hint">Keep this window open. It updates automatically after sign-in. If prompted, enable device-code login in your ChatGPT security settings.</p>
        </>}
        <button type="button" className="quiet" onClick={() => action(false)}>Cancel sign-in</button>
      </> : <>
        <p>{status.message || "Sign in to use your ChatGPT plan’s Codex allowance."}</p>
        <button type="button" className="quiet" disabled={!status.runner_available} onClick={() => action(true)}>Sign in with ChatGPT</button>
      </>}
      {status && !status.runner_available && <p className="hint">The OpenAtlas runner is unavailable. Start it to sign in or generate.</p>}
    </div>
    <p className="hint">Planning and generation use the signed-in account’s Codex allowance. Subscription jobs run one at a time. Your saved API profiles stay available when you switch back.</p>
    <p className="hint">This login is shared by users of this OpenAtlas library. Signing out also stops active subscription jobs. Save settings to select this mode.</p>
  </fieldset>;
}
