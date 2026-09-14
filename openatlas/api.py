from urllib.parse import urlsplit
import os
import ipaddress
import secrets
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from .reader import reader_document
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, SecretStr
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import config
from .artifacts import ArtifactStore, artifact_media_type
from .phone import PhoneAccess
from .credentials import Credentials
from .debug import DebugStore, redact
import json
from .models import DEFAULT_MODEL, MODELS
from .repository import Repository
from .skills import SkillCatalog
from .agents import CodexAdapter, DEFAULT_TEACHING_PROMPT
from .skill_editor import SkillEditor
from .planning import DEFAULT_PLANNER_INSTRUCTIONS


class Generation(BaseModel):
    prompt_only: bool = False
    learner_background: str = Field(default="", max_length=8000)
    prompt: str = Field(min_length=3, max_length=12000)
    skills: Optional[list[str]] = None
    skills_enabled: Optional[bool] = None
    instructions: str = Field(default="", max_length=8000)
    provider: Optional[str] = None
    reading_minutes: Optional[int] = Field(default=None, ge=5, le=50, strict=True)


class Settings(BaseModel):
    planner_model: str = Field(default=DEFAULT_MODEL, min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9._-]+$")
    planner_instructions: str = Field(default=DEFAULT_PLANNER_INSTRUCTIONS, min_length=1, max_length=40000)
    teaching_prompt: Optional[str] = Field(default=None, max_length=40000)
    provider: str = "demo"
    concurrency: int = Field(default=2, ge=1, le=8)
    model: str = Field(
        default=DEFAULT_MODEL,
        min_length=1,
        max_length=100,
        pattern=r"^[a-zA-Z0-9._-]+$",
    )


class PromptEdit(BaseModel):
    content: str = Field(max_length=40000)


class SkillFile(BaseModel):
    skill_id: str
    path: str
    content: str = Field(max_length=500000)
    revision: Optional[str] = None


class SkillCreate(BaseModel):
    name: str = Field(max_length=64)


class CredentialUpdate(BaseModel):
    api_key: SecretStr


class RetryJob(BaseModel):
    mode: str = Field(default="continue", pattern=r"^(continue|rerun)$")


class PhoneUpdate(BaseModel):
    enabled: bool
    rotate: bool = False


class Login(BaseModel):
    token: str


