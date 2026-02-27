from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
import logging
from pathlib import Path
import socket
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from starlette.websockets import WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.v1.agent import router as agent_router
from app.api.v1.audit import router as audit_router
from app.api.v1.auth import router as auth_router
from app.api.v1.inventory import router as inventory_router
from app.api.v1.remote_support import router as remote_support_router
from app.api.v1.users import router as users_router
from app.api.v1.web import router as web_router
from app.config import get_settings
from app.database import init_db, seed_initial_data
from app.tasks.scheduler import start_scheduler, stop_scheduler
from app.utils.file_handler import ensure_upload_dir
from app.services import agent_signal, novnc_service

settings = get_settings()
logger = logging.getLogger("appcenter")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
# Cache-bust static assets to avoid UI breaking after deploys due to stale browser cache.
templates.env.globals["ASSET_VERSION"] = settings.app_version
NAV_SCHEMA: list[dict[str, Any]] = [
    {
        "key": "dashboard",
        "title": "Dashboard",
        "path": "/dashboard",
        "active_pages": ["dashboard"],
        "roles": ["admin", "operator", "viewer"],
        "feature_flag": None,
    },
    {
        "key": "agents",
        "title": "Ajanlar",
        "path": "/agents",
        "active_pages": ["agents"],
        "roles": ["admin", "operator", "viewer"],
        "feature_flag": None,
    },
    {
        "key": "groups",
        "title": "Gruplar",
        "path": "/groups",
        "active_pages": ["groups"],
        "roles": ["admin", "operator", "viewer"],
        "feature_flag": None,
    },
    {
        "key": "applications",
        "title": "Uygulamalar",
        "path": "/applications",
        "active_pages": ["applications"],
        "roles": ["admin", "operator", "viewer"],
        "feature_flag": None,
    },
    {
        "key": "deployments",
        "title": "Dagitimlar",
        "path": "/deployments",
        "active_pages": ["deployments"],
        "roles": ["admin", "operator", "viewer"],
        "feature_flag": None,
    },
    {
        "key": "inventory",
        "title": "Envanter",
        "path": "/inventory",
        "active_pages": ["inventory"],
        "roles": ["admin", "operator", "viewer"],
        "feature_flag": None,
    },
    {
        "key": "licenses",
        "title": "Lisanslar",
        "path": "/licenses",
        "active_pages": ["licenses"],
        "roles": ["admin", "operator", "viewer"],
        "feature_flag": "licenses",
    },
    {
        "key": "management",
        "title": "Yonetim",
        "roles": ["admin", "operator", "viewer"],
        "feature_flag": None,
        "children": [
            {
                "key": "settings",
                "title": "Ayarlar",
                "path": "/settings",
                "active_pages": ["settings"],
                "roles": ["admin"],
                "feature_flag": None,
            },
            {"key": "users", "title": "Kullanicilar", "path": "/users", "active_pages": ["users"], "roles": ["admin"], "feature_flag": "users"},
            {"key": "roles", "title": "Roller (Yakinda)", "path": None, "active_pages": [], "roles": ["admin"], "feature_flag": "rbac"},
        ],
    },
    {
        "key": "infrastructure",
        "title": "Altyapi",
        "roles": ["admin", "operator", "viewer"],
        "feature_flag": None,
        "children": [
            {"key": "infra_health", "title": "Sistem Durumu (Yakinda)", "path": None, "active_pages": [], "roles": ["admin"], "feature_flag": "infra"},
            {"key": "infra_config", "title": "Konfigurasyon (Yakinda)", "path": None, "active_pages": [], "roles": ["admin"], "feature_flag": "infra"},
            {"key": "infra_integrations", "title": "Entegrasyonlar (Yakinda)", "path": None, "active_pages": [], "roles": ["admin"], "feature_flag": "infra"},
            {"key": "infra_audit", "title": "Audit Log", "path": "/audit", "active_pages": ["audit"], "roles": ["admin"], "feature_flag": "audit"},
            {"key": "infra_diag", "title": "Tanilama (Yakinda)", "path": None, "active_pages": [], "roles": ["admin"], "feature_flag": "infra"},
        ],
    },
]


