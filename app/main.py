from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
import logging
from pathlib import Path
import socket
import time
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from starlette.websockets import WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.v1.agent import router as agent_router
from app.api.v1.asset_registry import router as asset_registry_router
from app.api.v1.agent_ws import router as agent_ws_router
from app.api.v1 import announcements as announcements_router
from app.api.v1.audit import router as audit_router
from app.api.v1.auth import router as auth_router
from app.api.v1.inventory import router as inventory_router
from app.api.v1.remote_support import router as remote_support_router
from app.api.v1.roles import router as roles_router
from app.api.v1.ui_ws import router as ui_ws_router
from app.api.v1.users import router as users_router
from app.api.v1.web import router as web_router
from app.config import get_settings
from app.database import SessionLocal, get_db, init_db, seed_initial_data
from app.models import Setting
from app.tasks.scheduler import start_scheduler, stop_scheduler
from app.utils.file_handler import ensure_upload_dir
from app.services import agent_signal, novnc_service
from app.services import runtime_config_service as runtime_config
from app.services.ws_manager import ws_manager
from sqlalchemy.orm import Session

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
        "permission": "ui.menu.dashboard",
    },
    {
        "key": "agents",
        "title": "Ajanlar",
        "path": "/agents",
        "active_pages": ["agents"],
        "roles": ["admin", "operator", "viewer"],
        "feature_flag": None,
        "permission": "ui.menu.agents",
    },
    {
        "key": "remote_support",
        "title": "Destek Merkezi",
        "path": "/remote-support",
        "active_pages": ["remote_support"],
        "roles": ["admin", "operator", "viewer"],
        "feature_flag": None,
        "permission": "ui.menu.remote_support",
    },
    {
        "key": "announcements",
        "title": "Duyurular",
        "path": "/announcements",
        "active_pages": ["announcements"],
        "roles": ["admin", "operator", "viewer"],
        "feature_flag": None,
        "permission": "ui.menu.announcements",
        "icon": "ti ti-speakerphone",
    },
    {
        "key": "groups",
        "title": "Gruplar",
        "path": "/groups",
        "active_pages": ["groups"],
        "roles": ["admin", "operator", "viewer"],
        "feature_flag": None,
        "permission": "ui.menu.groups",
    },
    {
        "key": "applications",
        "title": "Uygulamalar",
        "path": "/applications",
        "active_pages": ["applications"],
        "roles": ["admin", "operator", "viewer"],
        "feature_flag": None,
        "permission": "ui.menu.applications",
    },
    {
        "key": "deployments",
        "title": "Dagitimlar",
        "path": "/deployments",
        "active_pages": ["deployments"],
        "roles": ["admin", "operator", "viewer"],
        "feature_flag": None,
        "permission": "ui.menu.deployments",
    },
    {
        "key": "asset_management",
        "title": "Asset Management",
        "roles": ["admin", "operator", "viewer"],
        "feature_flag": None,
        "permission": "ui.menu.asset_management",
        "children": [
            {
                "key": "asset_management_hardware",
                "title": "Hardware",
                "path": None,
                "active_pages": [],
                "roles": ["admin", "operator", "viewer"],
                "feature_flag": None,
                "permission": "ui.menu.asset_management",
            },
            {
                "key": "asset_registry",
                "title": "Asset Registry",
                "path": "/asset-registry",
                "active_pages": ["asset_registry"],
                "roles": ["admin", "operator", "viewer"],
                "feature_flag": None,
                "permission": "ui.menu.asset_registry",
            },
            {
                "key": "asset_management_software",
                "title": "Software",
                "path": None,
                "active_pages": [],
                "roles": ["admin", "operator", "viewer"],
                "feature_flag": None,
                "permission": "ui.menu.asset_management",
            },
            {
                "key": "sam_dashboard",
                "title": "SAM Dashboard",
                "path": "/inventory/sam-dashboard",
                "active_pages": ["sam_dashboard"],
                "roles": ["admin", "operator", "viewer"],
                "feature_flag": None,
                "permission": "ui.menu.inventory",
            },
            {
                "key": "sam_catalog",
                "title": "Yazilim Katalogu",
                "path": "/inventory/catalog",
                "active_pages": ["sam_catalog"],
                "roles": ["admin", "operator", "viewer"],
                "feature_flag": None,
                "permission": "ui.menu.inventory",
            },
            {
                "key": "inventory",
                "title": "Yazilim Ozeti",
                "path": "/inventory",
                "active_pages": ["inventory"],
                "roles": ["admin", "operator", "viewer"],
                "feature_flag": None,
                "permission": "ui.menu.inventory",
            },
            {
                "key": "inventory_normalization",
                "title": "Normalizasyon Kurallari",
                "path": "/inventory/normalization",
                "active_pages": ["inventory_normalization"],
                "roles": ["admin", "operator", "viewer"],
                "feature_flag": None,
                "permission": "inventory.manage",
            },
            {
                "key": "sam_compliance",
                "title": "Uyum ve Ihlaller",
                "path": "/inventory/compliance",
                "active_pages": ["sam_compliance"],
                "roles": ["admin", "operator", "viewer"],
                "feature_flag": None,
                "permission": "inventory.view",
            },
            {
                "key": "sam_reports",
                "title": "Rapor Merkezi",
                "path": "/inventory/reports",
                "active_pages": ["sam_reports"],
                "roles": ["admin", "operator", "viewer"],
                "feature_flag": None,
                "permission": "inventory.view",
            },
            {
                "key": "sam_risk",
                "title": "Risk ve Optimizasyon",
                "path": "/inventory/risk",
                "active_pages": ["sam_risk"],
                "roles": ["admin", "operator", "viewer"],
                "feature_flag": None,
                "permission": "inventory.view",
            },
            {
                "key": "licenses",
                "title": "Lisanslar",
                "path": "/licenses",
                "active_pages": ["licenses"],
                "roles": ["admin", "operator", "viewer"],
                "feature_flag": "licenses",
                "permission": "ui.menu.licenses",
            },
        ],
    },
    {
        "key": "management",
        "title": "Yonetim",
        "roles": ["admin", "operator", "viewer"],
        "feature_flag": None,
        "permission": "ui.menu.management",
        "children": [
            {
                "key": "agent_deploy",
                "title": "Ajan Deploy",
                "path": "/agent-deploy",
                "active_pages": ["agent_deploy"],
                "roles": ["admin", "operator", "viewer"],
                "feature_flag": None,
                "permission": "ui.menu.agent_deploy",
            },
            {
                "key": "settings",
                "title": "Ayarlar",
                "path": "/settings",
                "active_pages": ["settings"],
                "roles": ["admin", "operator", "viewer"],
                "feature_flag": None,
                "permission": "ui.menu.settings",
            },
            {"key": "users", "title": "Kullanicilar", "path": "/users", "active_pages": ["users"], "roles": ["admin", "operator", "viewer"], "feature_flag": "users", "permission": "ui.menu.users"},
            {"key": "roles", "title": "Roller", "path": "/roles", "active_pages": ["roles"], "roles": ["admin", "operator", "viewer"], "feature_flag": "rbac", "permission": "ui.menu.roles"},
            {"key": "infra_health", "title": "Sistem Durumu (Yakinda)", "path": None, "active_pages": [], "roles": ["admin"], "feature_flag": "infra", "permission": "infra.view"},
            {"key": "infra_config", "title": "Konfigurasyon (Yakinda)", "path": None, "active_pages": [], "roles": ["admin"], "feature_flag": "infra", "permission": "infra.manage"},
            {"key": "infra_integrations", "title": "Entegrasyonlar (Yakinda)", "path": None, "active_pages": [], "roles": ["admin"], "feature_flag": "infra", "permission": "infra.manage"},
            {
                "key": "infra_session_recordings",
                "title": "Session Recordings",
                "path": "/infra/recordings",
                "active_pages": ["infra_recordings"],
                "roles": ["admin", "operator", "viewer"],
                "feature_flag": "infra",
                "permission": "ui.menu.infra_recordings",
            },
            {"key": "infra_audit", "title": "Audit Log", "path": "/audit", "active_pages": ["audit"], "roles": ["admin", "operator", "viewer"], "feature_flag": "audit", "permission": "ui.menu.audit"},
            {"key": "infra_diag", "title": "Tanilama (Yakinda)", "path": None, "active_pages": [], "roles": ["admin"], "feature_flag": "infra", "permission": "infra.view"},
        ],
    },
]

