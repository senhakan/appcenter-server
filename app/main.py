from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.v1.agent import router as agent_router
from app.api.v1.auth import router as auth_router
from app.api.v1.web import router as web_router
from app.config import get_settings
from app.database import init_db, seed_initial_data
from app.tasks.scheduler import start_scheduler, stop_scheduler
from app.utils.file_handler import ensure_upload_dir

settings = get_settings()
logger = logging.getLogger("appcenter")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_upload_dir(settings.upload_dir)
    init_db()
    seed_initial_data()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(agent_router, prefix=settings.api_v1_prefix)
app.include_router(web_router, prefix=settings.api_v1_prefix)


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    if request.url.path.startswith(settings.api_v1_prefix):
        return JSONResponse(
            status_code=exc.status_code,
            content={"status": "error", "detail": exc.detail},
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s: %s", request.url.path, exc)
    if request.url.path.startswith(settings.api_v1_prefix):
        return JSONResponse(
            status_code=500,
            content={"status": "error", "detail": "Internal server error"},
        )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "api_prefix": settings.api_v1_prefix,
    }


@app.get("/ui")
def ui_root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=302)


@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request, "active_page": ""})


@app.get("/dashboard")
def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request, "active_page": "dashboard"})


@app.get("/agents")
def agents_page(request: Request):
    return templates.TemplateResponse("agents/list.html", {"request": request, "active_page": "agents"})


@app.get("/agents/{agent_uuid}")
def agent_detail_page(request: Request, agent_uuid: str):
    return templates.TemplateResponse(
        "agents/detail.html",
        {"request": request, "active_page": "agents", "agent_uuid": agent_uuid},
    )


@app.get("/applications")
def applications_page(request: Request):
    return templates.TemplateResponse(
        "applications/list.html",
        {"request": request, "active_page": "applications"},
    )


@app.get("/applications/upload")
def applications_upload_page(request: Request):
    return templates.TemplateResponse(
        "applications/upload.html",
        {"request": request, "active_page": "applications"},
    )


@app.get("/deployments")
def deployments_page(request: Request):
    return templates.TemplateResponse(
        "deployments/list.html",
        {"request": request, "active_page": "deployments"},
    )


@app.get("/deployments/create")
def deployments_create_page(request: Request):
    return templates.TemplateResponse(
        "deployments/create.html",
        {"request": request, "active_page": "deployments"},
    )


@app.get("/settings")
def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request, "active_page": "settings"})
