"""Immutable filesystem library and browser validation. Never execute generated source."""

import html
import json
import mimetypes
import shutil
from pathlib import Path
from urllib.parse import unquote, urlparse

from playwright.sync_api import expect, sync_playwright

from . import config

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
    if not safe_tree(workspace / "source"):
        raise ValueError("Notebook requires retained editable source files")
    dist = workspace / "dist"
    safe_tree(dist)
    for p in dist.rglob("*"):
        if p.is_file() and p.suffix.lower() not in ALLOWED:
            raise ValueError("Unsupported static artifact file: " + p.name)
    manifest = json.loads((workspace / "manifest.json").read_text())
    if (
        not isinstance(manifest.get("title"), str)
        or not 1 <= len(manifest["title"]) <= 150
    ):
        raise ValueError("Manifest needs a title of 1–150 characters")
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
    checks = manifest.get("checks", [])
    if not isinstance(checks, list) or not 1 <= len(checks) <= 30:
        raise ValueError("Declare 1–30 browser interaction checks in manifest.json")
    errors = []
    with sync_playwright() as p:
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
                content_type=mimetypes.guess_type(str(path))[0]
                or "application/octet-stream",
                headers={
                    "Content-Security-Policy": config.artifact_csp(
                        "http://notebook.invalid/artifact/"
                    ),
                    "Access-Control-Allow-Origin": "*",
                },
            )

        context.route("**/*", route_handler)
        try:
            page.goto("http://notebook.invalid/reader")
            frame = page.frame_locator("iframe")
            frame.locator("body").wait_for()
            if len(frame.locator("body").inner_text().strip()) < 150:
                raise ValueError("Notebook has insufficient rendered learning content")
            for index, check in enumerate(checks, 1):
                try:
                    target = frame.locator(check["selector"])
                    output = frame.locator(check["expect_selector"])
                    expect(target).to_be_visible(timeout=5000)
                    before_visible = output.is_visible()
                    before = output.inner_text() if before_visible else None
                    action = check.get("action", "click")
                    if action == "click":
                        target.click(timeout=5000)
                    elif action == "fill":
                        target.fill(str(check["value"]), timeout=5000)
                    elif action == "range":
                        target.evaluate(
                            '(el, value) => { el.value=value; el.dispatchEvent(new Event("input",{bubbles:true})); el.dispatchEvent(new Event("change",{bubbles:true})); }',
                            str(check["value"]),
                        )
                    else:
                        raise ValueError("Unsupported interaction check action")
                    # Feedback may be revealed or created by the action. It must be
                    # visible afterward; matching hidden text never counts as success.
                    expect(output).to_be_visible(timeout=5000)
                    if "expect_text" in check:
                        expect(output).to_contain_text(
                            str(check["expect_text"]), timeout=5000
                        )
                    elif before_visible:
                        expect(output).not_to_have_text(before, timeout=5000)
                except Exception as error:
                    raise ValueError(
                        f"Interaction check {index} failed: control={check.get('selector')!r}, "
                        f"feedback={check.get('expect_selector')!r}, action={check.get('action', 'click')!r}. "
                        + str(error)[:1200]
                    ) from error
            page.screenshot(path=str(workspace / "preview.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            if frame.locator("html").evaluate(
                "(el) => el.scrollWidth > innerWidth + 2"
            ):
                raise ValueError("Notebook overflows the phone viewport")
            page.screenshot(path=str(workspace / "preview-mobile.png"), full_page=True)
            if errors:
                raise ValueError(
                    "Browser validation failed: " + "; ".join(errors)[:1000]
                )
            (workspace / "validation.json").write_text(
                json.dumps(
                    {
                        "passed": True,
                        "checks": checks,
                        "browser": "Chromium",
                        "sandbox": "allow-scripts",
                    }
                )
            )
        finally:
            browser.close()
    manifest["entrypoint"] = entry
    return manifest
