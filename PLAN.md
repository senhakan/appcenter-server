# AppCenter Server - Gelistirme Plani

**Son Guncelleme:** 2026-02-26
**Referans:** `../PLAN.md` (genel), `../REMOTE_SUPPORT_PLAN.md` (uzak destek detay)
**Canli ortam:** `/opt/appcenter/server` → systemd `appcenter`, nginx reverse proxy

---

## Mevcut Durum

### Tamamlanan Fazlar (1-5)
Tum temel ozellikler uretim ortaminda calisir durumda:
- FastAPI + SQLAlchemy + PostgreSQL WAL
- JWT auth, agent register/heartbeat, task dagitimi
- Uygulama upload/download (Range destekli)
- Deployment CRUD, grup yonetimi
- Web UI (dashboard, agents, apps, deployments, groups, settings, inventory)
- Store API, agent update, scheduler, dashboard stats/timeline

### Faz 6 Kalan Isler

**6.1 Kisa Vade:**
- [x] `app/templates/deployments/list.html`: Deployment listesinde `app_id` yerine uygulama adini goster
- [x] `app/templates/deployments/list.html`: Deployment listesinde hedef grup/agent adini zenginlestir
- [x] `app/templates/deployments/list.html`: Yukaridaki degisikliklerin UI yansimasi
- [x] `app/templates/*/edit.html`: Form validasyonlarini guclendirme (required, format)
- [x] `app/templates/*/edit.html`: API hata mesajlarini form alanlarina detayli yansitma

**6.2 Orta Vade:**
- [x] Grup silme stratejisi: soft delete (`is_active` flag) + membership cleanup
- [x] Uygulama ikon degistirme/silme: `PUT /api/v1/applications/{id}/icon`, `DELETE /api/v1/applications/{id}/icon`
- [x] Liste ekranlarina arama/filtre/siralama (UI: agents/applications/deployments/groups)

**6.3 Yonetilebilirlik:**
- [x] Audit log tablosu: `audit_logs (id, user_id, action, resource_type, resource_id, details_json, created_at)`
- [ ] Audit log middleware: her mutating API call'da otomatik kayit (not: su an mutating endpoint seviyesinde kayit aktif)
- [x] Kritik operasyonlarda UI onay adimi (deployment silme, grup pasife alma, uygulama silme)
- [x] Rol bazli erisim detaylandirma (admin/operator/viewer, backend `403` + UI gorunurluk)

**6.4 Tabler UI Gecisi:**
- 6.1-6.3 tamamlanmadan baslanmaz
- `base.html`, topbar, kart, tablo, form yapilarinin Tabler uyumlu hale getirilmesi

### Faz 7: Kullanici Yonetimi & RBAC

- [x] `app/models.py`: User modeli (admin/operator/viewer rolleri) aktif
- [x] `app/api/v1/users.py`: User CRUD
  - `POST /api/v1/users` (admin only)
  - `GET /api/v1/users` (admin only)
  - `PUT /api/v1/users/{id}` (admin only)
  - `DELETE /api/v1/users/{id}` (admin only, son admin silme engeli)
- [x] `app/auth.py`: `require_role(...)` dependency aktif
- [x] `app/api/v1/web.py`: Mutating endpoint'lerde `operator+`, settings'te `admin` enforcement
- [x] `app/api/v1/inventory.py` ve `app/api/v1/remote_support.py`: role bazli enforcement
- [x] `app/api/v1/auth.py`: `GET /api/v1/auth/me`
- [x] `app/templates/base.html` + `app/static/js/api.js`: menu/aksiyon gorunurlugu role'a gore filtreleme
- [x] `app/templates/users/list.html`: web user management sayfasi
- [x] `app/templates/audit/list.html`: audit log web sayfasi (admin)
- [x] Merkezi page guard standardi: route context `page_roles` + frontend `protectPage()` otomatik guard

---

## Faz 8: Uzak Destek - Server Tarafindaki Isler

