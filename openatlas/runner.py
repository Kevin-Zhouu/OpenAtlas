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
from .planning import PlannerAdapter
from .references import stage_references
from .repository import Repository, uid
from .skills import SkillCatalog

log = logging.getLogger("openatlas.runner")


class Runner:
    def __init__(
        self, repo=None, store=None, catalog=None, executor=None, planner=None
    ):
        self.repo = repo or Repository()
        self.store = store or ArtifactStore(self.repo.data)
        self.catalog = catalog or SkillCatalog()
        self.executor = executor or DockerExecutor(
            Credentials(self.repo.data),
            debug=DebugStore(self.repo.data),
            checkpoint_store=self.store,
        )
        self.planner = planner or DockerExecutor(
            Credentials(self.repo.data),
            adapter=PlannerAdapter(),
            debug=DebugStore(self.repo.data),
        )
        self.stop = threading.Event()
        for execution in (self.executor, self.planner):
            if isinstance(execution, DockerExecutor):
                execution.cancelled = lambda request: (
                    self.stop.is_set()
                    or self.repo.job(request["job_id"])["status"] != "running"
                )

    def process(self, job):
        done = threading.Event()
        connection = None

        def run_agent(executor, workspace, request, progress):
            # Pin one key/URL pair for planning, building and repairs. A Settings
            # change affects the next job, never an already-started job.
            nonlocal connection
            if isinstance(executor, DockerExecutor):
                if connection is None:
                    connection = executor.credentials.connection()
                return executor.run(workspace, request, progress, connection=connection)
            return executor.run(workspace, request, progress)

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
                    request["golden_references"] = stage_references(workspace)
                    if request.get("skill_snapshots"):
                        self.catalog.stage_snapshots(
                            request["skills"],
                            self.repo.data / "skill-inputs",
                            workspace / "skills",
                        )
                    else:
                        self.catalog.stage(request["skills"], workspace / "skills")
                if (
                    request.get("planning_enabled")
                    and not recovery
                    and not request.get("build_prompt")
                ):
                    self.repo.stage(job["id"], "planning")
                    attempt = self.repo.start_plan(job["id"], request)
                    content = run_agent(
                        self.planner,
                        workspace,
                        dict(request, execution_stage="planning"),
                        lambda message: self.repo.progress(job["id"], message),
                    )
                    saved = self.repo.finish_plan(job["id"], attempt, content)
                    job["request"] = saved
                    request = dict(saved, job_id=job["id"])
                if request.get("prompt_only") and not recovery:
                    self.repo.complete_prompt(job["id"])
                    return
                self.repo.stage(job["id"], "building")
                if request.get("base_version"):
                    self.store.seed(
                        job["notebook_id"], request["base_version"], workspace
                    )

                if request.get("continue_job"):
                    self.store.seed_checkpoint(request["continue_job"], workspace)

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
                    run_agent(self.executor, workspace, request, progress)
                for attempt in range(2):
                    self.repo.stage(job["id"], "validating")
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
                        self.repo.stage(job["id"], "building")
                        run_agent(self.executor, workspace, request, progress)
                manifest["demo"] = request["provider"] == "demo"
                manifest["target_reading_minutes"] = request.get("reading_minutes", 20)
                manifest["planning_attempt_id"] = request.get("planning_attempt_id")
                manifest["prompt_revision_id"] = request.get("prompt_revision_id")
                version = uid()
                self.repo.stage(job["id"], "publishing")
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
            if self.repo.job(job["id"])["stage"] == "planning":
                message = "Planning failed: " + message
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
