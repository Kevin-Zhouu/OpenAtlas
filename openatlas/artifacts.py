"""Immutable filesystem library and browser validation. Never execute generated source."""

import html
import json
import mimetypes
import shutil
from pathlib import Path
from urllib.parse import unquote, urlparse

from playwright.sync_api import expect, sync_playwright

from . import config

# Functional checks also run with software-rendered WebGL in Docker. This is an
# action-completion budget, not a frame-rate or visual-quality acceptance test.
INTERACTION_TIMEOUT_MS = 15_000

TEXT_ATTACHMENTS = {
    ".cs",
    ".csproj",
    ".sln",
    ".sh",
    ".md",
    ".py",
    ".go",
    ".rs",
    ".java",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".ts",
    ".tsx",
    ".jsx",
    ".sql",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
}


def artifact_media_type(path):
    return (
        "text/plain; charset=utf-8"
        if path.suffix.lower() in TEXT_ATTACHMENTS
        else (mimetypes.guess_type(str(path))[0] or "application/octet-stream")
    )


ALLOWED = {
    ".html",
    ".css",
    ".js",
    ".mjs",
    ".json",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".mp3",
    ".mp4",
    ".webm",
    ".ogg",
    ".glb",
    ".gltf",
    ".bin",
    ".wasm",
    ".txt",
}


def safe_tree(root, limit=100 * 1024 * 1024):
    total = 0
    for p in root.rglob("*"):
        if p.is_symlink() or not (p.is_file() or p.is_dir()):
            raise ValueError("Output contains a link or special file")
        if p.is_file():
            total += p.stat().st_size
            if total > limit:
                raise ValueError("Output exceeds size limit")
    return total


