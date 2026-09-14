CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
INSERT OR IGNORE INTO settings VALUES (1, '{"provider":"demo","concurrency":2,"model":"gpt-5.3-codex"}');
CREATE TABLE IF NOT EXISTS notebooks (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL DEFAULT 'local', title TEXT NOT NULL, created_at TEXT NOT NULL, latest_version TEXT);
CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL DEFAULT 'local', notebook_id TEXT NOT NULL REFERENCES notebooks(id), status TEXT NOT NULL, progress TEXT NOT NULL, request TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, lease_until REAL, error TEXT, version_id TEXT);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status, created_at);
CREATE TABLE IF NOT EXISTS versions (id TEXT PRIMARY KEY, notebook_id TEXT NOT NULL REFERENCES notebooks(id), created_at TEXT NOT NULL, manifest TEXT NOT NULL, provenance TEXT NOT NULL, provider TEXT NOT NULL, job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id));