PAGE_PERMISSION_BY_ACTIVE: dict[str, str] = {
    "dashboard": "ui.page.dashboard",
    "agents": "ui.page.agents",
    "remote_support": "ui.page.remote_support",
    "asset_registry": "ui.page.asset_registry",
    "announcements": "ui.page.announcements",
    "groups": "ui.page.groups",
    "applications": "ui.page.applications",
    "deployments": "ui.page.deployments",
    "inventory": "ui.page.inventory",
    "sam_dashboard": "ui.page.inventory",
    "sam_catalog": "ui.page.inventory",
    "inventory_normalization": "ui.page.inventory",
    "sam_compliance": "ui.page.inventory",
    "sam_reports": "ui.page.inventory",
    "sam_risk": "ui.page.inventory",
    "licenses": "ui.page.licenses",
    "agent_deploy": "ui.page.agent_deploy",
    "settings": "ui.page.settings",
    "users": "ui.page.users",
    "roles": "ui.page.roles",
    "audit": "ui.page.audit",
    "infra_recordings": "ui.page.infra_recordings",
}


def _page_ctx(request: Request, active_page: str, **extra: Any) -> dict[str, Any]:
    ctx: dict[str, Any] = {"request": request, "active_page": active_page}
    permission = PAGE_PERMISSION_BY_ACTIVE.get(active_page, "")
    if permission:
        ctx["page_permissions"] = permission
    ctx.update(extra)
    return ctx


