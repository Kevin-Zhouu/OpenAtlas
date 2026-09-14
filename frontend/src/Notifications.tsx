import { useEffect, useRef, useState } from "react";

type Job = {
  id: string;
  status: string;
  error?: string;
  created_at: string;
  request: { prompt: string; revalidate_job?: string };
};
type Notice = {
  id: string;
  title: string;
  message: string;
  date: string;
  jobId?: string;
};
const storageKey = "openatlas-notifications";
function stored(): string[] {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey) || "[]");
    return Array.isArray(value)
      ? value.filter((v) => typeof v === "string").slice(-500)
      : [];
  } catch {
    return [];
  }
}
export function Notifications({
  jobs,
  ready,
  error,
  onInspect,
}: {
  jobs: Job[];
  ready: boolean;
  error: string;
  onInspect: (id: string) => void;
}) {
  const [read, setRead] = useState(stored);
  const [errors, setErrors] = useState<Notice[]>([]);
  const [toast, setToast] = useState<Notice | null>(null);
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const known = useRef<Set<string> | null>(null);
  const lastError = useRef("");
  const recovered = new Set(
    jobs
      .filter((j) => j.status === "succeeded")
      .map((j) => j.request.revalidate_job),
  );
  const failures: Notice[] = jobs
    .filter((j) => j.status === "failed" && !recovered.has(j.id))
    .map((j) => ({
      id: j.id,
      jobId: j.id,
      title: "Notebook generation failed",
      message: j.error || "Open the job inspector for details.",
      date: j.created_at,
    }));
  const notices = [...failures, ...errors].sort((a, b) =>
    b.date.localeCompare(a.date),
  );
  const unread = notices.filter((n) => !read.includes(n.id)).length;
  function markRead(ids: string[]) {
    setRead((previous) => [...new Set([...previous, ...ids])].slice(-500));
  }
  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(read));
    } catch {
      /* Reading notifications still works without browser storage. */
    }
  }, [read]);
  useEffect(() => {
    if (!ready) return;
    const failed = jobs.filter((j) => j.status === "failed");
    if (known.current) {
      const fresh = failures
        .filter((n) => !known.current!.has(n.id))
        .sort((a, b) => b.date.localeCompare(a.date));
      if (fresh.length) setToast(fresh[0]);
    }
    known.current = new Set([
      ...(known.current || []),
      ...failed.map((j) => j.id),
    ]);
  }, [jobs, ready]);
  useEffect(() => {
    if (error && error !== lastError.current) {
      const notice = {
        id: "request:" + error,
        title: "Something went wrong",
        message: error,
        date: new Date().toISOString(),
      };
      setErrors((previous) =>
        [notice, ...previous.filter((n) => n.id !== notice.id)].slice(0, 20),
      );
      setRead((previous) => previous.filter((id) => id !== notice.id));
      setToast(notice);
    }
    lastError.current = error;
  }, [error]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 8000);
    return () => clearTimeout(timer);
  }, [toast]);
  useEffect(() => {
    if (!open) return;
    function outside(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    function escape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    }
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  function inspect(notice: Notice) {
    markRead([notice.id]);
    setToast(null);
    setOpen(false);
    if (notice.jobId) onInspect(notice.jobId);
    else setOpen(true);
  }
  return (
    <div className="notifications" ref={root}>
      <button
        ref={trigger}
        className="notification-trigger quiet"
        aria-label={
          unread ? `Notifications, ${unread} unread` : "Notifications"
        }
        aria-expanded={open}
        aria-controls="notification-inbox"
        onClick={() => setOpen(!open)}
      >
        <svg
          width="21"
          height="21"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          aria-hidden="true"
        >
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9ZM10 21h4" />
        </svg>
        {unread > 0 && (
          <span className="notification-count" aria-hidden="true">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>
      {open && (
        <section
          id="notification-inbox"
          className="notification-inbox"
          aria-label="Notifications"
        >
          <div className="notification-heading">
            <h2>Notifications</h2>
            <button
              className="quiet"
              aria-label="Close notifications"
              onClick={() => {
                setOpen(false);
                trigger.current?.focus();
              }}
            >
              ✕
            </button>
          </div>
          <div className="notification-subheading">
            <span>{unread ? `${unread} unread` : "You're all caught up"}</span>
            {unread > 0 && (
              <button
                className="quiet"
                onClick={() => markRead(notices.map((n) => n.id))}
              >
                Mark all as read
              </button>
            )}
          </div>
          {notices.length === 0 ? (
            <p className="notification-empty">
              All quiet here. Updates that need your attention will appear here.
            </p>
          ) : (
            <ul>
              {notices.map((n) => (
                <li key={n.id} className={read.includes(n.id) ? "" : "unread"}>
                  <div className="notification-item-heading">
                    <strong>{n.title}</strong>
                    <time>
                      {new Date(n.date).toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                      })}
                    </time>
                  </div>
                  {n.jobId && (
                    <p className="notification-topic">
                      {jobs.find((j) => j.id === n.jobId)?.request.prompt}
                    </p>
                  )}
                  <p className="notification-message">{n.message}</p>
                  <div className="notification-actions">
                    {n.jobId && (
                      <button className="quiet" onClick={() => inspect(n)}>
                        Inspect job ↗
                      </button>
                    )}
                    {!read.includes(n.id) && (
                      <button
                        className="quiet"
                        onClick={() => markRead([n.id])}
                      >
                        Mark as read
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
          <p className="notification-footer">
            Full generation history is always available in Jobs.
          </p>
        </section>
      )}
      {toast && (
        <aside className="notification-toast" role="alert">
          <span className="notification-warning" aria-hidden="true">
            !
          </span>
          <div>
            <strong>{toast.title}</strong>
            <p>{toast.message}</p>
            <button className="quiet" onClick={() => inspect(toast)}>
              {toast.jobId ? "Inspect job ↗" : "View notification"}
            </button>
          </div>
          <button
            className="quiet"
            aria-label="Dismiss notification"
            onClick={() => setToast(null)}
          >
            ✕
          </button>
        </aside>
      )}
    </div>
  );
}