Karar notu (2026-02-20):
- Bu asamada hedef, remote support modulunu mevcut helper binary ile uctan uca calistirmaktir.
- UltraVNC rebrand/fork isi server-agent akisindan ayrildi; temel modul stabil olduktan sonra ele alinacak.
- noVNC viewer + internal WS bridge birincil calisma yoludur.
- Guacamole kodu alternatif cozum olarak korunur (varsayilan pasif profil).

### 8.2 Veritabani + API (2 gun)

#### 8.2.1 Model Ekleme

Dosya: `app/models.py`

```python
class RemoteSupportSession(Base):
    __tablename__ = "remote_support_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_approval','approved','rejected','connecting',"
            "'active','ended','timeout','error')",
            name="ck_rs_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_uuid: Mapped[str] = mapped_column(
        ForeignKey("agents.uuid", ondelete="CASCADE"), nullable=False
    )
    admin_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, default="pending_approval", nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vnc_password: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    guac_connection_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    approval_timeout_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    max_duration_min: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
```

Index'ler: `idx_rs_agent`, `idx_rs_status`, `idx_rs_requested`, `idx_rs_admin`

#### 8.2.2 Migration

Dosya: `app/database.py` (mevcut `_run_startup_migrations` fonksiyonuna ek)

```python
def _migrate_remote_support(conn):
    """remote_support_sessions tablosunu olustur (yoksa)."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS remote_support_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_uuid TEXT NOT NULL REFERENCES agents(uuid) ON DELETE CASCADE,
            admin_user_id INTEGER NOT NULL REFERENCES users(id),
            status TEXT NOT NULL DEFAULT 'pending_approval',
            reason TEXT,
            vnc_password TEXT,
            guac_connection_id TEXT,
            requested_at TEXT NOT NULL,
            approval_timeout_at TEXT NOT NULL,
            approved_at TEXT,
            connected_at TEXT,
            ended_at TEXT,
            ended_by TEXT,
            max_duration_min INTEGER NOT NULL DEFAULT 60,
            admin_notes TEXT,
            CONSTRAINT ck_rs_status CHECK (
                status IN ('pending_approval','approved','rejected',
                           'connecting','active','ended','timeout','error')
            )
        )
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rs_agent ON remote_support_sessions(agent_uuid)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rs_status ON remote_support_sessions(status)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rs_requested ON remote_support_sessions(requested_at)"))
```

#### 8.2.3 Service Katmani

Dosya: `app/services/remote_support_service.py` (YENi)

Sorumluluklar:
- `create_session(agent_uuid, admin_user_id, reason, max_duration_min)` → session olustur
  - Agent online kontrolu
  - Aktif oturum cakisma kontrolu
  - VNC one-time password uretimi (`secrets.token_hex(4)` → 8 char hex)
  - `approval_timeout_at = now + 120 saniye`
- `approve_session(session_id, agent_uuid, approved)` → onayla/reddet
  - Status gecisi: pending_approval → approved veya rejected
  - approved ise VNC bilgilerini dondur
- `report_ready(session_id, agent_uuid)` → VNC hazir
  - Status gecisi: approved → connecting
- `mark_active(session_id)` → viewer baglantisi kuruldu
  - Status gecisi: connecting → active
  - `connected_at = now`
- `end_session(session_id, ended_by)` → oturumu bitir
  - Status gecisi: * → ended
  - `ended_at = now`, `vnc_password = None`
- `get_pending_for_agent(agent_uuid)` → heartbeat icin bekleyen oturum
- `generate_novnc_ticket(session_id)` → noVNC ticket/token uret (birincil)
- `generate_guac_token(session_id)` → Encrypted JSON token uret (alternatif)
- `check_timeouts()` → scheduler icin timeout kontrolu
- `check_max_durations()` → scheduler icin sure asim kontrolu

#### 8.2.4 API Router

Dosya: `app/api/v1/remote_support.py` (YENi)

