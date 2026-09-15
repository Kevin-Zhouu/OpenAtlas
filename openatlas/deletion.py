"""Permanent, runner-owned removal after all generation writers have drained."""

import json
import shutil
import sqlite3
from uuid import UUID

from .debug import DebugStore


def remove(path):
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)


def purge(repo, notebook_id, containers=None):
    """Caller must drain generation futures first. Retryable after interruption."""
    records = repo.rows(
        "SELECT * FROM deletion_requests WHERE notebook_id=:id", id=notebook_id
    )
    if not records:
        return
    job_ids = json.loads(records[0]["job_ids"])
    # The runner owns Docker. Failure to stop a container must not report success.
    if containers is not None:
        for job_id in job_ids:
            for container in containers.list(
                all=True, filters={"label": "openatlas.job=" + job_id}
            ):
                container.remove(force=True)
    debug = DebugStore(repo.data)
    with debug.lock:
        for job_id in job_ids:
            ident = str(UUID(job_id))
            for folder in ("checkpoints", "failed", "previews", "validation"):
                remove(repo.data / folder / ident)
                remove(repo.data / folder / (ident + ".staging"))
            for workspace in (repo.data / "workspaces").glob(ident + "-*"):
                remove(workspace)
            for temporary in (repo.data / "debug").glob(ident + "-*"):
                remove(temporary)
            remove(repo.data / "debug" / (ident + ".json"))
            remove(repo.data / "debug" / (ident + ".invocations.json"))
            remove(repo.data / "debug" / "traces" / ident)
        remove(repo.data / "library" / str(UUID(notebook_id)))
        # Wipe deleted record bytes, including prior WAL frames. The request holds
        # only random identifiers and remains until every cleanup step succeeds.
        with sqlite3.connect(repo.data / "openatlas.sqlite3", timeout=30) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA secure_delete=ON")
            connection.execute("BEGIN IMMEDIATE")
            ids = [
                r[0]
                for r in connection.execute(
                    "SELECT id FROM jobs WHERE notebook_id=?", (notebook_id,)
                )
            ]
            for ident in ids:
                connection.execute(
                    "DELETE FROM steering_messages WHERE job_id=?", (ident,)
                )
                connection.execute("DELETE FROM job_events WHERE job_id=?", (ident,))
            attempts = [
                r[0]
                for r in connection.execute(
                    "SELECT id FROM planning_attempts WHERE job_id IN (SELECT id FROM jobs WHERE notebook_id=?)",
                    (notebook_id,),
                )
            ]
            for attempt in attempts:
                connection.execute(
                    "UPDATE prompt_revisions SET parent_id=NULL WHERE attempt_id=?",
                    (attempt,),
                )
            for attempt in attempts:
                connection.execute(
                    "DELETE FROM prompt_revisions WHERE attempt_id=?", (attempt,)
                )
            connection.execute(
                "DELETE FROM planning_attempts WHERE job_id IN (SELECT id FROM jobs WHERE notebook_id=?)",
                (notebook_id,),
            )
            connection.execute(
                "DELETE FROM versions WHERE notebook_id=?", (notebook_id,)
            )
            connection.execute("DELETE FROM jobs WHERE notebook_id=?", (notebook_id,))
            connection.execute("DELETE FROM notebooks WHERE id=?", (notebook_id,))
            connection.commit()
            if connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]:
                raise ValueError("Deletion is waiting for database readers to finish")
            connection.execute("VACUUM")
            if connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]:
                raise ValueError("Deletion is waiting for database readers to finish")
            connection.execute(
                "DELETE FROM deletion_requests WHERE notebook_id=?", (notebook_id,)
            )