class ArtifactStore:
    def __init__(self, data=None):
        self.root = Path(data or config.DATA) / "library"
        self.root.mkdir(parents=True, exist_ok=True)

    def version_path(self, notebook, version):
        # IDs originate in the database, but also enforce containment here.
        path = (self.root / notebook / version).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError("Invalid library path")
        return path

    def save(self, notebook, version, workspace, manifest, provenance):
        target = self.version_path(notebook, version)
        if target.exists():
            raise ValueError("Immutable version already exists")
        staging = target.with_name(version + ".staging")
        try:
            staging.mkdir(parents=True)
            shutil.copytree(workspace / "source", staging / "source")
            shutil.copytree(workspace / "dist", staging / "artifact")
            (staging / "manifest.json").write_text(json.dumps(manifest, indent=2))
            (staging / "provenance.json").write_text(json.dumps(provenance, indent=2))
            shutil.copy(workspace / "validation.json", staging / "validation.json")
            for image in ("preview.png", "preview-mobile.png"):
                if (workspace / image).exists():
                    shutil.copy(workspace / image, staging / image)
            staging.rename(target)
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def quarantine(self, job_id, attempt, workspace, error):
        target = self.root.parent / "failed" / job_id / str(attempt)
        target.mkdir(parents=True, exist_ok=True)
        for name in ("source", "dist"):
            source = workspace / name
            safe_tree(source)
            shutil.copytree(source, target / name, dirs_exist_ok=True)
        if (workspace / "manifest.json").is_file():
            shutil.copy(workspace / "manifest.json", target / "manifest.json")
        (target / "error.txt").write_text(str(error)[:4000])

    def recovery_path(self, job_id):
        from uuid import UUID

        root = self.root.parent / "failed" / str(UUID(job_id))
        for attempt in ("1", "0"):
            candidate = root / attempt
            if (candidate / "manifest.json").is_file():
                return candidate
        return None

    def seed_recovery(self, job_id, workspace):
        retained = self.recovery_path(job_id)
        if retained is None:
            raise ValueError("No retained Notebook artifact is available to revalidate")
        safe_tree(retained)
        for name in ("source", "dist"):
            shutil.copytree(retained / name, workspace / name, dirs_exist_ok=True)
        shutil.copy(retained / "manifest.json", workspace / "manifest.json")

    def snapshot_preview(self, job_id, workspace):
        from uuid import UUID, uuid4

        dist = workspace / "dist"
        safe_tree(dist)
        if not dist.is_dir():
            return
        revision = str(uuid4())
        target = self.root.parent / "previews" / str(UUID(job_id)) / revision
        target.mkdir(parents=True)
        shutil.copytree(dist, target / "dist")
        entry = "index.html"
        try:
            entry = json.loads((workspace / "manifest.json").read_text()).get(
                "entrypoint", entry
            )
        except (OSError, ValueError):
            pass
        if not isinstance(entry, str) or not self.preview_file(job_id, revision, entry):
            entry = "index.html"
        (target.parent / "current.json.tmp").write_text(
            json.dumps({"revision": revision, "entrypoint": entry})
        )
        (target.parent / "current.json.tmp").replace(target.parent / "current.json")

    def preview_info(self, job_id):
        from uuid import UUID

        path = self.root.parent / "previews" / str(UUID(job_id)) / "current.json"
        return json.loads(path.read_text()) if path.is_file() else None

    def preview_file(self, job_id, revision, name):
        from uuid import UUID

        root = (
            self.root.parent
            / "previews"
            / str(UUID(job_id))
            / str(UUID(revision))
            / "dist"
        )
        path = (root / name).resolve()
        if (
            path.is_relative_to(root.resolve())
            and path.is_file()
            and path.suffix.lower() in ALLOWED
        ):
            return path
        return None

    def checkpoint_path(self, job_id):
        from uuid import UUID

        path = self.root.parent / "checkpoints" / str(UUID(job_id))
        return path if (path / "source").is_dir() else self.recovery_path(job_id)

    def checkpoint(self, job_id, workspace):
        from uuid import UUID

        target = self.root.parent / "checkpoints" / str(UUID(job_id))
        safe_tree(workspace)
        if not safe_tree(workspace / "source"):
            return False
        staging = target.with_name(target.name + ".staging")
        try:
            staging.mkdir(parents=True, exist_ok=True, mode=0o700)
            for name in ("source", "dist", "manifest.json"):
                source = workspace / name
                if source.is_dir():
                    shutil.copytree(source, staging / name, dirs_exist_ok=True)
                elif source.is_file():
                    shutil.copy(source, staging / name)
            if target.exists():
                shutil.rmtree(target)
            staging.rename(target)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return True

    def seed_checkpoint(self, job_id, workspace):
        retained = self.checkpoint_path(job_id)
        if retained is None:
            raise ValueError(
                "No saved workspace remains for this job. Use Re-run instead."
            )
        safe_tree(retained)
        for name in ("source", "dist", "manifest.json"):
            source = retained / name
            if source.is_dir():
                shutil.copytree(source, workspace / name, dirs_exist_ok=True)
            elif source.is_file():
                shutil.copy(source, workspace / name)

    def can_validate_checkpoint(self, job_id):
        path = self.checkpoint_path(job_id)
        if path is None:
            return False
        try:
            # Capability discovery only; the validator checks the full tree.
            manifest = json.loads((path / "manifest.json").read_text())
            entry = (path / "dist" / manifest.get("entrypoint", "index.html")).resolve()
            return (path / "source").is_dir() and entry.is_relative_to(
                (path / "dist").resolve()
            ) and entry.suffix == ".html" and entry.is_file()
        except (OSError, ValueError, TypeError, AttributeError):
            return False

    def retain_publication(self, job_id, workspace, manifest):
        """Trusted receipt, written only after all required validation succeeds."""
        from .quality import artifact_fingerprint

        self.checkpoint(job_id, workspace)
        path = self.checkpoint_path(job_id)
        for name in ("validation.json", "preview.png", "preview-mobile.png"):
            if (workspace / name).is_file():
                shutil.copy(workspace / name, path / name)
        receipt = {
            "fingerprint": artifact_fingerprint(path),
            "policy": config.ARTIFACT_CSP,
            "manifest": manifest,
        }
        temporary = path / "publication.json.tmp"
        temporary.write_text(json.dumps(receipt))
        temporary.replace(path / "publication.json")

    def publication_receipt(self, job_id):
        from .quality import artifact_fingerprint

        path = self.checkpoint_path(job_id)
        if path is None or not (path / "publication.json").is_file():
            return None
        try:
            safe_tree(path)
            receipt = json.loads((path / "publication.json").read_text())
            validation = json.loads((path / "validation.json").read_text())
            if (receipt["fingerprint"] == artifact_fingerprint(path)
                    and receipt["policy"] == config.ARTIFACT_CSP
                    and validation.get("passed") is True):
                return receipt
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def seed_publication(self, job_id, workspace):
        receipt = self.publication_receipt(job_id)
        if receipt is None:
            raise ValueError("Saved publication evidence is unavailable or changed. Resume validation instead.")
        self.seed_checkpoint(job_id, workspace)
        path = self.checkpoint_path(job_id)
        for name in ("validation.json", "preview.png", "preview-mobile.png"):
            if (path / name).is_file():
                shutil.copy(path / name, workspace / name)
        return receipt["manifest"]

    def seed(self, notebook, version, workspace):
        shutil.copytree(
            self.version_path(notebook, version) / "source",
            workspace / "source",
            dirs_exist_ok=True,
        )

    def artifact(self, notebook, version, name):
        root = self.version_path(notebook, version) / "artifact"
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            return None
        return path