```python
from fastapi import APIRouter, Depends, HTTPException
from app.auth import get_current_user
from app.services.remote_support_service import RemoteSupportService

router = APIRouter(tags=["remote-support"])

# ─── Web UI (Admin) Endpoint'leri ───

@router.post("/remote-support/sessions", status_code=201)
async def create_session(
    body: CreateSessionRequest,
    user = Depends(get_current_user),
    db = Depends(get_db),
):
    """Yeni uzak destek oturumu baslat."""

@router.get("/remote-support/sessions")
async def list_sessions(
    status: str | None = None,
    agent_uuid: str | None = None,
    page: int = 1,
    per_page: int = 20,
    user = Depends(get_current_user),
    db = Depends(get_db),
):
    """Oturum listesi."""

@router.get("/remote-support/sessions/{session_id}")
async def get_session(session_id: int, user = Depends(get_current_user), db = Depends(get_db)):
    """Oturum detayi."""

@router.post("/remote-support/sessions/{session_id}/end")
async def end_session(session_id: int, user = Depends(get_current_user), db = Depends(get_db)):
    """Oturumu sonlandir (admin)."""

@router.get("/remote-support/sessions/{session_id}/novnc-ticket")
async def get_novnc_ticket(session_id: int, user = Depends(get_current_user), db = Depends(get_db)):
    """noVNC ticket/token uret (birincil)."""

@router.get("/remote-support/sessions/{session_id}/guac-token")
async def get_guac_token(session_id: int, user = Depends(get_current_user), db = Depends(get_db)):
    """Guacamole Encrypted JSON token uret (alternatif)."""

# ─── Agent Endpoint'leri ───

@router.post("/agent/remote-support/{session_id}/approve")
async def agent_approve(session_id: int, body: ApproveRequest, agent = Depends(verify_agent)):
    """Agent onay/red bildirimi."""

@router.post("/agent/remote-support/{session_id}/ready")
async def agent_ready(session_id: int, body: ReadyRequest, agent = Depends(verify_agent)):
    """Agent VNC hazir bildirimi."""

@router.post("/agent/remote-support/{session_id}/ended")
async def agent_ended(session_id: int, body: EndedRequest, agent = Depends(verify_agent)):
    """Agent oturum bitis bildirimi."""
```

#### 8.2.5 Schema'lar

Dosya: `app/schemas.py` (mevcut dosyaya ek)

```python
class CreateSessionRequest(BaseModel):
    agent_uuid: str
    reason: str = ""
    max_duration_min: int = Field(default=60, ge=1, le=480)

class ApproveRequest(BaseModel):
    approved: bool

class ReadyRequest(BaseModel):
    vnc_ready: bool
    local_vnc_port: int = 5900

class EndedRequest(BaseModel):
    ended_by: str = "agent"
    reason: str = ""

class SessionResponse(BaseModel):
    id: int
    agent_uuid: str
    agent_hostname: str | None = None
    admin_user: str | None = None
    status: str
    reason: str | None = None
    requested_at: str
    approved_at: str | None = None
    connected_at: str | None = None
    ended_at: str | None = None
    ended_by: str | None = None
    max_duration_min: int
    elapsed_min: float | None = None

class GuacTokenResponse(BaseModel):
    token: str
    tunnel_url: str
```

#### 8.2.6 Heartbeat Degisikligi

Dosya: `app/services/heartbeat_service.py` (mevcut, degisiklik)

Mevcut `build_heartbeat_response()` fonksiyonuna ek:

```python
# Heartbeat response'a remote_support_request ekle
pending = remote_support_service.get_pending_for_agent(agent_uuid)
if pending:
    response["remote_support_request"] = {
        "session_id": pending.id,
        "admin_name": pending.admin_user.full_name or pending.admin_user.username,
        "reason": pending.reason,
        "requested_at": pending.requested_at.isoformat(),
        "timeout_at": pending.approval_timeout_at.isoformat(),
    }

# Oturum sonlandirma sinyali
ended = remote_support_service.get_recently_ended_for_agent(agent_uuid)
if ended:
    response["remote_support_end"] = {
        "session_id": ended.id,
    }
```

