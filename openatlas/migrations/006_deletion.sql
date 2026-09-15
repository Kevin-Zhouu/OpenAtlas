CREATE TABLE deletion_requests (
 notebook_id TEXT PRIMARY KEY,
 job_ids TEXT NOT NULL,
 requested_at TEXT NOT NULL
);