def _enabled_menu_features() -> set[str]:
    features = {"licenses", "infra", "audit", "users", "rbac"}
    if settings.remote_support_enabled:
        features.add("remote_support")
    return features


def _item_visible(item: dict[str, Any], role: str, enabled_features: set[str]) -> bool:
    roles = item.get("roles") or []
    if roles and role not in roles:
        return False
    feature_flag = item.get("feature_flag")
    if feature_flag and feature_flag not in enabled_features:
        return False
    return True


def build_nav_menu(role: str = "admin") -> list[dict[str, Any]]:
    enabled = _enabled_menu_features()
    out: list[dict[str, Any]] = []
    for item in NAV_SCHEMA:
        if not _item_visible(item, role, enabled):
            continue
        if item.get("children"):
            children = [
                child
                for child in item["children"]
                if _item_visible(child, role, enabled)
            ]
            if not children:
                continue
            item_copy = dict(item)
            item_copy["children"] = children
            out.append(item_copy)
            continue
        out.append(item)
    return out


templates.env.globals["NAV_ROLE"] = "admin"
templates.env.globals["NAV_GET_MENU"] = build_nav_menu


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_upload_dir(settings.upload_dir)
    init_db()
    seed_initial_data()
    start_scheduler()
    yield
    agent_signal.clear_all()
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
app.include_router(users_router, prefix=settings.api_v1_prefix)
app.include_router(audit_router, prefix=settings.api_v1_prefix)


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

    client_ip = getattr(getattr(websocket, "client", None), "host", "-")
    token = (websocket.query_params.get("token") or "").strip()
    target = novnc_service.consume_internal_ticket(token)
    if not target:
        logger.warning("novnc bridge reject: invalid ticket ip=%s", client_ip)
        await websocket.close(code=1008, reason="invalid_or_expired_token")
        return
    agent_ip, vnc_port = target

    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(agent_ip, vnc_port), timeout=8)
    except Exception as exc:
        logger.warning(
            "novnc bridge connect failed ip=%s target=%s:%s err=%s",
            client_ip,
            agent_ip,
            vnc_port,
            exc,
        )
        await websocket.close(code=1011, reason="vnc_target_unreachable")
        return
    sock = writer.get_extra_info("socket")
    if sock:
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            # Linux TCP keepalive tuning; ignore on unsupported platforms.
            if hasattr(socket, "TCP_KEEPIDLE"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
            if hasattr(socket, "TCP_KEEPINTVL"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
            if hasattr(socket, "TCP_KEEPCNT"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
        except Exception as exc:
            logger.warning("novnc bridge keepalive setup failed target=%s:%s err=%s", agent_ip, vnc_port, exc)

    offered = (websocket.headers.get("sec-websocket-protocol") or "").lower()
    offered_list = [p.strip() for p in offered.split(",") if p.strip()]
    selected_subprotocol = None
    if "binary" in offered_list:
        selected_subprotocol = "binary"
    elif "base64" in offered_list:
        selected_subprotocol = "base64"

    await websocket.accept(subprotocol=selected_subprotocol)
    started_at = time.monotonic()
    logger.warning(
        "novnc bridge open ip=%s target=%s:%s proto=%s",
        client_ip,
        agent_ip,
        vnc_port,
        selected_subprotocol or "-",
    )

    async def ws_to_tcp():
        try:
            if selected_subprotocol == "base64":
                while True:
                    text_payload = await websocket.receive_text()
                    try:
                        payload = base64.b64decode(text_payload, validate=True)
                    except Exception:
                        payload = b""
                    if payload:
                        writer.write(payload)
                        await writer.drain()
                # unreachable
            else:
                while True:
                    payload = await websocket.receive_bytes()
                    if payload:
                        writer.write(payload)
                        await writer.drain()
                # unreachable
        except WebSocketDisconnect as exc:
            logger.warning("novnc bridge close side=browser ip=%s code=%s", client_ip, getattr(exc, "code", None))
            return
        except Exception as exc:
            logger.warning("novnc bridge error side=browser ip=%s err=%s", client_ip, exc)
            return

    async def tcp_to_ws():
        try:
            while True:
                chunk = await reader.read(65536)
                if not chunk:
                    logger.warning("novnc bridge eof side=vnc ip=%s target=%s:%s", client_ip, agent_ip, vnc_port)
                    break
                if selected_subprotocol == "base64":
                    await websocket.send_text(base64.b64encode(chunk).decode("ascii"))
                else:
                    await websocket.send_bytes(chunk)
        except WebSocketDisconnect as exc:
            logger.warning("novnc bridge close side=browser_send ip=%s code=%s", client_ip, getattr(exc, "code", None))
            return
        except Exception as exc:
            logger.warning("novnc bridge error side=vnc ip=%s target=%s:%s err=%s", client_ip, agent_ip, vnc_port, exc)
            return

    async def tcp_keepalive_request():
        # Keep VNC session alive during idle periods:
        # Client->Server FramebufferUpdateRequest (incremental=1, x=0,y=0,w=1,h=1).
        keepalive = b"\x03\x01\x00\x00\x00\x00\x00\x01\x00\x01"
        try:
            while True:
                await asyncio.sleep(25)
                writer.write(keepalive)
                await writer.drain()
        except Exception:
            return

    task_a = asyncio.create_task(ws_to_tcp())
    task_b = asyncio.create_task(tcp_to_ws())
    task_c = asyncio.create_task(tcp_keepalive_request())
    done, pending = await asyncio.wait({task_a, task_b, task_c}, return_when=asyncio.FIRST_COMPLETED)
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
    duration = time.monotonic() - started_at
    logger.warning(
        "novnc bridge closed ip=%s target=%s:%s duration_sec=%.1f",
        client_ip,
        agent_ip,
        vnc_port,
        duration,
    )


@app.get("/ui")
def ui_root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=302)


@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request, "active_page": ""})