#### 8.2.7 main.py Degisikligi

```python
# app/main.py icinde router ekleme
from app.api.v1.remote_support import router as remote_support_router
app.include_router(remote_support_router, prefix=settings.api_v1_prefix)
```

#### 8.2.8 Scheduler Degisikligi

Dosya: `app/tasks/scheduler.py` (mevcut, degisiklik)

```python
# Mevcut scheduler'a iki yeni job ekle:
scheduler.add_job(
    check_approval_timeouts,
    "interval",
    seconds=30,
    id="rs_approval_timeout",
)
scheduler.add_job(
    check_session_max_duration,
    "interval",
    seconds=60,
    id="rs_max_duration",
)
```

#### 8.2.9 Geri Donus Guvenceleri (Baslangica Donus)

Server tarafinda modulun aninda devre disi birakilabilmesi icin:

1. `REMOTE_SUPPORT_ENABLED` feature flag'i eklenir.
2. Flag kapaliyken:
   - `/api/v1/remote-support/*` endpoint'leri `503` doner.
   - `build_heartbeat_response()` remote support alanlarini eklemez.
3. Acik remote support oturumlari tek komutla `ended` durumuna alinabilir.
4. Bu davranis unit test ile dogrulanir (flag on/off).

### 8.4 Viewer Katmani (noVNC birincil, Guacamole alternatif) (2 gun)

#### 8.4.1 Docker Compose Kurulumu

Dosya: `/opt/appcenter/guacamole/docker-compose.yml`

Icerik: `../REMOTE_SUPPORT_PLAN.md` Bolum 5.1'deki tanim.

Adimlar:
1. Docker ve Docker Compose kurulumu (eger yoksa)
2. `docker compose up -d`
3. DB init SQL olustur ve uygula
4. Encrypted JSON auth extension'i kur
5. Shared secret key olustur ve `.env`'ye ekle

#### 8.4.2 Guacamole Token Uretici

Dosya: `app/utils/guac_token.py` (YENi)

```python
"""Guacamole Encrypted JSON auth token uretici."""

import hashlib
import hmac
import json
import os
from base64 import b64encode
from datetime import datetime, timedelta, timezone

from Crypto.Cipher import AES


def _get_secret_key() -> bytes:
    hex_key = os.environ.get("GUAC_JSON_SECRET", "")
    if not hex_key:
        raise RuntimeError("GUAC_JSON_SECRET environment variable not set")
    return bytes.fromhex(hex_key)


def generate_token(
    session_id: int,
    admin_user_id: int,
    vnc_password: str,
    reverse_port: int = 5500,
    expires_in_sec: int = 3600,
) -> str:
    secret = _get_secret_key()

    payload = {
        "username": f"appcenter-admin-{admin_user_id}",
        "expires": int(
            (datetime.now(timezone.utc) + timedelta(seconds=expires_in_sec)).timestamp() * 1000
        ),
        "connections": {
            f"session-{session_id}": {
                "protocol": "vnc",
                "parameters": {
                    "hostname": "",
                    "port": str(reverse_port),
                    "password": vnc_password,
                    "reverse-connect": "true",
                    "listen-timeout": "30000",
                    "color-depth": "24",
                    "cursor": "remote",
                    "read-only": "false",
                },
            }
        },
    }

    payload_bytes = json.dumps(payload).encode("utf-8")

    # HMAC-SHA256 imza
    sig = hmac.new(secret, payload_bytes, hashlib.sha256).digest()

    # Plaintext = imza + payload
    plaintext = sig + payload_bytes

    # PKCS7 padding
    pad_len = 16 - (len(plaintext) % 16)
    plaintext += bytes([pad_len] * pad_len)

    # AES-128-CBC, IV = all zeros
    cipher = AES.new(secret[:16], AES.MODE_CBC, iv=b"\x00" * 16)
    encrypted = cipher.encrypt(plaintext)

    return b64encode(encrypted).decode("ascii")
```