def validate(workspace):
    from .validation_report import current_report

    report = current_report()
    for key, title, expected in [
        (
            "source",
            "Editable source",
            "Retained source files contain no links or special files and fit the size limit.",
        ),
        (
            "assets",
            "Packaged assets",
            "Static files use supported formats; source attachments are UTF-8 text.",
        ),
        (
            "manifest",
            "Notebook metadata",
            "A valid JSON manifest has a title of 1–150 characters.",
        ),
        (
            "entrypoint",
            "HTML entrypoint",
            "The manifest points to an existing HTML document inside dist/.",
        ),
        (
            "contract",
            "Interaction test definitions",
            "The manifest declares 1–30 interaction checks.",
        ),
        (
            "browser",
            "Browser startup",
            "Chromium can start with a sandboxed Notebook frame.",
        ),
        (
            "desktop",
            "Desktop rendering",
            "At 1280 × 900, the Notebook renders at least 150 characters of learning content.",
        ),
        (
            "desktop_capture",
            "Desktop preview",
            "The browser can capture the rendered desktop page.",
        ),
        (
            "mobile",
            "Phone layout",
            "At 390 × 844, content does not overflow horizontally by more than 2 pixels.",
        ),
        (
            "mobile_capture",
            "Phone preview",
            "The browser can capture the rendered phone page.",
        ),
        (
            "runtime",
            "Browser errors and resources",
            "No JavaScript or console errors, missing local files, or blocked external resource requests.",
        ),
    ]:
        report.add(key, title, expected)
    try:
        manifest = _validate(workspace, report)
    except Exception as error:
        report.finish(error)
        raise
    report.finish()
    (workspace / "validation.json").write_text(json.dumps(report.data))
    return manifest


