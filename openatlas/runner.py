"""Trusted polling worker. Run one process; concurrency is also enforced transactionally."""

import json
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
from .quality import ReviewRequiresRepair, ReviewUnavailable, artifact_fingerprint
from .references import stage_references
from .repository import Repository, uid
from .skills import SkillCatalog
from .subscription import SubscriptionStore, SubscriptionWorker
from .validation_report import current_report, recording

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
        self.subscription = SubscriptionStore(self.repo.data)
        self.subscription_lock = threading.Lock()
        for execution in (self.executor, self.planner):
            if isinstance(execution, DockerExecutor):
                execution.cancelled = lambda request: (
                    self.stop.is_set()
                    or self.repo.job(request["job_id"])["status"] != "running"
                )

    def process(self, job):
        done = threading.Event()
        connection = None
        subscription_locked = False

        def run_agent(executor, workspace, request, progress):
            # Pin one key/URL pair for planning, building and repairs. A Settings
            # change affects the next job, never an already-started job.
            nonlocal connection, subscription_locked
            if isinstance(executor, DockerExecutor):
                if connection is None:
                    if request.get("inference_auth") == "chatgpt":
                        progress("Waiting for the subscription session")
                        while not self.subscription_lock.acquire(timeout=1):
                            if (
                                self.stop.is_set()
                                or self.repo.job(job["id"])["status"] != "running"
                            ):
                                raise ValueError(
                                    "Generation cancelled while waiting for the subscription session"
                                )
                        subscription_locked = True
                        connection = self.subscription.session()
                    else:
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
                if recovery:
                    original = self.repo.job(recovery)
                    if request.get("experience_review_required") or (
                        original
                        and original["request"].get("experience_review_required")
                    ):
                        raise ValueError(
                            "This Notebook requires independent experience review. Use Continue to complete the full publication checks."
                        )
                elif request["provider"] == "codex":
                    self.repo.require_experience_review(job["id"])
                    request["experience_review_required"] = True
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

                def remember_review(result):
                    if result and result.get("criteria"):
                        state = {
                            "criteria": result["criteria"],
                            "summary": result.get("summary", ""),
                        }
                        request["experience_review_state"] = state
                        self.repo.save_experience_review(job["id"], state)

                if recovery:
                    progress(
                        "Rechecking retained Notebook with the current browser validator"
                    )
                    self.store.seed_recovery(recovery, workspace)
                elif request["provider"] == "demo":
                    generate(workspace, request, progress)
                else:
                    run_agent(self.executor, workspace, request, progress)
                for attempt in range(3):
                    while True:
                        self.store.checkpoint(job["id"], workspace)
                        self.store.snapshot_preview(job["id"], workspace)
                        messages = self.repo.take_steering_or_validate(job["id"])
                        if not messages:
                            break
                        request["steering_message"] = "\n\n".join(
                            filter(
                                None,
                                [request.get("steering_message", "")]
                                + [m["message"] for m in messages],
                            )
                        )
                        self.repo.save_steering_instructions(
                            job["id"], request["steering_message"]
                        )
                        progress("Applying your follow-up instructions")
                        try:
                            run_agent(self.executor, workspace, request, progress)
                        except Exception:
                            self.repo.finish_steering(job["id"], "failed")
                            raise
                        self.repo.finish_steering(job["id"], "applied")
                    self.repo.stage(job["id"], "validating")
                    progress("Checking the Notebook in a sandboxed browser")
                    try:
                        with recording(
                            self.repo.data, job["id"], attempt
                        ) as validation:

                            def ensure_running():
                                if (
                                    self.stop.is_set()
                                    or self.repo.job(job["id"])["status"] != "running"
                                ):
                                    raise ValueError(
                                        "Validation stopped; draft retained for preview"
                                    )

                            validation.ensure_running = ensure_running
                            manifest = validate(workspace)
                            if request["provider"] == "codex" and not recovery:
                                report = current_report()
                                report.data.update(
                                    status="running", passed=False, finished_at=None
                                )
                                report.add(
                                    "experience",
                                    "Focused experience recheck"
                                    if request.get("experience_review_state")
                                    else "Independent experience review",
                                    "Recheck prior blockers and affected interactions, plus fresh overview, phone and normal-motion evidence."
                                    if request.get("experience_review_state")
                                    else "One consolidated audit against the original brief, separating evidenced blockers from optional suggestions.",
                                )
                                with report.check("experience"):
                                    progress(
                                        "Reviewing the learning experience, visuals and motion against your brief"
                                    )
                                    fingerprint = artifact_fingerprint(workspace)
                                    try:
                                        verdict = run_agent(
                                            self.executor,
                                            workspace,
                                            dict(request, execution_stage="reviewing"),
                                            progress,
                                        )
                                    except ReviewRequiresRepair as error:
                                        remember_review(error.result)
                                        raise
                                    except Exception as error:
                                        reason = (
                                            str(error)
                                            if isinstance(error, ValueError)
                                            else type(error).__name__
                                        )
                                        raise ReviewUnavailable(
                                            "Independent review unavailable; saved build retained. "
                                            + reason
                                        ) from error
                                    if (
                                        not isinstance(verdict, dict)
                                        or verdict.get("verdict") != "pass"
                                    ):
                                        raise ReviewUnavailable(
                                            "Independent experience review returned no valid pass"
                                        )
                                    if artifact_fingerprint(workspace) != fingerprint:
                                        raise ReviewUnavailable(
                                            "Artifact changed during review; refusing stale approval"
                                        )
                                    remember_review(verdict)
                                    manifest["experience_review"] = {
                                        "verdict": "pass",
                                        "summary": verdict.get("summary", ""),
                                        "artifact_sha256": fingerprint,
                                    }
                                    report.update(
                                        "experience",
                                        observed=verdict.get("summary", "Reviewed"),
                                    )
                            validation.finish()
                            (workspace / "validation.json").write_text(
                                json.dumps(validation.data)
                            )
                        break
                    except Exception as validation_error:
                        validation.finish(validation_error)
                        (workspace / "validation.json").write_text(
                            json.dumps(validation.data)
                        )
                        self.store.quarantine(
                            job["id"], attempt, workspace, validation_error
                        )
                        if (
                            self.repo.job(job["id"])["status"] != "running"
                            or self.stop.is_set()
                        ):
                            raise
                        if isinstance(validation_error, ReviewUnavailable):
                            self.store.checkpoint(job["id"], workspace)
                            raise
                        if recovery or request["provider"] != "codex" or attempt == 2:
                            raise
                        request["validation_feedback"] = (
                            str(validation_error)[:7000]
                            + "\nPreserve the original brief and primary interaction. Fix all reported blockers together without reducing motion quality, group coverage or visual clarity. Inspect source/EXPERIENCE.md and source/review/experience-review.json if present. Suggestions are optional. Test the reproductions and affected interactions, then a short overall regression sweep; avoid unrelated redesign or repeated dependency installation."
                        )
                        progress(
                            "Repairing issues found by the Notebook browser checks"
                        )
                        self.repo.stage(job["id"], "building")
                        run_agent(self.executor, workspace, request, progress)
                ensure_running()
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
            if isinstance(self.executor, DockerExecutor):
                self.executor.release(job["id"])
            done.set()
            heart.join()
            if subscription_locked:
                self.subscription_lock.release()

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
            target=SubscriptionWorker(self.subscription).run,
            args=(self.stop,),
            daemon=True,
        ).start()
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
