"""Application-specific persistence boundary. SQL stays here, not in generation logic."""

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, event, text

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

        with self.engine.connect() as c:
            c.exec_driver_sql("PRAGMA journal_mode=WAL")
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

    def list_jobs(self):
        return [
            self.job(row["id"])
            for row in self.rows(
                "SELECT id FROM jobs ORDER BY created_at DESC LIMIT 100"
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
        return json.loads(
            self.rows("SELECT value FROM settings WHERE id=1")[0]["value"]
        )

    def save_settings(self, settings):
        with self.engine.begin() as c:
            c.execute(
                text("UPDATE settings SET value=:v WHERE id=1"),
                {"v": json.dumps(settings)},
            )

    def enqueue(self, request, notebook_id=None):
        job, stamp = uid(), now()
        notebook_id = notebook_id or uid()
        with self.engine.begin() as c:
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

    def claim(self, concurrency):
        with self.engine.connect() as c:
            c.exec_driver_sql("BEGIN IMMEDIATE")
            c.execute(
                text(
                    "UPDATE jobs SET status='failed',progress='Runner interrupted',error='Generation lease expired; submit a revision or try again.',updated_at=:t WHERE status='running' AND lease_until<:s"
                ),
                {"t": now(), "s": time.time()},
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
                    "UPDATE jobs SET status='failed',progress='Generation failed',error=:e,updated_at=:t WHERE id=:id AND status='running'"
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
                    "UPDATE jobs SET status='succeeded',progress='Ready to explore',version_id=:v,updated_at=:t WHERE id=:id"
                ),
                {"v": version, "t": now(), "id": job["id"]},
            )

    def library(self):
        return self.rows(
            "SELECT n.*, v.provider FROM notebooks n JOIN versions v ON v.id=n.latest_version ORDER BY n.created_at DESC"
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