**Yeni dependency:** `requirements.txt`'ye `pycryptodome>=3.20` ekle.

#### 8.4.3 Nginx Konfigurasyonu

Dosya: `/etc/nginx/custom-conf/appcenter.akgun.com.tr.conf` (mevcut, degisiklik)

Eklenecek blok:
```nginx
location /guacamole/ {
    proxy_pass http://127.0.0.1:8080/guacamole/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_read_timeout 86400s;
    proxy_send_timeout 86400s;
}
```

`http` blogu icine (zaten yoksa):
```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
```

### 8.5 Web UI (2 gun)

#### 8.5.1 Template Dosyalari

Yeni dosyalar:
- `app/templates/remote_support/list.html` - Oturum listesi
- `app/templates/remote_support/start.html` - Oturum baslatma formu
- `app/templates/remote_support/view.html` - Uzak masaustu goruntuleme

#### 8.5.2 JavaScript

Dosya: `app/static/js/remote-viewer.js` (YENi)

```javascript
/**
 * AppCenter Remote Support Viewer
 * guacamole-common-js wrapper
 */

class RemoteViewer {
    constructor(containerId, tunnelUrl) {
        this.container = document.getElementById(containerId);
        this.tunnel = new Guacamole.WebSocketTunnel(tunnelUrl);
        this.client = new Guacamole.Client(this.tunnel);
        this.connected = false;
    }

    connect(token) {
        // Display'i DOM'a ekle
        const display = this.client.getDisplay().getElement();
        display.style.width = '100%';
        display.style.height = '100%';
        this.container.appendChild(display);

        // Mouse
        const mouse = new Guacamole.Mouse(display);
        mouse.onEach(['mousedown', 'mousemove', 'mouseup'], (e) => {
            this.client.sendMouseState(e.state);
        });

        // Keyboard (window'a bagla, iframe sorunlarini onle)
        const keyboard = new Guacamole.Keyboard(document);
        keyboard.onkeydown = (keysym) => {
            this.client.sendKeyEvent(1, keysym);
        };
        keyboard.onkeyup = (keysym) => {
            this.client.sendKeyEvent(0, keysym);
        };

        // Error handler
        this.client.onerror = (error) => {
            console.error('Guacamole error:', error);
            this.onError(error);
        };

        // State change handler
        this.client.onstatechange = (state) => {
            if (state === 3) { // CONNECTED
                this.connected = true;
                this.onConnected();
            } else if (state === 5) { // DISCONNECTED
                this.connected = false;
                this.onDisconnected();
            }
        };

        // Baglan
        this.client.connect('data=' + encodeURIComponent(token));
    }

    disconnect() {
        if (this.client) {
            this.client.disconnect();
        }
    }

    setReadOnly(readOnly) {
        // Read-only modda keyboard ve mouse event'lerini gonderme
        // Guacamole client'ta dogrudan bir flag yok,
        // keyboard/mouse handler'lari toggle etmek gerekir
    }

    fitToScreen() {
        const display = this.client.getDisplay();
        const scale = Math.min(
            this.container.offsetWidth / display.getWidth(),
            this.container.offsetHeight / display.getHeight()
        );
        display.scale(scale);
    }

    onConnected() {}       // Override edilebilir
    onDisconnected() {}    // Override edilebilir
    onError(error) {}      // Override edilebilir
}
```

#### 8.5.3 guacamole-common-js Dahil Etme

Secenekler:
1. CDN: `https://cdn.jsdelivr.net/npm/guacamole-common-js@1.5.5/dist/guacamole-common.min.js`
2. Vendor: `app/static/js/vendor/guacamole-common.min.js` (indirip koy)