def _enabled_menu_features() -> set[str]:
    features = {"licenses", "infra", "audit", "users", "rbac"}
    db = SessionLocal()
    try:
        if runtime_config.is_remote_support_enabled(db):
            features.add("remote_support")
    finally:
        db.close()
    return features


def _item_visible(item: dict[str, Any], role: str, enabled_features: set[str]) -> bool:
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
    ws_manager.set_loop(asyncio.get_running_loop())
    yield
    agent_signal.clear_all()
    await ws_manager.close_all()
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
app.include_router(asset_registry_router, prefix=settings.api_v1_prefix)
app.include_router(agent_ws_router, prefix=settings.api_v1_prefix + "/agent")
app.include_router(ui_ws_router, prefix=settings.api_v1_prefix + "/ui")
app.include_router(web_router, prefix=settings.api_v1_prefix)
app.include_router(inventory_router, prefix=settings.api_v1_prefix)
app.include_router(remote_support_router, prefix=settings.api_v1_prefix)
app.include_router(users_router, prefix=settings.api_v1_prefix)
app.include_router(roles_router, prefix=settings.api_v1_prefix)
app.include_router(audit_router, prefix=settings.api_v1_prefix)
app.include_router(announcements_router.router)


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
    db = SessionLocal()
    try:
        runtime = runtime_config.get_remote_support_runtime(db)
    finally:
        db.close()
    if runtime.ws_mode != "internal":
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
    return templates.TemplateResponse("dashboard.html", _page_ctx(request, "dashboard"))


@app.get("/dashboard-v2")
def dashboard_v2_page(request: Request):
    return templates.TemplateResponse("dashboard_v2.html", _page_ctx(request, "dashboard"))


@app.get("/agents")
def agents_page(request: Request):
    return templates.TemplateResponse("agents/list.html", _page_ctx(request, "agents"))


@app.get("/agents-v2")
def agents_v2_page(request: Request):
    return templates.TemplateResponse("agents/list_v2.html", _page_ctx(request, "agents"))


@app.get("/remote-support")
def remote_support_list_page(request: Request):
    return templates.TemplateResponse("remote_support/list.html", _page_ctx(request, "remote_support"))


@app.get("/asset-registry")
def asset_registry_overview_page(request: Request):
    return templates.TemplateResponse("asset_registry/overview.html", _page_ctx(request, "asset_registry"))


@app.get("/asset-registry/organization")
def asset_registry_organization_page(request: Request):
    return templates.TemplateResponse(
        "asset_registry/organization.html",
        _page_ctx(request, "asset_registry", page_permissions="asset_registry.view"),
    )


@app.get("/asset-registry/locations")
def asset_registry_locations_page(request: Request):
    return templates.TemplateResponse(
        "asset_registry/locations.html",
        _page_ctx(request, "asset_registry", page_permissions="asset_registry.view"),
    )


@app.get("/asset-registry/people")
def asset_registry_people_page(request: Request):
    return templates.TemplateResponse(
        "asset_registry/people_list.html",
        _page_ctx(request, "asset_registry", page_permissions="asset_registry.view"),
    )


@app.get("/asset-registry/people/{person_id}")
def asset_registry_person_detail_page(request: Request, person_id: int):
    return templates.TemplateResponse(
        "asset_registry/person_detail.html",
        _page_ctx(request, "asset_registry", page_permissions="asset_registry.view", person_id=person_id),
    )


