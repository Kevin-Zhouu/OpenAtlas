ALTER TABLE jobs ADD COLUMN stage TEXT NOT NULL DEFAULT 'queued';
CREATE TABLE planning_attempts (id TEXT PRIMARY KEY, job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id), inputs TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, finished_at TEXT, output TEXT, error TEXT);
CREATE TABLE prompt_revisions (id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES planning_attempts(id), parent_id TEXT REFERENCES prompt_revisions(id), content TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX prompt_attempt ON prompt_revisions(attempt_id);
UPDATE jobs SET stage=CASE status WHEN 'succeeded' THEN 'completed' WHEN 'failed' THEN 'failed' ELSE stage END;