Onerilen: Vendor (dis bagimliligi azaltir, CDN'e bagimliligi kaldirir).

```bash
# Indirme komutu
cd /root/appcenter/server/app/static/js
mkdir -p vendor
wget -O vendor/guacamole-common.min.js \
    "https://cdn.jsdelivr.net/npm/guacamole-common-js@1.5.5/dist/guacamole-common.min.js"
```

#### 8.5.4 Web Route'lari

Dosya: `app/api/v1/web.py` (mevcut, degisiklik)

```python
# Yeni web route'lari
@router.get("/remote-support", response_class=HTMLResponse)
async def remote_support_list(request: Request):
    return templates.TemplateResponse("remote_support/list.html", {"request": request})

@router.get("/remote-support/start/{agent_uuid}", response_class=HTMLResponse)
async def remote_support_start(request: Request, agent_uuid: str):
    return templates.TemplateResponse("remote_support/start.html", {
        "request": request,
        "agent_uuid": agent_uuid,
    })

@router.get("/remote-support/view/{session_id}", response_class=HTMLResponse)
async def remote_support_view(request: Request, session_id: int):
    return templates.TemplateResponse("remote_support/view.html", {
        "request": request,
        "session_id": session_id,
    })
```

#### 8.5.5 Navbar Ekleme

Dosya: `app/templates/components/topbar.html` (mevcut, degisiklik)

Mevcut menu listesine "Uzak Destek" linki ekle:
```html
<a href="/remote-support" class="nav-link">Uzak Destek</a>
```

#### 8.5.6 Agent Detail Sayfasina Ek

Dosya: `app/templates/agents/detail.html` (mevcut, degisiklik)

Agent online iken "Uzak Destek Baslat" butonu ekle:
```html
{% if agent.status == 'online' %}
<a href="/remote-support/start/{{ agent.uuid }}" class="btn btn-primary">
    Uzak Destek Baslat
</a>
{% endif %}
```

### 8.7 Test (2 gun)

#### Test Dosyasi

Dosya: `tests/test_remote_support.py` (YENi)

```python
"""Remote support API testleri."""

def test_create_session_success(client, auth_headers, online_agent):
    """Online agent icin oturum olusturma."""
    resp = client.post("/api/v1/remote-support/sessions", json={
        "agent_uuid": online_agent.uuid,
        "reason": "Test",
    }, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["session"]["status"] == "pending_approval"

def test_create_session_offline_agent(client, auth_headers, offline_agent):
    """Offline agent icin oturum olusturma reddedilmeli."""
    resp = client.post("/api/v1/remote-support/sessions", json={
        "agent_uuid": offline_agent.uuid,
    }, headers=auth_headers)
    assert resp.status_code == 400

def test_create_session_duplicate(client, auth_headers, online_agent):
    """Ayni agent icin ikinci aktif oturum reddedilmeli."""
    client.post("/api/v1/remote-support/sessions", json={
        "agent_uuid": online_agent.uuid,
    }, headers=auth_headers)
    resp = client.post("/api/v1/remote-support/sessions", json={
        "agent_uuid": online_agent.uuid,
    }, headers=auth_headers)
    assert resp.status_code == 409

def test_approve_session(client, auth_headers, agent_headers, session_id):
    """Agent onay bildirimi."""
    resp = client.post(f"/api/v1/agent/remote-support/{session_id}/approve", json={
        "approved": True,
    }, headers=agent_headers)
    assert resp.status_code == 200
    assert "vnc_password" in resp.json()

def test_reject_session(client, auth_headers, agent_headers, session_id):
    """Agent red bildirimi."""
    resp = client.post(f"/api/v1/agent/remote-support/{session_id}/approve", json={
        "approved": False,
    }, headers=agent_headers)
    assert resp.status_code == 200

def test_novnc_ticket_generation(client, auth_headers, active_session_id):
    """noVNC ticket uretimi (birincil)."""
    resp = client.get(
        f"/api/v1/remote-support/sessions/{active_session_id}/novnc-ticket",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "token" in resp.json()

def test_guac_token_generation(client, auth_headers, active_session_id):
    """Guacamole token uretimi (alternatif)."""
    resp = client.get(
        f"/api/v1/remote-support/sessions/{active_session_id}/guac-token",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "token" in resp.json()
    assert "tunnel_url" in resp.json()

def test_end_session(client, auth_headers, active_session_id):
    """Oturum sonlandirma."""
    resp = client.post(
        f"/api/v1/remote-support/sessions/{active_session_id}/end",
        headers=auth_headers,
    )
    assert resp.status_code == 200

def test_heartbeat_includes_remote_request(client, agent_headers, pending_session):
    """Heartbeat'te remote_support_request alani olmali."""
    resp = client.post("/api/v1/agent/heartbeat", json={...}, headers=agent_headers)
    assert "remote_support_request" in resp.json()
    assert resp.json()["remote_support_request"]["session_id"] == pending_session.id
```

---

## Deploy Kontrol Listesi

Server degisiklikleri deploy edildiginde:

1. [ ] `requirements.txt` guncelle (`pycryptodome` eklendi mi?)
2. [ ] `pip install -r requirements.txt` (canli ortam venv'inde)
3. [ ] DB migration otomatik calisir (startup migration)
4. [ ] noVNC birincil profil `.env` ayarlari dogru mu? (`REMOTE_SUPPORT_NOVNC_MODE`, `REMOTE_SUPPORT_WS_MODE`)
5. [ ] Nginx config guncellendi mi? (`sudo nginx -t && sudo systemctl reload nginx`)
6. [ ] `sudo systemctl restart appcenter`
7. [ ] Smoke test: `curl http://127.0.0.1:8000/health`
8. [ ] Smoke test: noVNC session acilisi + `/novnc-ws` baglanti testi
9. [ ] (Alternatif) Guacamole profili kullanilacaksa `.env` `GUAC_*` ve Docker compose dogrulandi mi?
10. [ ] `pytest tests/ -v`

---

## Dosya Degisiklik Ozeti

| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `app/models.py` | DEGISIKLIK | RemoteSupportSession modeli ekle |
| `app/schemas.py` | DEGISIKLIK | Remote support schema'lari ekle |
| `app/database.py` | DEGISIKLIK | Migration fonksiyonu ekle |
| `app/main.py` | DEGISIKLIK | remote_support router ekle |
| `app/api/v1/remote_support.py` | YENI | API endpoint'leri |
| `app/services/remote_support_service.py` | YENI | Is mantigi |
| `app/services/heartbeat_service.py` | DEGISIKLIK | remote_support_request alanini ekle |
| `app/utils/guac_token.py` | YENI | Encrypted JSON token uretici (alternatif profil) |
| `app/tasks/scheduler.py` | DEGISIKLIK | Timeout job'lari ekle |
| `app/templates/remote_support/list.html` | YENI | Oturum listesi sayfasi |
| `app/templates/remote_support/start.html` | YENI | Oturum baslatma sayfasi |
| `app/templates/remote_support/view.html` | YENI | Uzak masaustu sayfasi |
| `app/static/js/remote-viewer.js` | YENI | Viewer wrapper (noVNC birincil, Guacamole alternatif) |
| `app/static/js/vendor/guacamole-common.min.js` | YENI | Guacamole JS kutuphanesi (alternatif profil) |
| `app/templates/components/topbar.html` | DEGISIKLIK | Navbar'a "Uzak Destek" ekle |
| `app/templates/agents/detail.html` | DEGISIKLIK | "Uzak Destek Baslat" butonu |
| `app/api/v1/web.py` | DEGISIKLIK | Web route'lari ekle |
| `requirements.txt` | DEGISIKLIK | pycryptodome ekle |
| `.env.example` | DEGISIKLIK | GUAC_* degiskenleri ekle |
| `tests/test_remote_support.py` | YENI | Testler |
