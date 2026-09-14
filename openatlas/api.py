from urllib.parse import urlsplit
import os
import ipaddress
import secrets
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, SecretStr
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import config
from .artifacts import ArtifactStore
from .credentials import Credentials
from .debug import DebugStore
from .models import DEFAULT_MODEL, MODELS
from .repository import Repository
from .skills import SkillCatalog


class Generation(BaseModel):
    prompt: str = Field(min_length=3, max_length=12000)
    skills: Optional[list[str]] = None
    skills_enabled: Optional[bool] = None
    instructions: str = Field(default="", max_length=8000)
    provider: Optional[str] = None
    reading_minutes: Optional[int] = Field(default=None, ge=5, le=50, strict=True)


class Settings(BaseModel):
    provider: str = "demo"
    concurrency: int = Field(default=2, ge=1, le=8)
    model: str = Field(
        default=DEFAULT_MODEL,
        min_length=1,
        max_length=100,
        pattern=r"^[a-zA-Z0-9._-]+$",
    )


class CredentialUpdate(BaseModel):
    api_key: SecretStr


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

    def browser_origin(request):
        # Serve terminates HTTPS before forwarding to the loopback HTTP port.
        # Only the explicit configured host uses the canonical HTTPS origin.
        if public_origin and request.headers.get("host") == remote.netloc:
            return public_origin
        return str(request.base_url).rstrip("/")

    @app.middleware("http")
    async def boundaries(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/"):
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
                access_token
                and path != "/api/session"
                and not secrets.compare_digest(
                    request.cookies.get("openatlas_session", ""), access_token
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
            response.headers["Cache-Control"] = "public,max-age=31536000,immutable"
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
            )
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/session")
    def login(body: Login, response: Response, request: Request):
        if not access_token or not secrets.compare_digest(body.token, access_token):
            raise HTTPException(403, "Invalid access token")
        response.set_cookie(
            "openatlas_session", access_token, httponly=True, samesite="strict",
            secure=browser_origin(request).startswith("https://")
        )
        return {"ok": True}

    @app.get("/api/phone")
    def phone_access():
        # Protected by the same owner session as settings. Fragments never go to
        # the HTTP server; the trusted UI exchanges this for an HttpOnly cookie.
        return {"enabled": bool(lan_url), "url": lan_url,
                "pairing_url": lan_url + "/#access_token=" + access_token if lan_url else ""}

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
        repo.save_settings(body.model_dump())
        return repo.settings()

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
        reading_minutes = body.reading_minutes
        ids = body.skills
        skills_enabled = body.skills_enabled
        if notebook_id:
            existing = repo.notebook(notebook_id)
            if not existing or not existing["latest_version"]:
                raise HTTPException(404, "Published Notebook not found")
            base_version = existing["latest_version"]
            version = next(v for v in existing["versions"] if v["id"] == base_version)
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
        return repo.enqueue(
            {
                "prompt": body.prompt.strip(),
                "instructions": body.instructions,
                "skills": selected,
                "skills_enabled": skills_enabled is not False,
                "provider": provider,
                "model": settings["model"],
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
        return repo.list_jobs()

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

    @app.get("/api/jobs/{job_id}/debug")
    def job_debug(job_id: str):
        job = repo.job(job_id)
        if not job:
            raise HTTPException(404, "Generation not found")
        return {"job": job, **DebugStore(repo.data).read(job_id)}

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        result = repo.job(job_id)
        if not result:
            raise HTTPException(404, "Job not found")
        return result

    @app.get("/artifacts/{notebook_id}/{version_id}/{path:path}")
    def artifact(notebook_id: str, version_id: str, path: str):
        if not repo.has_version(notebook_id, version_id):
            raise HTTPException(404, "Published Notebook version not found")
        result = store.artifact(notebook_id, version_id, path)
        if not result:
            raise HTTPException(404, "Artifact not found")
        return FileResponse(result)

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
