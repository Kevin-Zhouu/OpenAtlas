"""Trusted polling worker. Run one process; concurrency is also enforced transactionally."""

import logging
import signal
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .artifacts import ArtifactStore, validate
from .credentials import Credentials
from .debug import DebugStore, observe
from .demo import generate
from .execution import DockerExecutor
from .repository import Repository, uid
from .skills import SkillCatalog

log = logging.getLogger("openatlas.runner")


class Runner:
    def __init__(self, repo=None, store=None, catalog=None, executor=None):
        self.repo = repo or Repository()
        self.store = store or ArtifactStore(self.repo.data)
        self.catalog = catalog or SkillCatalog()
        self.executor = executor or DockerExecutor(
            Credentials(self.repo.data), debug=DebugStore(self.repo.data)
        )
        self.stop = threading.Event()

    def process(self, job):
        done = threading.Event()

        def heartbeat():
            while not done.wait(10):
                self.repo.progress(job["id"])

        heart = threading.Thread(target=heartbeat, daemon=True)
        heart.start()
        try:
            with tempfile.TemporaryDirectory(prefix="openatlas-") as tmp:
                workspace = Path(tmp)
                (workspace / "source").mkdir()
                (workspace / "dist").mkdir()
                request = dict(job["request"], job_id=job["id"])
                recovery = request.get("revalidate_job")
                if not recovery:
                    self.catalog.stage(request["skills"], workspace / "skills")
                if request.get("base_version"):
                    self.store.seed(
                        job["notebook_id"], request["base_version"], workspace
                    )

                def progress(message):
                    self.repo.progress(job["id"], message)

                if recovery:
                    progress(
                        "Rechecking retained Notebook with the current browser validator"
                    )
                    self.store.seed_recovery(recovery, workspace)
                elif request["provider"] == "demo":
                    generate(workspace, request, progress)
                else:
                    self.executor.run(workspace, request, progress)
                for attempt in range(2):
                    progress("Checking the Notebook in a sandboxed browser")
                    try:
                        manifest = validate(workspace)
                        break
                    except Exception as validation_error:
                        self.store.quarantine(
                            job["id"], attempt, workspace, validation_error
                        )
                        if recovery or request["provider"] != "codex" or attempt == 1:
                            raise
                        request["validation_feedback"] = str(validation_error)[:4000]
                        progress(
                            "Repairing issues found by the Notebook browser checks"
                        )
                        self.executor.run(workspace, request, progress)
                manifest["demo"] = request["provider"] == "demo"
                manifest["target_reading_minutes"] = request.get("reading_minutes", 20)
                version = uid()
                progress("Saving the Notebook to your local library")
                self.store.save(
                    job["notebook_id"], version, workspace, manifest, request["skills"]
                )
                self.repo.publish(job, version, manifest)
        except Exception as e:
            # Do not persist arbitrary provider output or Docker arguments containing secrets.
            message = (
                str(e)
                if isinstance(e, (ValueError, FileNotFoundError))
                else type(e).__name__
                + ": generation or browser validation failed; inspect local prerequisites."
            )
            self.repo.fail(job["id"], message)
            log.warning("Job %s failed (%s)", job["id"], type(e).__name__)
        finally:
            done.set()
            heart.join()

    def cleanup_expired(self):
        try:
            import docker

            client = docker.from_env()
            for c in client.containers.list(
                all=True, filters={"label": "openatlas.expires"}
            ):
                job = self.repo.job(c.labels.get("openatlas.job", ""))
                if float(c.labels["openatlas.expires"]) < time.time() or (
                    job and job["status"] in ("failed", "succeeded")
                ):
                    c.remove(force=True)
            client.close()
        except Exception:
            pass

    def run(self):
        threading.Thread(
            target=observe, args=(self.repo.data, self.stop), daemon=True
        ).start()
        last_cleanup = 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = set()
            while not self.stop.is_set():
                futures = {f for f in futures if not f.done()}
                concurrency = self.repo.settings()["concurrency"]
                if len(futures) < concurrency:
                    job = self.repo.claim(concurrency)
                    if job:
                        futures.add(pool.submit(self.process, job))
                        continue
                if time.monotonic() - last_cleanup > 60:
                    self.cleanup_expired()
                    last_cleanup = time.monotonic()
                self.stop.wait(0.5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    runner = Runner()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: runner.stop.set())
    runner.run()