@app.get("/dashboard")
def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request, "active_page": "dashboard"})


@app.get("/dashboard-v2")
def dashboard_v2_page(request: Request):
    return templates.TemplateResponse("dashboard_v2.html", {"request": request, "active_page": "dashboard"})


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
        {"request": request, "active_page": "applications", "app_id": app_id, "page_roles": "operator,admin"},
    )


@app.get("/applications/upload")
def applications_upload_page(request: Request):
    return templates.TemplateResponse(
        "applications/upload.html",
        {"request": request, "active_page": "applications", "page_roles": "operator,admin"},
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
        {"request": request, "active_page": "deployments", "page_roles": "operator,admin"},
    )


@app.get("/deployments/{deployment_id}/edit")
def deployments_edit_page(request: Request, deployment_id: int):
    return templates.TemplateResponse(
        "deployments/edit.html",
        {
            "request": request,
            "active_page": "deployments",
            "deployment_id": deployment_id,
            "page_roles": "operator,admin",
        },
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
        {"request": request, "active_page": "inventory", "page_roles": "operator,admin"},
    )


@app.get("/licenses")
def licenses_page(request: Request):
    return templates.TemplateResponse("licenses/list.html", {"request": request, "active_page": "licenses"})


@app.get("/licenses/create")
def licenses_create_page(request: Request):
    return templates.TemplateResponse(
        "licenses/form.html",
        {"request": request, "active_page": "licenses", "license_id": None, "page_roles": "operator,admin"},
    )


@app.get("/licenses/{license_id}/edit")
def licenses_edit_page(request: Request, license_id: int):
    return templates.TemplateResponse(
        "licenses/form.html",
        {"request": request, "active_page": "licenses", "license_id": license_id, "page_roles": "operator,admin"},
    )


@app.get("/settings")
def settings_page(request: Request):
    return templates.TemplateResponse(
        "settings.html",
        {"request": request, "active_page": "settings", "page_roles": "admin"},
    )


@app.get("/users")
def users_page(request: Request):
    return templates.TemplateResponse(
        "users/list.html",
        {"request": request, "active_page": "users", "page_roles": "admin"},
    )


@app.get("/audit")
def audit_page(request: Request):
    return templates.TemplateResponse(
        "audit/list.html",
        {"request": request, "active_page": "audit", "page_roles": "admin"},
    )


@app.get("/groups/{group_id}/edit")
def groups_edit_page(request: Request, group_id: int):
    return templates.TemplateResponse(
        "groups/edit.html",
        {"request": request, "active_page": "groups", "group_id": group_id, "page_roles": "operator,admin"},
    )
