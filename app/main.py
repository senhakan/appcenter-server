from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from starlette.websockets import WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.v1.agent import router as agent_router
from app.api.v1.auth import router as auth_router
from app.api.v1.inventory import router as inventory_router
from app.api.v1.remote_support import router as remote_support_router
from app.api.v1.web import router as web_router
from app.config import get_settings
from app.database import init_db, seed_initial_data
from app.tasks.scheduler import start_scheduler, stop_scheduler
from app.utils.file_handler import ensure_upload_dir
from app.services import novnc_service

settings = get_settings()
logger = logging.getLogger("appcenter")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
# Cache-bust static assets to avoid UI breaking after deploys due to stale browser cache.
templates.env.globals["ASSET_VERSION"] = settings.app_version


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
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(agent_router, prefix=settings.api_v1_prefix)
app.include_router(web_router, prefix=settings.api_v1_prefix)
app.include_router(inventory_router, prefix=settings.api_v1_prefix)
app.include_router(remote_support_router, prefix=settings.api_v1_prefix)


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


@app.websocket("/novnc-ws")
async def novnc_ws_bridge(websocket: WebSocket):
    """
    Internal noVNC bridge mode:
    Browser WS <-> raw TCP VNC (agent_ip:5900), validated by one-time ticket.
    """
    if settings.remote_support_ws_mode != "internal":
        await websocket.close(code=1008, reason="internal_ws_mode_disabled")
        return

    token = (websocket.query_params.get("token") or "").strip()
    target = novnc_service.consume_internal_ticket(token)
    if not target:
        await websocket.close(code=1008, reason="invalid_or_expired_token")
        return
    agent_ip, vnc_port = target

    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(agent_ip, vnc_port), timeout=8)
    except Exception:
        await websocket.close(code=1011, reason="vnc_target_unreachable")
        return

    await websocket.accept()

    async def ws_to_tcp():
        try:
            while True:
                message = await websocket.receive()
                if "bytes" in message and message["bytes"] is not None:
                    writer.write(message["bytes"])
                    await writer.drain()
                    continue
                if message.get("type") == "websocket.disconnect":
                    break
                if "text" in message and message["text"] is not None:
                    writer.write(message["text"].encode("utf-8", errors="ignore"))
                    await writer.drain()
        except WebSocketDisconnect:
            return
        except Exception:
            return

    async def tcp_to_ws():
        try:
            while True:
                chunk = await reader.read(65536)
                if not chunk:
                    break
                await websocket.send_bytes(chunk)
        except WebSocketDisconnect:
            return
        except Exception:
            return

    task_a = asyncio.create_task(ws_to_tcp())
    task_b = asyncio.create_task(tcp_to_ws())
    done, pending = await asyncio.wait({task_a, task_b}, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    await asyncio.gather(*done, return_exceptions=True)

    try:
        writer.close()
        await writer.wait_closed()
    except Exception:
        pass
    try:
        await websocket.close()
    except Exception:
        pass


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


@app.get("/groups")
def groups_page(request: Request):
    return templates.TemplateResponse("groups/list.html", {"request": request, "active_page": "groups"})


@app.get("/agents/{agent_uuid}")
def agent_detail_page(request: Request, agent_uuid: str):
    return templates.TemplateResponse(
        "agents/detail.html",
        {"request": request, "active_page": "agents", "agent_uuid": agent_uuid},
    )

@app.get("/remote-support/sessions/{session_id}")
def remote_support_session_page(request: Request, session_id: int):
    return templates.TemplateResponse(
        "remote_support/session.html",
        {
            "request": request,
            "active_page": "agents",
            "session_id": session_id,
            "novnc_mode": settings.remote_support_novnc_mode,
        },
    )


@app.get("/applications")
def applications_page(request: Request):
    return templates.TemplateResponse(
        "applications/list.html",
        {"request": request, "active_page": "applications"},
    )


@app.get("/applications/{app_id}/edit")
def applications_edit_page(request: Request, app_id: int):
    return templates.TemplateResponse(
        "applications/edit.html",
        {"request": request, "active_page": "applications", "app_id": app_id},
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


@app.get("/deployments/{deployment_id}/edit")
def deployments_edit_page(request: Request, deployment_id: int):
    return templates.TemplateResponse(
        "deployments/edit.html",
        {"request": request, "active_page": "deployments", "deployment_id": deployment_id},
    )


@app.get("/inventory")
def inventory_page(request: Request):
    return templates.TemplateResponse("inventory/list.html", {"request": request, "active_page": "inventory"})


@app.get("/inventory/software/{software_name}/agents")
def inventory_software_detail_page(request: Request, software_name: str):
    return templates.TemplateResponse(
        "inventory/software_detail.html",
        {"request": request, "active_page": "inventory", "software_name": software_name},
    )


@app.get("/inventory/normalization")
def inventory_normalization_page(request: Request):
    return templates.TemplateResponse(
        "inventory/normalization.html",
        {"request": request, "active_page": "inventory"},
    )


@app.get("/licenses")
def licenses_page(request: Request):
    return templates.TemplateResponse("licenses/list.html", {"request": request, "active_page": "licenses"})


@app.get("/licenses/create")
def licenses_create_page(request: Request):
    return templates.TemplateResponse("licenses/form.html", {"request": request, "active_page": "licenses", "license_id": None})


@app.get("/licenses/{license_id}/edit")
def licenses_edit_page(request: Request, license_id: int):
    return templates.TemplateResponse(
        "licenses/form.html",
        {"request": request, "active_page": "licenses", "license_id": license_id},
    )


@app.get("/settings")
def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request, "active_page": "settings"})


@app.get("/groups/{group_id}/edit")
def groups_edit_page(request: Request, group_id: int):
    return templates.TemplateResponse(
        "groups/edit.html",
        {"request": request, "active_page": "groups", "group_id": group_id},
    )
