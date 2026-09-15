"""Application-specific persistence boundary. SQL stays here, not in generation logic."""

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError

from . import config


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return str(uuid.uuid4())


class Repository:
    def __init__(self, data=None):
        self.data = Path(data or config.DATA)
        self.data.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            "sqlite:///" + str(self.data / "openatlas.sqlite3"),
            connect_args={"timeout": 30},
        )

        @event.listens_for(self.engine, "connect")
        def configure_connection(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA secure_delete=ON")

        with self.engine.connect() as c:
            # SQLite's journal-mode transition can return SQLITE_BUSY immediately
            # while another process initializes the same new library.
            for attempt in range(100):
                try:
                    c.exec_driver_sql("PRAGMA journal_mode=WAL")
                    break
                except OperationalError as error:
                    if "locked" not in str(error).lower() or attempt == 99:
                        raise
                    time.sleep(0.05)
            c.exec_driver_sql("BEGIN IMMEDIATE")
            c.exec_driver_sql(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY)"
            )
            for p in sorted((Path(__file__).parent / "migrations").glob("*.sql")):
                if not c.execute(
                    text("SELECT version FROM schema_migrations WHERE version=:v"),
                    {"v": p.name},
                ).first():
                    for statement in p.read_text().split(";"):
                        if statement.strip():
                            c.exec_driver_sql(statement)
                    c.execute(
                        text("INSERT INTO schema_migrations VALUES (:v)"), {"v": p.name}
                    )

            c.commit()

    def rows(self, query, **args):
        with self.engine.connect() as c:
            return [dict(r) for r in c.execute(text(query), args).mappings()]

    def request_deletion(self, notebook_id):
        with self.engine.connect() as c:
            c.exec_driver_sql("BEGIN IMMEDIATE")
            ids = list(
                c.execute(
                    text("SELECT id FROM jobs WHERE notebook_id=:id"),
                    {"id": notebook_id},
                ).scalars()
            )
            if (
                not ids
                and not c.execute(
                    text("SELECT 1 FROM notebooks WHERE id=:id"), {"id": notebook_id}
                ).first()
            ):
                raise ValueError("Notebook not found")
            c.execute(
                text("INSERT OR IGNORE INTO deletion_requests VALUES (:id,:jobs,:t)"),
                {"id": notebook_id, "jobs": json.dumps(ids), "t": now()},
            )
            c.execute(
                text(
                    "UPDATE jobs SET status='deleting',progress='Permanently deleting Notebook and history' WHERE notebook_id=:id"
                ),
                {"id": notebook_id},
            )
            c.commit()
        return {"notebook_id": notebook_id, "status": "deleting"}

    def deleting(self, notebook_id):
        return bool(
            self.rows(
                "SELECT 1 FROM deletion_requests WHERE notebook_id=:id", id=notebook_id
            )
        )

    def list_jobs(self):
        return [
            self.job(row["id"])
            for row in self.rows(
                "SELECT id FROM jobs WHERE status != 'deleting' ORDER BY created_at DESC LIMIT 100"
            )
        ]

    def has_version(self, notebook_id, version_id):
        return bool(
            self.rows(
                "SELECT id FROM versions WHERE id=:v AND notebook_id=:n",
                v=version_id,
                n=notebook_id,
            )
        )

    def settings(self):
        from .models import DEFAULT_MODEL
        from .planning import current_planner_instructions

        saved = json.loads(
            self.rows("SELECT value FROM settings WHERE id=1")[0]["value"]
        )
        return {
            "generation_timeout_minutes": max(
                1, min(1440, (config.TIMEOUT + 59) // 60)
            ),
            "inference_auth": "api_key",
            "planner_model": DEFAULT_MODEL,
            **saved,
            "planner_instructions": current_planner_instructions(
                saved.get("planner_instructions")
            ),
        }

    def save_settings(self, settings):
        with self.engine.begin() as c:
            c.execute(
                text("UPDATE settings SET value=:v WHERE id=1"),
                {"v": json.dumps(settings)},
            )

    def enqueue(self, request, notebook_id=None, retry_of=None):
        job, stamp = uid(), now()
        notebook_id = notebook_id or uid()
        with self.engine.begin() as c:
            c.exec_driver_sql("BEGIN IMMEDIATE")
            if c.execute(
                text("SELECT 1 FROM deletion_requests WHERE notebook_id=:id"),
                {"id": notebook_id},
            ).first():
                raise ValueError("This Notebook is being permanently deleted")
            if retry_of:
                existing = c.execute(
                    text(
                        "SELECT id FROM jobs WHERE status IN ('queued','running') AND json_extract(request, '$.retry_of')=:id"
                    ),
                    {"id": retry_of},
                ).first()
                if existing:
                    raise ValueError(
                        "An attempt for this failed job is already queued or running"
                    )
            c.execute(
                text(
                    "INSERT OR IGNORE INTO notebooks(id,title,created_at) VALUES (:id,:title,:stamp)"
                ),
                {"id": notebook_id, "title": request["prompt"][:100], "stamp": stamp},
            )
            c.execute(
                text(
                    "INSERT INTO jobs(id,notebook_id,status,progress,request,created_at,updated_at) VALUES (:id,:n,'queued','Waiting for a generation slot',:r,:t,:t)"
                ),
                {"id": job, "n": notebook_id, "r": json.dumps(request), "t": stamp},
            )
        return self.job(job)

    def job(self, job_id):
        rows = self.rows("SELECT * FROM jobs WHERE id=:id", id=job_id)
        if not rows:
            return None
        j = rows[0]
        j["request"] = json.loads(j["request"])
        return j

    def steering(self, job_id):
        return self.rows(
            "SELECT * FROM steering_messages WHERE job_id=:id ORDER BY rowid", id=job_id
        )

    def queue_steering(self, job_id, message):
        message = message.strip()
        if not message or len(message) > 8000:
            raise ValueError("Enter a message of 1–8000 characters")
        with self.engine.connect() as c:
            c.exec_driver_sql("BEGIN IMMEDIATE")
            job = (
                c.execute(
                    text("SELECT status,stage,request FROM jobs WHERE id=:id"),
                    {"id": job_id},
                )
                .mappings()
                .first()
            )
            if (
                not job
                or job["status"] != "running"
                or job["stage"] != "building"
                or json.loads(job["request"])["provider"] != "codex"
            ):
                raise ValueError(
                    "Messages can only be sent while Codex is implementing"
                )
            if (
                c.execute(
                    text("SELECT count(*) FROM steering_messages WHERE job_id=:id"),
                    {"id": job_id},
                ).scalar()
                >= 100
            ):
                raise ValueError("This attempt has reached its 100-message limit")
            c.execute(
                text(
                    "INSERT INTO steering_messages VALUES (:id,:job,:message,'queued',:t)"
                ),
                {"id": uid(), "job": job_id, "message": message, "t": now()},
            )
            c.commit()
        return self.steering(job_id)

    def take_steering_or_validate(self, job_id):
        # Serialize accepting messages against closing the implementation stage.
        with self.engine.connect() as c:
            c.exec_driver_sql("BEGIN IMMEDIATE")
            job = c.execute(
                text("SELECT status FROM jobs WHERE id=:id"), {"id": job_id}
            ).scalar()
            if job != "running":
                raise ValueError("Generation stopped; saved draft retained")
            rows = list(
                c.execute(
                    text(
                        "SELECT * FROM steering_messages WHERE job_id=:id AND status='queued' ORDER BY rowid"
                    ),
                    {"id": job_id},
                ).mappings()
            )
            if rows:
                c.execute(
                    text(
                        "UPDATE steering_messages SET status='applying' WHERE job_id=:id AND status='queued'"
                    ),
                    {"id": job_id},
                )
            else:
                c.execute(
                    text("UPDATE jobs SET stage='validating' WHERE id=:id"),
                    {"id": job_id},
                )
            c.commit()
        return [dict(row) for row in rows]

    def save_steering_instructions(self, job_id, message):
        with self.engine.begin() as c:
            c.execute(
                text(
                    "UPDATE jobs SET request=json_set(request, '$.steering_message', :message) WHERE id=:id"
                ),
                {"id": job_id, "message": message},
            )

    def finish_steering(self, job_id, status):
        with self.engine.begin() as c:
            c.execute(
                text(
                    "UPDATE steering_messages SET status=:s WHERE job_id=:id AND status='applying'"
                ),
                {"id": job_id, "s": status},
            )

    def skip_validation(self, job_id):
        with self.engine.begin() as c:
            result = c.execute(
                text(
                    "UPDATE jobs SET stopped_stage=stage,status='failed',progress='Draft preview ready',error='Validation skipped by user; draft retained for preview and Continue.',updated_at=:t WHERE id=:id AND status='running' AND stage='validating'"
                ),
                {"id": job_id, "t": now()},
            )
            if not result.rowcount:
                raise ValueError("Validation is no longer running")

    def require_experience_review(self, job_id):
        """Persist the publication policy so recovery cannot downgrade a new run."""
        with self.engine.begin() as c:
            c.execute(
                text(
                    "UPDATE jobs SET request=json_set(request, '$.experience_review_required', json('true')) WHERE id=:id"
                ),
                {"id": job_id},
            )

    def save_experience_review(self, job_id, state):
        """Server-owned findings persist across repair and checkpoint continuation."""
        with self.engine.begin() as c:
            c.execute(
                text(
                    "UPDATE jobs SET request=json_set(request, '$.experience_review_state', json(:state)) WHERE id=:id"
                ),
                {"id": job_id, "state": json.dumps(state)},
            )

    def claim(self, concurrency):
        with self.engine.connect() as c:
            c.exec_driver_sql("BEGIN IMMEDIATE")
            c.execute(
                text(
                    "UPDATE jobs SET stopped_stage=stage,status='failed',stage='failed',progress='Runner interrupted',error='Generation lease expired; submit a revision or try again.',updated_at=:t WHERE status='running' AND lease_until<:s"
                ),
                {"t": now(), "s": time.time()},
            )
            c.execute(
                text(
                    "UPDATE planning_attempts SET status='failed',error='Runner interrupted; retry planning',finished_at=:t WHERE status='running' AND job_id IN (SELECT id FROM jobs WHERE status='failed')"
                ),
                {"t": now()},
            )
            count = c.execute(
                text("SELECT count(*) FROM jobs WHERE status='running'")
            ).scalar()
            row = (
                c.execute(
                    text(
                        "SELECT id FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1"
                    )
                ).first()
                if count < concurrency
                else None
            )
            if row:
                c.execute(
                    text(
                        "UPDATE jobs SET status='running',progress='Preparing the Notebook workspace',lease_until=:l,updated_at=:t WHERE id=:id"
                    ),
                    {"l": time.time() + 60, "t": now(), "id": row[0]},
                )
            c.commit()
        return self.job(row[0]) if row else None

    def progress(self, job_id, message=None):
        with self.engine.begin() as c:
            if message:
                c.execute(
                    text(
                        "INSERT INTO job_events(job_id,stage,message,created_at) SELECT id,stage,:m,:t FROM jobs WHERE id=:id AND status='running'"
                    ),
                    {"id": job_id, "m": message, "t": now()},
                )
            c.execute(
                text(
                    "UPDATE jobs SET progress=COALESCE(:p,progress),updated_at=:t,lease_until=:l WHERE id=:id AND status='running'"
                ),
                {"p": message, "t": now(), "l": time.time() + 60, "id": job_id},
            )

    def fail(self, job_id, error):
        with self.engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO job_events(job_id,stage,message,created_at) SELECT id,stage,:m,:t FROM jobs WHERE id=:id AND status='running'"
                ),
                {"id": job_id, "m": error[:2000], "t": now()},
            )
            c.execute(
                text(
                    "UPDATE jobs SET stopped_stage=stage,status='failed',stage='failed',progress='Generation failed',error=:e,updated_at=:t WHERE id=:id AND status='running'"
                ),
                {"e": error[:2000], "t": now(), "id": job_id},
            )

            c.execute(
                text(
                    "UPDATE planning_attempts SET status='failed',error=:e,finished_at=:t WHERE job_id=:id AND status='running'"
                ),
                {"e": error[:2000], "t": now(), "id": job_id},
            )

    def publish(self, job, version, manifest):
        with self.engine.begin() as c:
            if (
                c.execute(
                    text("SELECT status FROM jobs WHERE id=:id"), {"id": job["id"]}
                ).scalar()
                != "running"
            ):
                raise ValueError("Job no longer owns its generation lease")
            c.execute(
                text("INSERT INTO versions VALUES (:id,:n,:t,:m,:p,:provider,:j)"),
                {
                    "id": version,
                    "n": job["notebook_id"],
                    "t": now(),
                    "m": json.dumps(manifest),
                    "p": json.dumps(job["request"]["skills"]),
                    "provider": job["request"]["provider"],
                    "j": job["id"],
                },
            )
            c.execute(
                text(
                    "UPDATE notebooks SET latest_version=:v,title=:title WHERE id=:id"
                ),
                {"v": version, "title": manifest["title"], "id": job["notebook_id"]},
            )
            c.execute(
                text(
                    "INSERT INTO job_events(job_id,stage,message,created_at) VALUES (:id,'publishing',:m,:t)"
                ),
                {
                    "id": job["id"],
                    "m": "Published Notebook version " + version,
                    "t": now(),
                },
            )
            c.execute(
                text(
                    "UPDATE jobs SET status='succeeded',stage='completed',progress='Ready to explore',version_id=:v,updated_at=:t WHERE id=:id"
                ),
                {"v": version, "t": now(), "id": job["id"]},
            )

    def library(self):
        return self.rows(
            "SELECT n.*, v.provider FROM notebooks n JOIN versions v ON v.id=n.latest_version WHERE NOT EXISTS (SELECT 1 FROM deletion_requests d WHERE d.notebook_id=n.id) ORDER BY n.created_at DESC"
        )

    def notebook(self, notebook_id):
        rows = self.rows("SELECT * FROM notebooks WHERE id=:id", id=notebook_id)
        if not rows:
            return None
        n = rows[0]
        n["versions"] = self.rows(
            "SELECT * FROM versions WHERE notebook_id=:id ORDER BY created_at DESC",
            id=notebook_id,
        )
        for v in n["versions"]:
            v["manifest"] = json.loads(v["manifest"])
            v["provenance"] = json.loads(v["provenance"])
        return n

    def stage(self, job_id, stage):
        with self.engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO job_events(job_id,stage,message,created_at) SELECT id,:s,:m,:t FROM jobs WHERE id=:id AND status='running' AND stage != :s"
                ),
                {"id": job_id, "s": stage, "m": "Started " + stage, "t": now()},
            )
            c.execute(
                text("UPDATE jobs SET stage=:s WHERE id=:id AND status='running'"),
                {"s": stage, "id": job_id},
            )

    def start_plan(self, job_id, request):
        attempt = uid()
        with self.engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO planning_attempts(id,job_id,inputs,status,created_at) VALUES (:id,:j,:i,'running',:t)"
                ),
                {"id": attempt, "j": job_id, "i": json.dumps(request), "t": now()},
            )
        return attempt

    def plan_records(self, notebook_id):
        attempts = self.rows(
            "SELECT p.* FROM planning_attempts p JOIN jobs j ON j.id=p.job_id WHERE j.notebook_id=:n ORDER BY p.created_at",
            n=notebook_id,
        )
        for a in attempts:
            a["inputs"] = json.loads(a["inputs"])
            a["revisions"] = self.rows(
                "SELECT * FROM prompt_revisions WHERE attempt_id=:id ORDER BY created_at",
                id=a["id"],
            )
        return attempts

    def prompt_revision(self, revision_id):
        rows = self.rows("SELECT * FROM prompt_revisions WHERE id=:id", id=revision_id)
        return rows[0] if rows else None

    def save_prompt(self, attempt, content, parent=None):
        from .planning import validate_prompt

        content = validate_prompt(content)
        revision = uid()
        with self.engine.begin() as c:
            c.execute(
                text("INSERT INTO prompt_revisions VALUES (:id,:a,:p,:c,:t)"),
                {"id": revision, "a": attempt, "p": parent, "c": content, "t": now()},
            )
        return self.prompt_revision(revision)

    def finish_plan(self, job_id, attempt, content):
        from .planning import validate_prompt

        content = validate_prompt(content)
        revision = uid()
        with self.engine.begin() as c:
            c.exec_driver_sql("BEGIN IMMEDIATE")
            row = c.execute(
                text("SELECT request FROM jobs WHERE id=:id AND status='running'"),
                {"id": job_id},
            ).first()
            if not row:
                raise ValueError("Planning job no longer owns its lease")
            request = json.loads(row[0])
            request.update(
                build_prompt=content,
                planning_attempt_id=attempt,
                prompt_revision_id=revision,
            )
            c.execute(
                text("INSERT INTO prompt_revisions VALUES (:id,:a,NULL,:c,:t)"),
                {"id": revision, "a": attempt, "c": content, "t": now()},
            )
            c.execute(
                text(
                    "UPDATE planning_attempts SET status='succeeded',output=:o,finished_at=:t WHERE id=:id"
                ),
                {"o": content, "t": now(), "id": attempt},
            )
            c.execute(
                text("UPDATE jobs SET request=:r WHERE id=:id"),
                {"r": json.dumps(request), "id": job_id},
            )
        return request

    def complete_prompt(self, job_id):
        with self.engine.begin() as c:
            c.execute(
                text(
                    "UPDATE jobs SET status='succeeded',stage='completed',progress='Prompt ready to inspect and build',updated_at=:t WHERE id=:id AND status='running'"
                ),
                {"t": now(), "id": job_id},
            )

    def cancel(self, job_id):
        with self.engine.begin() as c:
            c.execute(
                text(
                    "UPDATE jobs SET stopped_stage=stage,status='failed',stage='failed',progress='Cancelled',error='Cancelled by user; saved prompts can be reused',updated_at=:t WHERE id=:id AND status IN ('queued','running')"
                ),
                {"t": now(), "id": job_id},
            )
            c.execute(
                text(
                    "UPDATE planning_attempts SET status='failed',error='Cancelled by user',finished_at=:t WHERE job_id=:id AND status='running'"
                ),
                {"t": now(), "id": job_id},
            )