@app.get("/asset-registry/assets")
def asset_registry_assets_page(request: Request):
    return templates.TemplateResponse(
        "asset_registry/assets_list.html",
        _page_ctx(request, "asset_registry", page_permissions="asset_registry.view"),
    )


@app.get("/asset-registry/assets/{asset_id}")
def asset_registry_asset_detail_page(request: Request, asset_id: int):
    return templates.TemplateResponse(
        "asset_registry/asset_detail.html",
        _page_ctx(request, "asset_registry", page_permissions="asset_registry.view", asset_id=asset_id),
    )


@app.get("/asset-registry/matching")
def asset_registry_matching_page(request: Request):
    return templates.TemplateResponse(
        "asset_registry/matching_queue.html",
        _page_ctx(request, "asset_registry", page_permissions="asset_registry.view"),
    )


@app.get("/asset-registry/data-quality")
def asset_registry_data_quality_page(request: Request):
    return templates.TemplateResponse(
        "asset_registry/data_quality.html",
        _page_ctx(request, "asset_registry", page_permissions="asset_registry.view"),
    )


@app.get("/asset-registry/reports")
def asset_registry_reports_page(request: Request):
    return templates.TemplateResponse(
        "asset_registry/reports.html",
        _page_ctx(request, "asset_registry", page_permissions="asset_registry.reports.view"),
    )


@app.get("/asset-registry/settings")
def asset_registry_settings_page(request: Request):
    return templates.TemplateResponse(
        "asset_registry/settings.html",
        _page_ctx(request, "asset_registry", page_permissions="asset_registry.settings.manage"),
    )


@app.get("/asset-registry/help")
def asset_registry_help_page(request: Request):
    return templates.TemplateResponse(
        "asset_registry/help.html",
        _page_ctx(request, "asset_registry", page_permissions="asset_registry.view"),
    )


@app.get("/announcements")
def announcements_list_page(request: Request):
    return templates.TemplateResponse("announcements/list.html", _page_ctx(request, "announcements"))


@app.get("/announcements/create")
def announcements_create_page(request: Request):
    return templates.TemplateResponse(
        "announcements/create.html",
        _page_ctx(request, "announcements", page_permissions="announcements.manage"),
    )


@app.get("/announcements/{announcement_id}")
def announcements_detail_page(request: Request, announcement_id: int):
    return templates.TemplateResponse(
        "announcements/detail.html",
        _page_ctx(request, "announcements", announcement_id=announcement_id),
    )


@app.get("/groups")
def groups_page(request: Request):
    return templates.TemplateResponse("groups/list.html", _page_ctx(request, "groups"))


@app.get("/agents/{agent_uuid}")
def agent_detail_page(request: Request, agent_uuid: str):
    return templates.TemplateResponse(
        "agents/detail.html",
        _page_ctx(request, "agents", agent_uuid=agent_uuid),
    )

@app.get("/remote-support/sessions/{session_id}")
def remote_support_session_page(request: Request, session_id: int):
    db = SessionLocal()
    try:
        runtime = runtime_config.get_remote_support_runtime(db)
    finally:
        db.close()
    return templates.TemplateResponse(
        "remote_support/session.html",
        _page_ctx(
            request,
            "remote_support",
            session_id=session_id,
            novnc_mode=runtime.novnc_mode,
            control_bar_mode=runtime.control_bar_mode,
            log_screen_enabled=runtime.log_screen_enabled,
        ),
    )


@app.get("/applications")
def applications_page(request: Request):
    return templates.TemplateResponse(
        "applications/list.html",
        _page_ctx(request, "applications"),
    )


@app.get("/applications/{app_id}/edit")
def applications_edit_page(request: Request, app_id: int):
    return templates.TemplateResponse(
        "applications/edit.html",
        _page_ctx(request, "applications", app_id=app_id, page_permissions="applications.manage"),
    )


@app.get("/applications/upload")
def applications_upload_page(request: Request):
    return templates.TemplateResponse(
        "applications/upload.html",
        _page_ctx(request, "applications", page_permissions="applications.manage"),
    )


@app.get("/deployments")
def deployments_page(request: Request):
    return templates.TemplateResponse(
        "deployments/list.html",
        _page_ctx(request, "deployments"),
    )


@app.get("/deployments/create")
def deployments_create_page(request: Request):
    return templates.TemplateResponse(
        "deployments/create.html",
        _page_ctx(request, "deployments", page_permissions="deployments.manage"),
    )