def create_app(repo=None, catalog=None, store=None, credentials=None):
    repo = repo or Repository()
    catalog = catalog or SkillCatalog()
    store = store or ArtifactStore(repo.data)
    credentials = credentials or Credentials(repo.data)
    app = FastAPI(title="OpenAtlas", docs_url=None, redoc_url=None)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=os.getenv("OPENATLAS_ALLOWED_HOSTS", "localhost,127.0.0.1").split(
            ","
        ),
    )
    access_token = os.getenv("OPENATLAS_ACCESS_TOKEN", "")
    public_origin = os.getenv("OPENATLAS_PUBLIC_ORIGIN", "").rstrip("/")
    remote = urlsplit(public_origin)
    if public_origin and (
        remote.scheme != "https" or not remote.hostname or remote.path
        or remote.query or remote.fragment or remote.username or remote.password
        or not access_token
    ):
        raise ValueError("Remote access requires an HTTPS origin and an access token")

    lan_url = os.getenv("OPENATLAS_LAN_URL", "").rstrip("/")
    if lan_url:
        lan = urlsplit(lan_url)
        try:
            address = ipaddress.IPv4Address(lan.hostname)
            valid = any(address in ipaddress.ip_network(net) for net in
                        ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
        except (ValueError, TypeError):
            valid = False
        if (not valid or lan.scheme != "http" or lan.path or lan.query
                or lan.fragment or lan.username or lan.password or not access_token):
            raise ValueError("Wi-Fi access requires a private IPv4 HTTP URL and an access token")

    desktop_port = os.getenv("OPENATLAS_DESKTOP_PORT", "")
    phone = PhoneAccess(repo.data, access_token)

    def desktop_request(request):
        # The host launcher maps this socket exclusively to host loopback.
        # Host and forwarded client headers alone are never sufficient.
        server = request.scope.get("server")
        return bool(desktop_port and server and str(server[1]) == desktop_port
                    and request.url.hostname in ("localhost", "127.0.0.1", "::1"))

    def browser_origin(request):
        # Serve terminates HTTPS before forwarding to the loopback HTTP port.
        # Only the explicit configured host uses the canonical HTTPS origin.
        if public_origin and request.headers.get("host") == remote.netloc:
            return public_origin
        return str(request.base_url).rstrip("/")

    @app.middleware("http")
    async def boundaries(request: Request, call_next):
        path = request.url.path
        local = desktop_request(request)
        sharing = phone.read() if desktop_port else None
        # A disabled LAN listener serves no application data or artifacts.
        if desktop_port and not local and (not sharing["enabled"] or not lan_url):
            return JSONResponse({"detail": "Phone access is off. Enable it in Settings on the host computer."}, status_code=403)
        if path.startswith("/api/"):
            # Local access is implicit authority: opaque generated frames and
            # cross-site pages must not use it, including on read endpoints.
            if local and (request.headers.get("sec-fetch-site") == "cross-site"
                          or (request.headers.get("origin") is not None
                              and request.headers["origin"] != browser_origin(request))):
                return JSONResponse({"detail": "Cross-origin desktop access is not allowed"}, status_code=403)
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                origin = request.headers.get("origin")
                if origin and origin != browser_origin(request):
                    return JSONResponse(
                        {"detail": "Cross-origin writes are not allowed"},
                        status_code=403,
                    )
                if request.headers.get("sec-fetch-site") == "cross-site":
                    return JSONResponse(
                        {"detail": "Cross-site writes are not allowed"}, status_code=403
                    )
            if (
                not local
                and (desktop_port or access_token)
                and path != "/api/session"
                and not secrets.compare_digest(
                    request.cookies.get("openatlas_session", ""), sharing["token"] if sharing else access_token
                )
            ):
                return JSONResponse(
                    {"detail": "Enter the host access token to open this library"},
                    status_code=401,
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if path.startswith("/artifacts/"):
            base = (
                browser_origin(request) + "/".join(path.split("/")[:4]) + "/"
            )
            response.headers["Content-Security-Policy"] = config.artifact_csp(base)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Cache-Control"] = "no-store" if "reader" in request.query_params else "public,max-age=31536000,immutable"
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
            )
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/session")
    def login(body: Login, response: Response, request: Request):
        session_token = phone.read()["token"] if desktop_port else access_token
        if not session_token or not secrets.compare_digest(body.token, session_token):
            raise HTTPException(403, "Invalid access token")
        response.set_cookie(
            "openatlas_session", session_token, httponly=True, samesite="strict",
            secure=browser_origin(request).startswith("https://"),
            max_age=30 * 24 * 60 * 60, path="/"
        )
        return {"ok": True}

    def phone_details(request):
        state = phone.read() if desktop_port else {"enabled": bool(lan_url), "token": access_token}
        enabled = bool(lan_url and state["enabled"])
        return {"enabled": enabled, "available": bool(lan_url and desktop_port),
                "desktop": desktop_request(request), "url": lan_url,
                "pairing_url": lan_url + "/#access_token=" + state["token"] if enabled else ""}

    @app.get("/api/phone")
    def phone_access(request: Request):
        return phone_details(request)

    @app.put("/api/phone")
    def update_phone(body: PhoneUpdate, request: Request):
        if not desktop_request(request):
            raise HTTPException(403, "Manage phone access on the host computer")
        if not lan_url:
            raise HTTPException(409, "No Wi-Fi adapter is available. Reconnect the host to Wi-Fi and restart OpenAtlas.")
        phone.update(body.enabled, body.rotate)
        return phone_details(request)

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/settings")
    def settings():
        return repo.settings()

    @app.put("/api/settings")
    def update_settings(body: Settings):
        if body.provider not in ("demo", "codex"):
            raise HTTPException(422, "Unknown provider")
        saved = body.model_dump()
        previous = repo.settings()
        for field in ('planner_model', 'planner_instructions'):
            if field not in body.model_fields_set:
                saved[field] = previous[field]
        repo.save_settings(saved)
        return repo.settings()

    @app.get("/api/prompt")
    def prompt_defaults():
        return {"default": DEFAULT_TEACHING_PROMPT, "planner_default": DEFAULT_PLANNER_INSTRUCTIONS}

    @app.post("/api/prompt/preview")
    def prompt_preview(body: PromptEdit):
        return {"prompt": CodexAdapter().prompt({"prompt": "[The learner’s topic]", "instructions": "[Additional instructions]", "skills": [], "teaching_prompt": body.content, "reading_minutes": 20})}

    @app.get("/api/skill-files")
    def skill_files(skill_id: str, path: Optional[str] = None):
        try:
            return SkillEditor(catalog).read(skill_id, path)
        except (ValueError, OSError) as e:
            raise HTTPException(422, str(e))

    @app.put("/api/skill-files")
    def save_skill_file(body: SkillFile):
        try:
            return SkillEditor(catalog).save(body.skill_id, body.path, body.content, body.revision)
        except (ValueError, OSError) as e:
            raise HTTPException(422, str(e))

    @app.post("/api/skills/create", status_code=201)
    def create_skill(body: SkillCreate):
        try:
            return SkillEditor(catalog).create(body.name)
        except (ValueError, OSError) as e:
            raise HTTPException(422, str(e))

    @app.post("/api/skills/install", status_code=201)
    async def install_skill(request: Request):
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 20 * 1024 * 1024:
                raise HTTPException(413, "ZIP exceeds 20 MB")
        try:
            return SkillEditor(catalog).install(bytes(data))
        except (ValueError, OSError) as e:
            raise HTTPException(422, str(e))

    @app.get("/api/models")
    def models():
        return MODELS

    @app.get("/api/credentials")
    def credential_status():
        return credentials.status()

    @app.put("/api/credentials")
    def save_credential(body: CredentialUpdate):
        try:
            credentials.save(body.api_key.get_secret_value())
        except ValueError as error:
            raise HTTPException(422, str(error))
        return credentials.status()

    @app.delete("/api/credentials")
    def remove_credential():
        credentials.remove()
        return credentials.status()

    @app.get("/api/skills")
    def skills():
        return [{k: v for k, v in s.items() if k != "path"} for s in catalog.discover()]

    @app.get("/api/notebooks")
    def notebooks():
        return repo.library()

    @app.get("/api/notebooks/{notebook_id}")
    def notebook(notebook_id: str):
        result = repo.notebook(notebook_id)
        if not result:
            raise HTTPException(404, "Notebook not found")
        return result

    def submit(body, notebook_id=None):
        if len(body.prompt.strip()) < 3:
            raise HTTPException(
                422, "Enter a learning topic of at least three characters"
            )
        settings = repo.settings()
        provider = body.provider or settings["provider"]
        if provider not in ("demo", "codex"):
            raise HTTPException(422, "Unknown generation provider")
        base_version = None
        existing_context = None
        reading_minutes = body.reading_minutes
        ids = body.skills
        skills_enabled = body.skills_enabled
        if notebook_id:
            existing = repo.notebook(notebook_id)
            if not existing or not existing["latest_version"]:
                raise HTTPException(404, "Published Notebook not found")
            base_version = existing["latest_version"]
            version = next(v for v in existing["versions"] if v["id"] == base_version)
            existing_context = {'title': existing['title'], 'description': version['manifest'].get('description', '')}
            if skills_enabled is None:
                skills_enabled = bool(version["provenance"])
            if reading_minutes is None:
                reading_minutes = version["manifest"].get("target_reading_minutes", 20)
            if body.provider is None:
                provider = version["provider"]
            if ids is None:
                ids = [s["id"] for s in version["provenance"] if not s["required"]]
        try:
            selected = catalog.resolve(ids or []) if skills_enabled is not False else []
        except ValueError as e:
            raise HTTPException(422, str(e))
        if body.prompt_only and provider != 'codex':
            raise HTTPException(422, 'Prompt planning requires the Codex provider and an OpenAI key')
        try:
            catalog.snapshot(selected, repo.data / 'skill-inputs')
        except (ValueError, OSError) as error:
            raise HTTPException(422, str(error))
        return repo.enqueue(
            {
                "prompt": body.prompt.strip(),
                "learner_background": body.learner_background,
                "existing_notebook": existing_context,
                "prompt_only": body.prompt_only,
                "planning_enabled": provider == 'codex',
                "skill_snapshots": True,
                "planner_model": settings['planner_model'],
                "planner_instructions": settings['planner_instructions'],
                "instructions": body.instructions,
                "skills": selected,
                "skills_enabled": skills_enabled is not False,
                "provider": provider,
                "model": settings["model"],
                "teaching_prompt": settings.get("teaching_prompt") or DEFAULT_TEACHING_PROMPT,
                "base_version": base_version,
                "reading_minutes": reading_minutes
                if reading_minutes is not None
                else 20,
            },
            notebook_id,
        )

    @app.post("/api/jobs", status_code=202)
    def generate(body: Generation):
        return submit(body)

    @app.post("/api/notebooks/{notebook_id}/revisions", status_code=202)
    def revise(notebook_id: str, body: Generation):
        return submit(body, notebook_id)

    @app.get("/api/jobs")
    def jobs():
        return [dict(job, can_continue=job["status"] == "failed" and store.checkpoint_path(job["id"]) is not None) for job in repo.list_jobs()]

    @app.post("/api/jobs/{job_id}/retry", status_code=202)
    def retry_job(job_id: str, body: RetryJob):
        original = repo.job(job_id)
        if not original:
            raise HTTPException(404, "Generation not found")
        if original["status"] != "failed":
            raise HTTPException(409, "Only failed jobs can be retried")
        if body.mode == "continue" and store.checkpoint_path(job_id) is None:
            raise HTTPException(409, "No saved workspace remains. Use Re-run to start a fresh attempt.")
        request = dict(original["request"])
        for key in ("revalidate_job", "continue_job", "validation_feedback", "previous_error", "job_id"):
            request.pop(key, None)
        request["retry_of"] = job_id
        if body.mode == "continue":
            request["continue_job"] = job_id
            request["previous_error"] = (original.get("error") or "")[:2000]
        try:
            return repo.enqueue(request, original["notebook_id"], retry_of=job_id)
        except ValueError as error:
            raise HTTPException(409, str(error))

    @app.post("/api/jobs/{job_id}/revalidate", status_code=202)
    def revalidate_job(job_id: str):
        original = repo.job(job_id)
        if not original:
            raise HTTPException(404, "Generation not found")
        if original["status"] != "failed" or store.recovery_path(job_id) is None:
            raise HTTPException(
                409, "Only failed jobs with retained artifacts can be rechecked"
            )
        return repo.enqueue(
            dict(original["request"], revalidate_job=job_id), original["notebook_id"]
        )

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        if not repo.job(job_id):
            raise HTTPException(404, 'Generation not found')
        repo.cancel(job_id)
        return repo.job(job_id)

    @app.get("/api/jobs/{job_id}/plans")
    def plans(job_id: str):
        job = repo.job(job_id)
        if not job:
            raise HTTPException(404, 'Generation not found')
        return repo.plan_records(job['notebook_id'])

    @app.post("/api/prompts/{revision_id}/edit", status_code=201)
    def edit_plan(revision_id: str, body: PromptEdit):
        revision = repo.prompt_revision(revision_id)
        if not revision:
            raise HTTPException(404, 'Prompt not found')
        try:
            return repo.save_prompt(revision['attempt_id'], body.content, revision_id)
        except ValueError as error:
            raise HTTPException(422, str(error))

    @app.post("/api/prompts/{revision_id}/build", status_code=202)
    def build_plan(revision_id: str):
        revision = repo.prompt_revision(revision_id)
        if not revision:
            raise HTTPException(404, 'Prompt not found')
        attempt = repo.rows('SELECT job_id FROM planning_attempts WHERE id=:id', id=revision['attempt_id'])[0]
        original = repo.job(attempt['job_id'])
        request = dict(original['request'], build_prompt=revision['content'], prompt_only=False,
                       planning_attempt_id=revision['attempt_id'], prompt_revision_id=revision_id)
        for key in ('continue_job', 'revalidate_job', 'retry_of', 'validation_feedback', 'job_id'):
            request.pop(key, None)
        return repo.enqueue(request, original['notebook_id'])

    @app.post("/api/jobs/{job_id}/replan", status_code=202)
    def replan(job_id: str):
        original = repo.job(job_id)
        if not original:
            raise HTTPException(404, 'Generation not found')
        if original['status'] in ('queued', 'running'):
            raise HTTPException(409, 'Wait for this attempt to finish')
        request = dict(original['request'], prompt_only=True, planning_enabled=True, provider='codex')
        for key in ('build_prompt', 'planning_attempt_id', 'prompt_revision_id', 'continue_job', 'retry_of', 'revalidate_job', 'job_id'):
            request.pop(key, None)
        settings = repo.settings()
        request.update(planner_model=settings['planner_model'], planner_instructions=settings['planner_instructions'])
        return repo.enqueue(request, original['notebook_id'])

    @app.get("/api/jobs/{job_id}/debug")
    def job_debug(job_id: str):
        job = repo.job(job_id)
        if not job:
            raise HTTPException(404, "Generation not found")
        debug = DebugStore(repo.data)
        request = job["request"]
        agent_used = request.get("provider") == "codex" and not request.get("revalidate_job") and not request.get("local_edit")
        invocations = debug.invocations(job_id)
        prompt = CodexAdapter().prompt(request) if agent_used else None
        metadata = {
            "request": request,
            "job": {k: v for k, v in job.items() if k != "request"},
            "invocations": invocations,
            "prompt": prompt,
            "prompt_source": "captured" if invocations else "reconstructed" if agent_used else "not_applicable",
            "skills": [{**s, "sandbox_path": "/workspace/skills/" + s["id"].replace(":", "--") + "/SKILL.md"} for s in request.get("skills", [])],
        }
        try:
            known_key = credentials.openai_key()
        except ValueError:
            known_key = ''
        return json.loads(redact(json.dumps({"job": job, **debug.read(job_id), "generation": metadata}), (known_key,)))

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        result = repo.job(job_id)
        if not result:
            raise HTTPException(404, "Job not found")
        return result

    @app.get("/artifacts/{notebook_id}/{version_id}/{path:path}")
    def artifact(notebook_id: str, version_id: str, path: str, reader: bool = False):
        if not repo.has_version(notebook_id, version_id):
            raise HTTPException(404, "Published Notebook version not found")
        result = store.artifact(notebook_id, version_id, path)
        if not result:
            raise HTTPException(404, "Artifact not found")
        if reader and result.suffix.lower() == ".html":
            return HTMLResponse(reader_document(result.read_text(encoding="utf-8")))
        return FileResponse(result, media_type=artifact_media_type(result))

    if (config.FRONTEND / "assets").exists():
        app.mount(
            "/assets",
            StaticFiles(directory=config.FRONTEND / "assets"),
            name="frontend-assets",
        )

    @app.get("/")
    @app.get("/notebooks/{notebook_id}")
    def frontend(notebook_id: str = ""):
        if not (config.FRONTEND / "index.html").exists():
            return JSONResponse(
                {
                    "detail": "Build the frontend: cd frontend && npm ci && npm run build"
                },
                status_code=503,
            )
        return FileResponse(config.FRONTEND / "index.html")

    return app


app = create_app()