def _validate(workspace, report):
    with report.check("source"):
        if not safe_tree(workspace / "source"):
            raise ValueError("Notebook requires retained editable source files")
    dist = workspace / "dist"
    with report.check("assets"):
        safe_tree(dist)
        for p in dist.rglob("*"):
            if p.is_file() and p.suffix.lower() not in ALLOWED | TEXT_ATTACHMENTS:
                raise ValueError(
                    "Unsupported static artifact file: "
                    + str(p.relative_to(dist))
                    + ". Keep compiled binaries and build dependencies in source only; dist may contain web assets and UTF-8 teaching source attachments."
                )
            if p.is_file() and p.suffix.lower() in TEXT_ATTACHMENTS:
                try:
                    content = p.read_text(encoding="utf-8")
                    if "\x00" in content:
                        raise ValueError(
                            "Source attachment contains binary data: " + p.name
                        )
                except UnicodeError:
                    raise ValueError("Source attachment must be UTF-8 text: " + p.name)
    with report.check("manifest"):
        manifest = json.loads((workspace / "manifest.json").read_text())
        if (
            not isinstance(manifest.get("title"), str)
            or not 1 <= len(manifest["title"]) <= 150
        ):
            raise ValueError("Manifest needs a title of 1–150 characters")
    with report.check("entrypoint"):
        entry = manifest.get("entrypoint", "index.html")
        entry_path = (dist / entry).resolve()
        if (
            not entry_path.is_relative_to(dist.resolve())
            or entry_path.suffix != ".html"
            or not entry_path.is_file()
        ):
            available = [str(p.relative_to(dist)) for p in dist.rglob("*.html")][:20]
            raise ValueError(
                f"Notebook requires a built HTML entrypoint relative to dist/. Manifest entrypoint: {entry!r}. Available HTML files: {available}"
            )
        if "<html" not in entry_path.read_text().lower():
            raise ValueError("Entrypoint is not an HTML document")
    with report.check("contract"):
        checks = manifest.get("checks", [])
        if not isinstance(checks, list) or not 1 <= len(checks) <= 30:
            raise ValueError("Declare 1–30 browser interaction checks in manifest.json")
    for index, check in enumerate(checks, 1):
        report.add(
            f"interaction-{index}",
            f"Interaction {index}",
            "Control is visible; the action produces the declared text or visibility transition.",
            definition=check,
            before="desktop_capture",
        )
    errors = []
    with sync_playwright() as p:
        with report.check("browser"):
            browser = p.chromium.launch()
            context = browser.new_context(
                viewport={"width": 1280, "height": 900}, service_workers="block"
            )
            page = context.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on(
            "console",
            lambda message: (
                errors.append(message.text) if message.type == "error" else None
            ),
        )

        def route_handler(route):
            url = urlparse(route.request.url)
            if url.netloc != "notebook.invalid":
                route.abort()
                errors.append("External resource blocked: " + url.netloc)
                return
            if url.path == "/reader":
                route.fulfill(
                    content_type="text/html",
                    body='<iframe title="Notebook" sandbox="allow-scripts" style="width:100%;height:95vh;border:0" src="/artifact/'
                    + html.escape(entry, quote=True)
                    + '"></iframe>',
                )
                return
            path = (dist / unquote(url.path.removeprefix("/artifact/"))).resolve()
            if (
                not url.path.startswith("/artifact/")
                or not path.is_relative_to(dist.resolve())
                or not path.is_file()
            ):
                errors.append("Missing local resource: " + url.path)
                route.fulfill(status=404, body="Not found")
                return
            route.fulfill(
                body=path.read_bytes(),
                content_type=artifact_media_type(path),
                headers={
                    "Content-Security-Policy": config.artifact_csp(
                        "http://notebook.invalid/artifact/"
                    ),
                    "Access-Control-Allow-Origin": "*",
                },
            )

        context.route("**/*", route_handler)
        try:
            with report.check("desktop"):
                page.goto("http://notebook.invalid/reader")
                frame = page.frame_locator("iframe")
                frame.locator("body").wait_for()
                rendered_characters = len(frame.locator("body").inner_text().strip())
                report.update(
                    "desktop", observed=f"{rendered_characters} rendered characters."
                )
                if rendered_characters < 150:
                    raise ValueError(
                        "Notebook has insufficient rendered learning content"
                    )
            for index, check in enumerate(checks, 1):
                with report.check(f"interaction-{index}"):
                    try:
                        target = frame.locator(check["selector"])
                        output = frame.locator(check["expect_selector"])
                        visibility = check.get("expect_visible")
                        if "expect_visible" in check and type(visibility) is not bool:
                            raise ValueError("expect_visible must be a boolean")
                        if visibility is False and "expect_text" in check:
                            raise ValueError(
                                "Hidden outcomes cannot require visible text"
                            )
                        expect(target).to_be_visible(timeout=INTERACTION_TIMEOUT_MS)
                        before_visible = output.is_visible()
                        before = output.inner_text() if before_visible else None
                        if (
                            visibility is not None
                            and "expect_text" not in check
                            and before_visible == visibility
                        ):
                            raise ValueError(
                                "Visibility check must observe a transition, not an already satisfied state"
                            )
                        report.update(
                            f"interaction-{index}",
                            before_text=(before or "")[:2000],
                            before_visible=before_visible,
                        )
                        action = check.get("action", "click")
                        if action == "click":
                            target.click(timeout=INTERACTION_TIMEOUT_MS)
                        elif action in ("fill", "select"):
                            tag = target.evaluate("el => el.tagName.toLowerCase()")
                            if tag == "select":
                                # Older manifests used fill because the original contract
                                # omitted dropdown selection. Keep those jobs recoverable.
                                target.select_option(
                                    value=str(check["value"]),
                                    timeout=INTERACTION_TIMEOUT_MS,
                                )
                            elif action == "select":
                                raise ValueError(
                                    "The select action requires a <select> control; use fill for text fields"
                                )
                            else:
                                target.fill(
                                    str(check["value"]), timeout=INTERACTION_TIMEOUT_MS
                                )
                        elif action == "range":
                            target.evaluate(
                                '(el, value) => { el.value=value; el.dispatchEvent(new Event("input",{bubbles:true})); el.dispatchEvent(new Event("change",{bubbles:true})); }',
                                str(check["value"]),
                            )
                        else:
                            raise ValueError("Unsupported interaction check action")
                        # Closing an overlay is a real observable outcome; it does not
                        # need a fabricated status-text change elsewhere on the page.
                        if visibility is False:
                            expect(output).to_be_hidden(timeout=INTERACTION_TIMEOUT_MS)
                        else:
                            expect(output).to_be_visible(timeout=INTERACTION_TIMEOUT_MS)
                        if visibility is not False and "expect_text" in check:
                            expect(output).to_contain_text(
                                str(check["expect_text"]),
                                timeout=INTERACTION_TIMEOUT_MS,
                            )
                        elif visibility is None and before_visible:
                            expect(output).not_to_have_text(
                                before, timeout=INTERACTION_TIMEOUT_MS
                            )
                        report.update(
                            f"interaction-{index}",
                            after_text=output.inner_text()[:2000]
                            if visibility is not False
                            else "",
                            after_visible=visibility is not False,
                        )
                    except Exception as error:
                        try:
                            report.update(
                                f"interaction-{index}",
                                after_text=output.inner_text(timeout=1000)[:2000]
                                if output.is_visible()
                                else "",
                            )
                        except Exception:
                            pass
                        raise ValueError(
                            f"Interaction check {index} failed: control={check.get('selector')!r}, "
                            f"feedback={check.get('expect_selector')!r}, action={check.get('action', 'click')!r}. "
                            + str(error)[:1200]
                        ) from error
            with report.check("desktop_capture"):
                page.screenshot(path=str(workspace / "preview.png"), full_page=True)
            with report.check("mobile"):
                page.set_viewport_size({"width": 390, "height": 844})
                dimensions = frame.locator("html").evaluate(
                    "(el) => ({content: el.scrollWidth, viewport: innerWidth})"
                )
                report.update(
                    "mobile",
                    observed=f"Content width: {dimensions['content']}px; frame viewport: {dimensions['viewport']}px.",
                )
                if dimensions["content"] > dimensions["viewport"] + 2:
                    raise ValueError("Notebook overflows the phone viewport")
            with report.check("mobile_capture"):
                page.screenshot(
                    path=str(workspace / "preview-mobile.png"), full_page=True
                )
            with report.check("runtime"):
                if errors:
                    raise ValueError(
                        "Browser validation failed: " + "; ".join(errors)[:1000]
                    )
        finally:
            if errors:
                report.update(
                    "runtime",
                    status="failed",
                    reason="Browser errors were recorded.",
                    diagnostics=[str(error)[:2000] for error in errors[:50]],
                )
            browser.close()
    manifest["entrypoint"] = entry
    return manifest
