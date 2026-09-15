CREATE TABLE steering_messages (
 id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
 message TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', created_at TEXT NOT NULL
);
CREATE INDEX steering_job ON steering_messages(job_id, created_at);