@app.get("/deployments/{deployment_id}/edit")
def deployments_edit_page(request: Request, deployment_id: int):
    return templates.TemplateResponse(
        "deployments/edit.html",
        _page_ctx(request, "deployments", deployment_id=deployment_id, page_permissions="deployments.manage"),
    )


@app.get("/inventory")
def inventory_page(request: Request):
    return templates.TemplateResponse("inventory/list.html", _page_ctx(request, "inventory"))


@app.get("/inventory/sam-dashboard")
def inventory_sam_dashboard_page(request: Request):
    return templates.TemplateResponse("inventory/sam_dashboard.html", _page_ctx(request, "sam_dashboard"))


@app.get("/inventory/catalog")
def inventory_catalog_page(request: Request):
    return templates.TemplateResponse("inventory/catalog.html", _page_ctx(request, "sam_catalog"))


@app.get("/inventory/software/{software_name}/agents")
def inventory_software_detail_page(request: Request, software_name: str):
    return templates.TemplateResponse(
        "inventory/software_detail.html",
        _page_ctx(request, "inventory", software_name=software_name),
    )


@app.get("/inventory/normalization")
def inventory_normalization_page(request: Request):
    return templates.TemplateResponse(
        "inventory/normalization.html",
        _page_ctx(request, "inventory_normalization", page_permissions="inventory.manage"),
    )


@app.get("/inventory/compliance")
def inventory_compliance_page(request: Request):
    return templates.TemplateResponse("inventory/compliance.html", _page_ctx(request, "sam_compliance"))


@app.get("/inventory/reports")
def inventory_reports_page(request: Request):
    return templates.TemplateResponse("inventory/reports.html", _page_ctx(request, "sam_reports"))


@app.get("/inventory/risk")
def inventory_risk_page(request: Request):
    return templates.TemplateResponse("inventory/risk.html", _page_ctx(request, "sam_risk"))


@app.get("/licenses")
def licenses_page(request: Request):
    return templates.TemplateResponse("licenses/list.html", _page_ctx(request, "licenses"))


@app.get("/licenses/create")
def licenses_create_page(request: Request):
    return templates.TemplateResponse(
        "licenses/form.html",
        _page_ctx(request, "licenses", license_id=None, page_permissions="licenses.manage"),
    )


@app.get("/licenses/{license_id}/edit")
def licenses_edit_page(request: Request, license_id: int):
    return templates.TemplateResponse(
        "licenses/form.html",
        _page_ctx(request, "licenses", license_id=license_id, page_permissions="licenses.manage"),
    )


@app.get("/settings")
def settings_page(request: Request):
    return templates.TemplateResponse(
        "settings.html",
        _page_ctx(request, "settings"),
    )


@app.get("/agent-deploy")
def agent_deploy_page(request: Request, db: Session = Depends(get_db)):
    rows = (
        db.query(Setting)
        .filter(
            Setting.key.in_(
                [
                    "agent_latest_version_windows",
                    "agent_download_url_windows",
                    "agent_hash_windows",
                    "agent_update_filename_windows",
                    "agent_latest_version_linux",
                    "agent_download_url_linux",
                    "agent_hash_linux",
                    "agent_update_filename_linux",
                ]
            )
        )
        .all()
    )
    values = {x.key: x.value for x in rows}
    return templates.TemplateResponse(
        "agent_deploy.html",
        _page_ctx(request, "agent_deploy", agent_update_settings=values),
    )


@app.get("/users")
def users_page(request: Request):
    return templates.TemplateResponse(
        "users/list.html",
        _page_ctx(request, "users"),
    )


@app.get("/profile")
def profile_page(request: Request):
    return templates.TemplateResponse(
        "profile.html",
        _page_ctx(request, ""),
    )


@app.get("/roles")
def roles_page(request: Request):
    return templates.TemplateResponse(
        "roles/list.html",
        _page_ctx(request, "roles"),
    )


@app.get("/audit")
def audit_page(request: Request):
    return templates.TemplateResponse(
        "audit/list.html",
        _page_ctx(request, "audit"),
    )


@app.get("/infra/recordings")
def infra_recordings_page(request: Request):
    return templates.TemplateResponse(
        "infrastructure/recordings.html",
        _page_ctx(request, "infra_recordings"),
    )


@app.get("/groups/{group_id}/edit")
def groups_edit_page(request: Request, group_id: int):
    return templates.TemplateResponse(
        "groups/edit.html",
        _page_ctx(request, "groups", group_id=group_id, page_permissions="groups.manage"),
    )
