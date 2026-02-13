# AppCenter - Teknik Şartname ve Geliştirme Planı (v1.1)

**Proje Adı:** AppCenter  
**Versiyon:** 1.1 (MVP)  
**Son Güncelleme:** 13 Şubat 2026  
**Mimari:** Client-Server (Agent-Based)  
**Hedef Platform:** Windows 10/11 (Client), Linux (Server)  
**Geliştirme Aracı:** Claude Code (Server ve Agent ayrı session'larda)

---

## 📑 İÇİNDEKİLER

1. [Genel Mimari ve Teknoloji Yığını](#1-genel-mimari-ve-teknoloji-yığını)
2. [Veritabanı Tasarımı (SQLite)](#2-veritabanı-tasarımı-sqlite)
3. [API Protokolü](#3-api-protokolü)
4. [Server Tarafı Detayları](#4-server-tarafı-detayları)
5. [Agent Tarafı Detayları](#5-agent-tarafı-detayları)
6. [Web Arayüzü](#6-web-arayüzü)
7. [Güvenlik](#7-güvenlik)
8. [Deployment & DevOps (Native/Binary)](#8-deployment--devops-nativebinary)
9. [Geliştirme Planı (Sprint Bazlı)](#9-geliştirme-planı-sprint-bazlı)
10. [Claude Code Geliştirme Rehberi](#10-claude-code-geliştirme-rehberi)

---

## ⚠️ v1.0 → v1.1 DEĞİŞİKLİK ÖZETİ

| Değişiklik | Detay |
|---|---|
| Docker kaldırıldı | Tüm server bileşenleri native binary olarak kurulur ve systemd ile yönetilir |
| IPC değişti | File-based IPC → Named Pipes (`\\.\pipe\AppCenterIPC`) |
| SQLite zorunlu ayarlar | WAL mode + busy_timeout=5000 zorunlu |
| ZIP desteği kaldırıldı | `file_type` sadece `msi` ve `exe` |
| Log cleanup | Trigger → Background scheduler (günde 1 kez) |
| Timezone | Server UTC kullanır, tüm zaman damgaları UTC |
| Store endpoint güvenliği | UUID path'ten kaldırıldı → header-based |
| Filename güvenliği | Upload edilen dosyalar `{app_id}_{hash[:8]}.{ext}` formatında saklanır |
| Uninstall | MVP'de sadece "remove" işareti, gerçek uninstall v2.0'da |
| Backup path | Docker path'ler → native Linux path'ler |
| Claude Code uyumu | Server ve Agent ayrı doküman yapısı |

---

## 1. GENEL MİMARİ VE TEKNOLOJİ YIĞINI

### 1.1 Sistem Mimarisi

```
┌─────────────────────────────────────────────────────────┐
│                    MERKEZ SERVER (Linux)                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Web UI       │  │ REST API     │  │  Static      │  │
│  │ (Jinja2+JS)  │  │ (FastAPI)    │  │  Files       │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                  │                  │          │
│         └──────────────────┴──────────────────┘          │
│                            │                             │
│                   ┌────────▼─────────┐                   │
│                   │  SQLite + ORM    │                   │
│                   │  (SQLAlchemy)    │                   │
│                   │  WAL + busy_timeout=5000             │
│                   └──────────────────┘                   │
│                                                          │
│  Runtime: Nginx (reverse proxy) + Uvicorn (ASGI)        │
│  Managed by: systemd                                     │
└─────────────────────────────────────────────────────────┘
                            │
                    HTTPS (Internet/LAN)
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼──────┐   ┌───────▼──────┐   ┌───────▼──────┐
│ Windows      │   │ Windows      │   │ Windows      │
│ PC-001       │   │ PC-002       │   │ PC-003       │
│              │   │              │   │              │
│ ┌──────────┐ │   │ ┌──────────┐ │   │ ┌──────────┐ │
│ │Service   │ │   │ │Service   │ │   │ │Service   │ │
│ │(SYSTEM)  │ │   │ │(SYSTEM)  │ │   │ │(SYSTEM)  │ │
│ └────┬─────┘ │   │ └────┬─────┘ │   │ └────┬─────┘ │
│      │ Named │   │      │ Named │   │      │ Named │
│      │ Pipe  │   │      │ Pipe  │   │      │ Pipe  │
│ ┌────▼─────┐ │   │ ┌────▼─────┐ │   │ ┌────▼─────┐ │
│ │Tray App  │ │   │ │Tray App  │ │   │ │Tray App  │ │
│ │(User)    │ │   │ │(User)    │ │   │ │(User)    │ │
│ └──────────┘ │   │ └──────────┘ │   │ └──────────┘ │
└──────────────┘   └──────────────┘   └──────────────┘
```

### 1.2 Sunucu Tarafı (Server)

**İşletim Sistemi:** Linux (Ubuntu 22.04 LTS / Debian 12+)  
**Kurulum Tipi:** Native binary, systemd ile yönetim (Docker YOK)

**Teknoloji Stack:**
- **Dil:** Python 3.10+
- **Web Framework:** FastAPI 0.109+
- **ORM:** SQLAlchemy 2.0+
- **Veritabanı:** SQLite 3 (WAL mode + busy_timeout=5000 ZORUNLU)
- **Template Engine:** Jinja2
- **CSS Framework:** TailwindCSS 3.4+ (CDN)
- **Web Server:** Nginx (reverse proxy) + Uvicorn (ASGI)
- **Process Manager:** systemd
- **Dosya Sunumu:** Nginx static files veya FastAPI StaticFiles

**Dizin Yapısı (Linux Native):**
```
/opt/appcenter/                     # Ana uygulama dizini
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI application entry
│   ├── config.py                   # Configuration management
│   ├── database.py                 # SQLAlchemy setup (WAL + busy_timeout)
│   ├── models.py                   # Database models
│   ├── schemas.py                  # Pydantic schemas
│   ├── auth.py                     # Authentication logic
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── agent.py            # Agent endpoints
│   │   │   ├── web.py              # Web UI endpoints
│   │   │   └── auth.py             # Auth endpoints
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── agent_service.py
│   │   ├── application_service.py
│   │   ├── deployment_service.py
│   │   └── heartbeat_service.py
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── file_handler.py
│   │   ├── hash_utils.py
│   │   └── logger.py
│   │
│   ├── tasks/
│   │   ├── __init__.py
│   │   └── scheduler.py            # Background tasks (offline check + log cleanup)
│   │
│   ├── templates/                  # Jinja2 templates
│   │   ├── base.html
│   │   ├── components/
│   │   │   ├── navbar.html
│   │   │   ├── sidebar.html
│   │   │   └── stats_card.html
│   │   ├── auth/
│   │   │   └── login.html
│   │   ├── dashboard.html
│   │   ├── agents/
│   │   │   ├── list.html
│   │   │   └── detail.html
│   │   ├── applications/
│   │   │   ├── list.html
│   │   │   ├── upload.html
│   │   │   └── detail.html
│   │   ├── deployments/
│   │   │   ├── list.html
│   │   │   └── create.html
│   │   └── settings.html
│   │
│   └── static/                     # CSS, JS, images
│       ├── css/
│       ├── js/
│       └── icons/
│
├── venv/                           # Python virtual environment
├── requirements.txt
├── .env                            # Environment variables
└── README.md

/var/lib/appcenter/                 # Veri dizini
├── appcenter.db                    # SQLite database
├── uploads/                        # Application installers
└── backups/                        # DB backups

/var/log/appcenter/                 # Log dizini
└── server.log

/etc/appcenter/                     # Konfigürasyon
└── .env                            # Production environment variables

/etc/systemd/system/
├── appcenter.service               # Uvicorn systemd unit
└── appcenter-nginx.conf            # Nginx site config symlink
```

### 1.3 İstemci Tarafı (Agent)

**İşletim Sistemi:** Windows 10/11, Server 2016+

**Teknoloji Stack:**
- **Dil:** Go 1.21+
- **Service Management:** golang.org/x/sys/windows/svc
- **GUI:** github.com/getlantern/systray
- **HTTP Client:** net/http (standart library)
- **Rate Limiting:** golang.org/x/time/rate
- **IPC:** Named Pipes (net package, Windows native)

**Çalışma Modları:**
1. **Windows Service (Backend)**
   - SYSTEM yetkileriyle çalışır
   - Arka planda heartbeat, download, install işlemlerini yürütür
   - Named Pipe server olarak dinler (`\\.\pipe\AppCenterIPC`)
   - Otomatik başlatma (Automatic startup)
   
2. **System Tray Application (Frontend)**
   - Kullanıcı oturum açtığında çalışır
   - Taskbar'da ikon gösterir
   - Store penceresini açar
   - Service ile Named Pipe üzerinden iletişim kurar

**Dizin Yapısı:**
```
appcenter-agent/
├── cmd/
│   ├── service/
│   │   └── main.go                 # Service entry point
│   └── tray/
│       └── main.go                 # Tray app entry point
│
├── internal/
│   ├── config/
│   │   └── config.go               # Config management
│   ├── api/
│   │   └── client.go               # HTTP client
│   ├── heartbeat/
│   │   └── heartbeat.go            # Heartbeat sender
│   ├── installer/
│   │   ├── installer.go            # Install orchestrator
│   │   ├── msi.go                  # MSI handler
│   │   └── exe.go                  # EXE handler
│   ├── downloader/
│   │   └── downloader.go           # Bandwidth-limited downloader
│   ├── system/
│   │   ├── info.go                 # System info collector
│   │   ├── uuid.go                 # UUID generator/storage
│   │   └── disk.go                 # Disk space checker
│   ├── queue/
│   │   └── taskqueue.go            # Task queue with retry logic
│   ├── tray/
│   │   ├── tray.go                 # System tray
│   │   └── store.go                # Store window
│   └── ipc/
│       └── namedpipe.go            # Named Pipe IPC (Service ↔ Tray)
│
├── pkg/
│   └── utils/
│       ├── hash.go                 # SHA256 verification
│       └── logger.go               # Logging utility
│
├── configs/
│   └── config.yaml.template        # Default config template
│
├── build/
│   ├── build.bat                   # Build script
│   └── service-install.bat         # Service installation script
│
├── go.mod
├── go.sum
└── README.md
```

**Agent Kurulum Yolları:**
- **Çalışma Dizini:** `C:\Program Files\AppCenter\`
- **Veri Dizini:** `C:\ProgramData\AppCenter\`
  - `downloads\` - Geçici indirilen dosyalar
  - `logs\` - Log dosyaları
  - `config.yaml` - Konfigürasyon
- **Registry:** `HKLM\SOFTWARE\AppCenter\`
  - `UUID` - Agent benzersiz kimliği
  - `SecretKey` - Şifreli authentication key

---

## 2. VERİTABANI TASARIMI (SQLite)

### 2.1 Zorunlu SQLite Ayarları

```sql
-- Uygulama başlatıldığında MUTLAKA çalıştırılmalı
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
PRAGMA foreign_keys=ON;
PRAGMA synchronous=NORMAL;
```

**Python (database.py) içinde:**
```python
from sqlalchemy import create_engine, event

engine = create_engine(
    "sqlite:////var/lib/appcenter/appcenter.db",
    connect_args={"check_same_thread": False}
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()
```

### 2.2 Tam Şema (SQL)

```sql
-- =====================================================
-- SETTINGS TABLE - Global Ayarlar
-- =====================================================
CREATE TABLE settings (
    key TEXT PRIMARY KEY NOT NULL,
    value TEXT NOT NULL,
    description TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Default settings (Tüm zamanlar UTC)
INSERT INTO settings (key, value, description) VALUES
('bandwidth_limit_kbps', '1024', 'Agent download bandwidth limit (KB/s)'),
('work_hour_start', '09:00', 'Work hours start time (HH:MM) - UTC'),
('work_hour_end', '18:00', 'Work hours end time (HH:MM) - UTC'),
('heartbeat_interval_sec', '60', 'Agent heartbeat interval (seconds)'),
('agent_timeout_sec', '300', 'Agent offline threshold (5 minutes)'),
('download_timeout_sec', '1800', 'Max download timeout (30 minutes)'),
('install_timeout_sec', '1800', 'Max install timeout (30 minutes)'),
('max_retry_count', '3', 'Failed task max retry count'),
('log_retention_days', '30', 'Keep logs for X days'),
('enable_auto_cleanup', 'true', 'Delete installers after successful install'),
('agent_latest_version', '1.0.0', 'Latest available agent version'),
('agent_download_url', '', 'Agent self-update download URL'),
('agent_hash', '', 'Agent installer SHA256 hash'),
('server_timezone', 'UTC', 'Server timezone (always UTC)');

CREATE INDEX idx_settings_key ON settings(key);

-- =====================================================
-- GROUPS TABLE - Agent Gruplandırma
-- =====================================================
CREATE TABLE groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO groups (name, description) VALUES
('Genel', 'Tüm bilgisayarlar'),
('IT', 'Bilgi İşlem'),
('Muhasebe', 'Muhasebe departmanı'),
('Satış', 'Satış departmanı');

CREATE INDEX idx_group_name ON groups(name);

-- =====================================================
-- AGENTS TABLE - İstemci Envanteri
-- =====================================================
CREATE TABLE agents (
    uuid TEXT PRIMARY KEY NOT NULL,
    hostname TEXT NOT NULL,
    ip_address TEXT,
    os_user TEXT,
    os_version TEXT,
    version TEXT,
    last_seen DATETIME,
    status TEXT DEFAULT 'offline' CHECK(status IN ('online', 'offline')),
    group_id INTEGER,
    secret_key TEXT,
    cpu_model TEXT,
    ram_gb INTEGER,
    disk_free_gb INTEGER,
    tags TEXT,                                 -- JSON: ["windows_11", "ssd"]
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE SET NULL
);

CREATE INDEX idx_agent_status ON agents(status);
CREATE INDEX idx_agent_last_seen ON agents(last_seen);
CREATE INDEX idx_agent_group ON agents(group_id);

-- =====================================================
-- APPLICATIONS TABLE - Uygulama Kataloğu
-- file_type: sadece 'msi' ve 'exe' (zip kaldırıldı)
-- filename: güvenli format -> {app_id}_{hash[:8]}.{ext}
-- =====================================================
CREATE TABLE applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name TEXT NOT NULL,
    description TEXT,
    filename TEXT NOT NULL,                    -- Güvenli: {id}_{hash[:8]}.ext
    original_filename TEXT,                    -- Orijinal yüklenen dosya adı
    version TEXT NOT NULL,
    file_hash TEXT NOT NULL,                   -- SHA256 (zorunlu)
    file_size_bytes INTEGER,
    file_type TEXT DEFAULT 'msi' CHECK(file_type IN ('msi', 'exe')),
    install_args TEXT,
    uninstall_args TEXT,
    is_visible_in_store BOOLEAN DEFAULT 1,
    icon_url TEXT,
    category TEXT,
    dependencies TEXT,                         -- JSON: [app_id, app_id]
    min_os_version TEXT,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_app_name ON applications(display_name);
CREATE INDEX idx_app_visible ON applications(is_visible_in_store);
CREATE INDEX idx_app_active ON applications(is_active);

-- =====================================================
-- DEPLOYMENTS TABLE - Dağıtım Kuralları
-- =====================================================
CREATE TABLE deployments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id INTEGER NOT NULL,
    target_type TEXT NOT NULL CHECK(target_type IN ('All', 'Group', 'Agent')),
    target_id TEXT,
    is_mandatory BOOLEAN DEFAULT 0,
    force_update BOOLEAN DEFAULT 0,
    priority INTEGER DEFAULT 5,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT,
    FOREIGN KEY (app_id) REFERENCES applications(id) ON DELETE CASCADE
);

CREATE INDEX idx_deployment_app ON deployments(app_id);
CREATE INDEX idx_deployment_target ON deployments(target_type, target_id);
CREATE INDEX idx_deployment_active ON deployments(is_active);

-- =====================================================
-- AGENT_APPLICATIONS TABLE - Agent-Application İlişkisi
-- =====================================================
CREATE TABLE agent_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_uuid TEXT NOT NULL,
    app_id INTEGER NOT NULL,
    deployment_id INTEGER,
    status TEXT DEFAULT 'pending' CHECK(status IN 
        ('pending', 'downloading', 'installing', 'installed', 'failed', 'uninstalling', 'removed')),
    installed_version TEXT,
    last_attempt DATETIME,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_uuid) REFERENCES agents(uuid) ON DELETE CASCADE,
    FOREIGN KEY (app_id) REFERENCES applications(id) ON DELETE CASCADE,
    FOREIGN KEY (deployment_id) REFERENCES deployments(id) ON DELETE SET NULL,
    UNIQUE(agent_uuid, app_id)
);

CREATE INDEX idx_agent_app_status ON agent_applications(status);
CREATE INDEX idx_agent_app_agent ON agent_applications(agent_uuid);
CREATE INDEX idx_agent_app_app ON agent_applications(app_id);

-- =====================================================
-- TASK_HISTORY TABLE - İşlem Logları
-- NOT: Log temizliği background scheduler ile yapılır (trigger YOK)
-- =====================================================
CREATE TABLE task_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_uuid TEXT,
    app_id INTEGER,
    deployment_id INTEGER,
    action TEXT NOT NULL CHECK(action IN ('install', 'uninstall', 'update', 'self_update')),
    status TEXT NOT NULL CHECK(status IN ('pending', 'downloading', 'success', 'failed', 'timeout')),
    message TEXT,
    exit_code INTEGER,
    started_at DATETIME,
    completed_at DATETIME,
    download_duration_sec INTEGER,
    install_duration_sec INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (agent_uuid) REFERENCES agents(uuid) ON DELETE SET NULL,
    FOREIGN KEY (app_id) REFERENCES applications(id) ON DELETE SET NULL,
    FOREIGN KEY (deployment_id) REFERENCES deployments(id) ON DELETE SET NULL
);

CREATE INDEX idx_task_agent ON task_history(agent_uuid);
CREATE INDEX idx_task_app ON task_history(app_id);
CREATE INDEX idx_task_status ON task_history(status);
CREATE INDEX idx_task_created ON task_history(created_at);

-- NOT: cleanup_old_logs trigger KALDIRILDI
-- Log temizliği background scheduler'da günde 1 kez çalışır:
-- DELETE FROM task_history WHERE created_at < datetime('now', '-30 days');

-- =====================================================
-- USERS TABLE - Web Arayüzü Kullanıcıları
-- =====================================================
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    email TEXT,
    role TEXT DEFAULT 'viewer' CHECK(role IN ('admin', 'operator', 'viewer')),
    is_active BOOLEAN DEFAULT 1,
    last_login DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO users (username, password_hash, full_name, role) VALUES
('admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5ztP3qI8VGUbK', 'Sistem Yöneticisi', 'admin');

CREATE INDEX idx_user_username ON users(username);
```

### 2.3 Veritabanı İlişkileri

```
groups (1) ──┐
             ├──< (N) agents
             └──< (N) deployments (target_type='Group')

agents (1) ──┐
             ├──< (N) agent_applications
             ├──< (N) task_history
             └──< (N) deployments (target_type='Agent')

applications (1) ──┐
                   ├──< (N) deployments
                   ├──< (N) agent_applications
                   └──< (N) task_history

deployments (1) ──┐
                  ├──< (N) agent_applications
                  └──< (N) task_history
```

---

## 3. API PROTOKOLÜ

Tüm API endpoint'leri JSON formatında veri alışverişi yapar.  
**Tüm zaman damgaları UTC formatında olmalıdır.**

### 3.1 Agent Endpoints

#### 3.1.1 Agent Registration (İlk Kayıt)

**Endpoint:** `POST /api/v1/agent/register`

**Request:**
```json
{
    "uuid": "550e8400-e29b-41d4-a716-446655440000",
    "hostname": "PC-MUHASEBE-01",
    "os_version": "Windows 11 Pro 23H2",
    "agent_version": "1.0.0",
    "cpu_model": "Intel Core i7-12700",
    "ram_gb": 16,
    "disk_free_gb": 250
}
```

**Response:**
```json
{
    "status": "success",
    "message": "Agent registered successfully",
    "secret_key": "sk_a7b3c9d2e1f4g5h6i7j8k9l0m1n2o3p4",
    "config": {
        "heartbeat_interval_sec": 60,
        "bandwidth_limit_kbps": 1024,
        "work_hour_start": "09:00",
        "work_hour_end": "18:00"
    }
}
```

#### 3.1.2 Heartbeat (Her 60 saniyede bir)

**Endpoint:** `POST /api/v1/agent/heartbeat`

**Request Headers:**
```
Content-Type: application/json
X-Agent-UUID: 550e8400-e29b-41d4-a716-446655440000
X-Agent-Secret: sk_a7b3c9d2e1f4g5h6i7j8k9l0m1n2o3p4
```

**Request Body:**
```json
{
    "hostname": "PC-MUHASEBE-01",
    "ip_address": "192.168.1.105",
    "os_user": "ahmet.yilmaz",
    "agent_version": "1.0.0",
    "disk_free_gb": 245,
    "cpu_usage": 35.5,
    "ram_usage": 62.3,
    "current_status": "Idle",
    "apps_changed": true,
    "installed_apps": [
        {"app_id": 5, "version": "23.01"},
        {"app_id": 7, "version": "120.0.6099"}
    ]
}
```

**NOT:** `apps_changed` alanı eklendi. `false` ise `installed_apps` boş array gönderilebilir, server mevcut kayıtları korur. Sadece install/uninstall sonrası `true` gönderilir.

**Response:**
```json
{
    "status": "ok",
    "server_time": "2026-02-13T14:30:00Z",
    "config": {
        "bandwidth_limit_kbps": 1024,
        "work_hour_start": "09:00",
        "work_hour_end": "18:00",
        "latest_agent_version": "1.0.0",
        "agent_download_url": null,
        "agent_hash": null
    },
    "commands": [
        {
            "task_id": 1001,
            "action": "install",
            "app_id": 12,
            "app_name": "7-Zip",
            "app_version": "23.01",
            "download_url": "https://server.company.com/api/v1/agent/download/12",
            "file_hash": "sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
            "file_size_bytes": 2097152,
            "install_args": "/S",
            "force_update": false,
            "priority": 5
        }
    ]
}
```

#### 3.1.3 Download Application

**Endpoint:** `GET /api/v1/agent/download/{app_id}`

**Request Headers:**
```
X-Agent-UUID: 550e8400-e29b-41d4-a716-446655440000
X-Agent-Secret: sk_a7b3c9d2e1f4g5h6i7j8k9l0m1n2o3p4
Range: bytes=0-1048575  (Resume desteği için)
```

**Response:**
- **Status:** 200 OK (veya 206 Partial Content)
- **Headers:**
  ```
  Content-Type: application/octet-stream
  Content-Length: 2097152
  Content-Disposition: attachment; filename="7zip_23.01.msi"
  Accept-Ranges: bytes
  Content-Range: bytes 0-1048575/2097152
  ```
- **Body:** Binary file stream

#### 3.1.4 Report Task Status

**Endpoint:** `POST /api/v1/agent/task/{task_id}/status`

**Request Headers:**
```
Content-Type: application/json
X-Agent-UUID: 550e8400-e29b-41d4-a716-446655440000
X-Agent-Secret: sk_a7b3c9d2e1f4g5h6i7j8k9l0m1n2o3p4
```

**Request Body (Success):**
```json
{
    "status": "success",
    "progress": 100,
    "message": "Installation completed successfully",
    "exit_code": 0,
    "installed_version": "23.01",
    "download_duration_sec": 45,
    "install_duration_sec": 120
}
```

**Request Body (Failed):**
```json
{
    "status": "failed",
    "progress": 0,
    "message": "Installation failed: Access denied",
    "exit_code": 1603,
    "error": "MSI installer returned error code 1603"
}
```

#### 3.1.5 Get Store Applications

**Endpoint:** `GET /api/v1/agent/store`

**NOT:** UUID artık path'te değil, sadece header'da.

**Request Headers:**
```
X-Agent-UUID: 550e8400-e29b-41d4-a716-446655440000
X-Agent-Secret: sk_a7b3c9d2e1f4g5h6i7j8k9l0m1n2o3p4
```

**Response:**
```json
{
    "apps": [
        {
            "id": 5,
            "display_name": "7-Zip",
            "version": "23.01",
            "description": "Ücretsiz arşivleme programı",
            "icon_url": "/static/icons/7zip.png",
            "file_size_mb": 2,
            "category": "Utilities",
            "installed": false,
            "installed_version": null,
            "can_uninstall": false
        }
    ]
}
```

### 3.2 Web UI Endpoints

#### Authentication

```
POST /api/v1/auth/login
Request: {"username": "admin", "password": "admin123"}
Response: {"access_token": "jwt_token_here", "token_type": "bearer"}

POST /api/v1/auth/logout
Headers: Authorization: Bearer {token}
```

#### Dashboard

```
GET /api/v1/dashboard/stats
Response:
{
    "total_agents": 150,
    "online_agents": 142,
    "offline_agents": 8,
    "total_applications": 25,
    "pending_tasks": 12,
    "failed_tasks": 2,
    "active_deployments": 5
}
```

#### CRUD Endpoints

```
GET    /api/v1/agents?status=online&group_id=2&limit=50&offset=0
GET    /api/v1/agents/{agent_uuid}
PUT    /api/v1/agents/{agent_uuid}
DELETE /api/v1/agents/{agent_uuid}
GET    /api/v1/agents/{agent_uuid}/applications
GET    /api/v1/agents/{agent_uuid}/logs

GET    /api/v1/applications
POST   /api/v1/applications              (multipart file upload)
GET    /api/v1/applications/{app_id}
PUT    /api/v1/applications/{app_id}
DELETE /api/v1/applications/{app_id}

GET    /api/v1/deployments
POST   /api/v1/deployments
GET    /api/v1/deployments/{deployment_id}
PUT    /api/v1/deployments/{deployment_id}
DELETE /api/v1/deployments/{deployment_id}
```

---

## 4. SERVER TARAFI DETAYLARI

### 4.1 Python Dependencies (requirements.txt)

```txt
fastapi==0.109.0
uvicorn[standard]==0.27.0
sqlalchemy==2.0.25
pydantic==2.5.3
pydantic-settings==2.1.0
python-multipart==0.0.6
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
aiofiles==23.2.1
apscheduler==3.10.4
jinja2==3.1.3
```

### 4.2 Kritik Fonksiyonlar

#### 4.2.1 Heartbeat Handler

```python
async def process_heartbeat(agent_data: HeartbeatRequest, db: Session):
    """
    1. Agent'ı veritabanında bul/güncelle
    2. last_seen timestamp'i güncelle (UTC)
    3. status = 'online' yap
    4. apps_changed=true ise installed_apps'i sync et
    5. Active deployment'lara bak, pending task'ları belirle
    6. Self-update gerekiyor mu kontrol et
    7. Config ayarlarını döndür
    """
    pass
```

#### 4.2.2 Background Scheduler Tasks

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

# Her 2 dakikada bir: Offline agent detection
async def check_offline_agents():
    timeout_sec = get_setting('agent_timeout_sec', 300)
    threshold = datetime.utcnow() - timedelta(seconds=timeout_sec)
    
    agents = db.query(Agent).filter(
        Agent.last_seen < threshold,
        Agent.status == 'online'
    ).all()
    
    for agent in agents:
        agent.status = 'offline'
    db.commit()

# Günde 1 kez: Log temizliği (gece 03:00 UTC)
async def cleanup_old_logs():
    retention_days = int(get_setting('log_retention_days', 30))
    db.execute(
        text("DELETE FROM task_history WHERE created_at < datetime('now', :days)"),
        {"days": f"-{retention_days} days"}
    )
    db.commit()

scheduler.add_job(check_offline_agents, 'interval', minutes=2)
scheduler.add_job(cleanup_old_logs, 'cron', hour=3, minute=0)
scheduler.start()
```

#### 4.2.3 Güvenli File Upload Handler

```python
import hashlib
import os
import re

ALLOWED_EXTENSIONS = {'.msi', '.exe'}
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB

def sanitize_filename(app_id: int, file_hash: str, original_filename: str) -> str:
    """Güvenli dosya adı oluştur - path traversal engellenir"""
    ext = os.path.splitext(original_filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Invalid extension: {ext}")
    # Format: {app_id}_{hash_ilk_8_karakter}.{ext}
    safe_hash = re.sub(r'[^a-f0-9]', '', file_hash[:8])
    return f"{app_id}_{safe_hash}{ext}"

async def upload_application(file: UploadFile, display_name: str, version: str, ...):
    # 1. Extension kontrolü
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, "Invalid file type. Only .msi and .exe allowed.")
    
    # 2. Geçici dosyaya yaz + hash hesapla
    temp_path = f"/var/lib/appcenter/uploads/temp_{uuid4()}"
    hash_sha256 = hashlib.sha256()
    total_size = 0
    
    async with aiofiles.open(temp_path, 'wb') as f:
        while chunk := await file.read(1024 * 1024):
            total_size += len(chunk)
            if total_size > MAX_FILE_SIZE:
                os.remove(temp_path)
                raise HTTPException(413, "File too large. Max 2GB.")
            await f.write(chunk)
            hash_sha256.update(chunk)
    
    file_hash = hash_sha256.hexdigest()
    
    # 3. DB'ye kaydet (ID almak için)
    app = Application(
        display_name=display_name,
        original_filename=file.filename,
        filename="temp",  # geçici
        version=version,
        file_hash=f"sha256:{file_hash}",
        file_size_bytes=total_size,
        file_type=ext.lstrip('.'),
        ...
    )
    db.add(app)
    db.flush()  # ID oluşsun
    
    # 4. Güvenli dosya adı oluştur ve taşı
    safe_filename = sanitize_filename(app.id, file_hash, file.filename)
    final_path = f"/var/lib/appcenter/uploads/{safe_filename}"
    os.rename(temp_path, final_path)
    
    app.filename = safe_filename
    db.commit()
```

#### 4.2.4 Deployment Task Generator

```python
async def get_pending_tasks_for_agent(agent_uuid: str, db: Session):
    """
    Agent için bekleyen görevleri belirle.
    task_id = task_history tablosundaki auto-increment ID kullanılır.
    """
    tasks = []
    agent = db.query(Agent).filter(Agent.uuid == agent_uuid).first()
    
    deployments = db.query(Deployment).filter(
        Deployment.is_active == True
    ).all()
    
    for deployment in deployments:
        # Target matching
        if deployment.target_type == 'All':
            match = True
        elif deployment.target_type == 'Group':
            match = (agent.group_id == int(deployment.target_id))
        elif deployment.target_type == 'Agent':
            match = (agent.uuid == deployment.target_id)
        else:
            match = False
        
        if not match:
            continue
        
        # Mevcut durumu kontrol et
        agent_app = db.query(AgentApplication).filter(
            AgentApplication.agent_uuid == agent_uuid,
            AgentApplication.app_id == deployment.app_id
        ).first()
        
        app = deployment.application
        
        if agent_app and agent_app.status == 'installed' and agent_app.installed_version == app.version:
            continue  # Zaten güncel
        
        # agent_applications'a kayıt yoksa oluştur
        if not agent_app:
            agent_app = AgentApplication(
                agent_uuid=agent_uuid,
                app_id=deployment.app_id,
                deployment_id=deployment.id,
                status='pending'
            )
            db.add(agent_app)
            db.flush()
        
        if agent_app.status in ('installed',) and agent_app.installed_version != app.version:
            action = 'update'
        else:
            action = 'install'
        
        # task_history'ye kaydet, ID'yi task_id olarak kullan
        task_record = TaskHistory(
            agent_uuid=agent_uuid,
            app_id=app.id,
            deployment_id=deployment.id,
            action=action,
            status='pending',
            started_at=datetime.utcnow()
        )
        db.add(task_record)
        db.flush()
        
        task = {
            "task_id": task_record.id,
            "action": action,
            "app_id": app.id,
            "app_name": app.display_name,
            "app_version": app.version,
            "download_url": f"/api/v1/agent/download/{app.id}",
            "file_hash": app.file_hash,
            "file_size_bytes": app.file_size_bytes,
            "install_args": app.install_args,
            "force_update": deployment.force_update,
            "priority": deployment.priority
        }
        tasks.append(task)
    
    db.commit()
    tasks.sort(key=lambda x: x['priority'])
    return tasks
```

### 4.3 File Download with Resume Support

```python
from fastapi.responses import StreamingResponse
import re

async def download_application(app_id: int, range_header: str = None):
    app = db.query(Application).filter(Application.id == app_id).first()
    file_path = f"/var/lib/appcenter/uploads/{app.filename}"
    file_size = app.file_size_bytes
    
    start = 0
    end = file_size - 1
    
    if range_header:
        range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
        if range_match:
            start = int(range_match.group(1))
            if range_match.group(2):
                end = int(range_match.group(2))
    
    async def file_iterator():
        async with aiofiles.open(file_path, 'rb') as f:
            await f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk_size = min(1024 * 1024, remaining)
                chunk = await f.read(chunk_size)
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
    
    headers = {
        'Content-Length': str(end - start + 1),
        'Content-Range': f'bytes {start}-{end}/{file_size}',
        'Accept-Ranges': 'bytes',
        'Content-Disposition': f'attachment; filename="{app.filename}"'
    }
    
    status_code = 206 if start > 0 else 200
    return StreamingResponse(file_iterator(), status_code=status_code,
                            headers=headers, media_type='application/octet-stream')
```

---

## 5. AGENT TARAFI DETAYLARI

### 5.1 Go Dependencies (go.mod)

```go
module appcenter-agent

go 1.21

require (
    github.com/getlantern/systray v1.2.2
    github.com/google/uuid v1.5.0
    golang.org/x/sys v0.16.0
    golang.org/x/time v0.5.0
    gopkg.in/yaml.v3 v3.0.1
    github.com/Microsoft/go-winio v0.6.1  // Named Pipes desteği
)
```

### 5.2 Agent İş Akışı (Service)

```
┌─────────────────────────────────────────────────────────┐
│                    SERVICE MAIN LOOP                     │
└─────────────────────────────────────────────────────────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │  Initialize      │
                  │  - Load Config   │
                  │  - Get/Gen UUID  │
                  │  - Register      │
                  │  - Start Named   │
                  │    Pipe Server   │
                  └────────┬─────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
    ┌──────────────┐ ┌──────────┐ ┌──────────────┐
    │ Heartbeat    │ │ Named    │ │ Task         │
    │ Timer        │ │ Pipe     │ │ Processor    │
    │ (60 sec)     │ │ Listener │ │ (goroutine)  │
    └──────┬───────┘ └────┬─────┘ └──────┬───────┘
           │              │              │
           ▼              ▼              ▼
    Send heartbeat   Handle Tray    Download →
    → Get commands    requests      Verify →
    → Queue tasks     (install      Install →
                       from store)  Report
```

### 5.3 Named Pipe IPC (Yeni)

```go
// internal/ipc/namedpipe.go

import (
    "net"
    "github.com/Microsoft/go-winio"
    "encoding/json"
)

const PipeName = `\\.\pipe\AppCenterIPC`

// === SERVICE TARAFI (Server) ===

type IPCRequest struct {
    Action    string `json:"action"`     // "install_from_store", "get_status", "get_store"
    AppID     int    `json:"app_id,omitempty"`
    Timestamp string `json:"timestamp"`
}

type IPCResponse struct {
    Status  string      `json:"status"`   // "ok", "error"
    Message string      `json:"message,omitempty"`
    Data    interface{} `json:"data,omitempty"`
}

func StartPipeServer(handler func(IPCRequest) IPCResponse) error {
    config := &winio.PipeConfig{
        SecurityDescriptor: "D:P(A;;GA;;;WD)", // Everyone read/write
        MessageMode:        true,
        InputBufferSize:    65536,
        OutputBufferSize:   65536,
    }
    
    listener, err := winio.ListenPipe(PipeName, config)
    if err != nil {
        return err
    }
    
    go func() {
        for {
            conn, err := listener.Accept()
            if err != nil {
                continue
            }
            go handleConnection(conn, handler)
        }
    }()
    
    return nil
}

func handleConnection(conn net.Conn, handler func(IPCRequest) IPCResponse) {
    defer conn.Close()
    
    decoder := json.NewDecoder(conn)
    encoder := json.NewEncoder(conn)
    
    var req IPCRequest
    if err := decoder.Decode(&req); err != nil {
        return
    }
    
    resp := handler(req)
    encoder.Encode(resp)
}

// === TRAY TARAFI (Client) ===

func SendIPCRequest(req IPCRequest) (*IPCResponse, error) {
    timeout := 5 * time.Second
    conn, err := winio.DialPipe(PipeName, &timeout)
    if err != nil {
        return nil, err
    }
    defer conn.Close()
    
    encoder := json.NewEncoder(conn)
    decoder := json.NewDecoder(conn)
    
    if err := encoder.Encode(req); err != nil {
        return nil, err
    }
    
    var resp IPCResponse
    if err := decoder.Decode(&resp); err != nil {
        return nil, err
    }
    
    return &resp, nil
}
```

### 5.4 UUID Generation & Storage

```go
// internal/system/uuid.go

func GetOrCreateUUID() (string, error) {
    k, err := registry.OpenKey(registry.LOCAL_MACHINE, 
        `SOFTWARE\AppCenter`, registry.READ)
    if err == nil {
        defer k.Close()
        val, _, err := k.GetStringValue("UUID")
        if err == nil && val != "" {
            return val, nil
        }
    }
    
    newUUID := uuid.New().String()
    
    k, _, err = registry.CreateKey(registry.LOCAL_MACHINE, 
        `SOFTWARE\AppCenter`, registry.WRITE)
    if err != nil {
        return "", err
    }
    defer k.Close()
    
    err = k.SetStringValue("UUID", newUUID)
    return newUUID, err
}
```

### 5.5 Bandwidth-Limited Downloader

```go
// internal/downloader/downloader.go

type BandwidthLimitedReader struct {
    Reader  io.Reader
    Limiter *rate.Limiter
}

func (r *BandwidthLimitedReader) Read(p []byte) (int, error) {
    n, err := r.Reader.Read(p)
    if n > 0 {
        r.Limiter.WaitN(context.Background(), n)
    }
    return n, err
}

func DownloadFile(url, destPath string, limitKBps int, uuid, secretKey string) error {
    limiter := rate.NewLimiter(rate.Limit(limitKBps*1024), limitKBps*1024)
    
    var rangeHeader string
    if fileInfo, err := os.Stat(destPath); err == nil {
        rangeHeader = fmt.Sprintf("bytes=%d-", fileInfo.Size())
    }
    
    req, _ := http.NewRequest("GET", url, nil)
    req.Header.Set("X-Agent-UUID", uuid)
    req.Header.Set("X-Agent-Secret", secretKey)
    if rangeHeader != "" {
        req.Header.Set("Range", rangeHeader)
    }
    
    resp, err := http.DefaultClient.Do(req)
    if err != nil {
        return err
    }
    defer resp.Body.Close()
    
    flag := os.O_CREATE | os.O_WRONLY
    if rangeHeader != "" {
        flag |= os.O_APPEND
    } else {
        flag |= os.O_TRUNC
    }
    
    out, err := os.OpenFile(destPath, flag, 0644)
    if err != nil {
        return err
    }
    defer out.Close()
    
    limitedReader := &BandwidthLimitedReader{Reader: resp.Body, Limiter: limiter}
    _, err = io.Copy(out, limitedReader)
    return err
}
```

### 5.6 Hash Verification

```go
func VerifyFileHash(filePath, expectedHash string) (bool, error) {
    expectedHash = strings.TrimPrefix(expectedHash, "sha256:")
    
    file, err := os.Open(filePath)
    if err != nil {
        return false, err
    }
    defer file.Close()
    
    hasher := sha256.New()
    if _, err := io.Copy(hasher, file); err != nil {
        return false, err
    }
    
    computedHash := fmt.Sprintf("%x", hasher.Sum(nil))
    return computedHash == expectedHash, nil
}
```

### 5.7 Time Window Checker (UTC)

```go
func isWithinWorkHours(serverTime time.Time, config Config) bool {
    startTime, _ := time.Parse("15:04", config.WorkHourStart)
    endTime, _ := time.Parse("15:04", config.WorkHourEnd)
    
    currentMinutes := serverTime.Hour()*60 + serverTime.Minute()
    startMinutes := startTime.Hour()*60 + startTime.Minute()
    endMinutes := endTime.Hour()*60 + endTime.Minute()
    
    return currentMinutes >= startMinutes && currentMinutes <= endMinutes
}

func shouldExecuteNow(task Task, serverTime time.Time, config Config) bool {
    if task.ForceUpdate {
        return true
    }
    if !isWithinWorkHours(serverTime, config) {
        return false
    }
    jitter := rand.Intn(300)
    time.Sleep(time.Duration(jitter) * time.Second)
    return true
}
```

### 5.8 Installer Execution

```go
func Install(filePath, args string, timeoutSec int) (exitCode int, err error) {
    ctx, cancel := context.WithTimeout(context.Background(), 
        time.Duration(timeoutSec)*time.Second)
    defer cancel()
    
    var cmd *exec.Cmd
    
    if strings.HasSuffix(filePath, ".msi") {
        cmd = exec.CommandContext(ctx, "msiexec", "/i", filePath)
        if args != "" {
            cmd.Args = append(cmd.Args, strings.Fields(args)...)
        }
    } else {
        cmd = exec.CommandContext(ctx, filePath)
        if args != "" {
            cmd.Args = append(cmd.Args, strings.Fields(args)...)
        }
    }
    
    output, err := cmd.CombinedOutput()
    
    if ctx.Err() == context.DeadlineExceeded {
        return -1, fmt.Errorf("Installation timeout after %d seconds", timeoutSec)
    }
    
    if err != nil {
        if exitErr, ok := err.(*exec.ExitError); ok {
            return exitErr.ExitCode(), fmt.Errorf("Installation failed: %s", output)
        }
        return -1, err
    }
    
    return 0, nil
}
```

### 5.9 Self-Update Mechanism

```go
func SelfUpdate(newAgentPath string) error {
    currentExe, _ := os.Executable()
    
    oldPath := strings.Replace(currentExe, ".exe", ".old", 1)
    if err := os.Rename(currentExe, oldPath); err != nil {
        return err
    }
    
    if err := os.Rename(newAgentPath, currentExe); err != nil {
        os.Rename(oldPath, currentExe) // Rollback
        return err
    }
    
    return RestartService()
}

func RestartService() error {
    cmd := exec.Command("sc", "stop", "AppCenterAgent")
    cmd.Run()
    time.Sleep(2 * time.Second)
    cmd = exec.Command("sc", "start", "AppCenterAgent")
    return cmd.Run()
}
```

### 5.10 Task Queue with Retry

```go
type TaskQueue struct {
    Tasks      []Task
    RetryMap   map[int]*RetryInfo
    MaxRetries int
}

type RetryInfo struct {
    Count       int
    NextRetryAt time.Time
}

func (q *TaskQueue) ProcessTasks(config Config, serverTime time.Time) {
    for _, task := range q.Tasks {
        if retry, exists := q.RetryMap[task.TaskID]; exists {
            if retry.Count >= q.MaxRetries {
                ReportFailed(task, "Max retry count exceeded")
                delete(q.RetryMap, task.TaskID)
                continue
            }
            if time.Now().Before(retry.NextRetryAt) {
                continue
            }
        }
        
        if !shouldExecuteNow(task, serverTime, config) {
            continue
        }
        
        if !HasEnoughSpace(task.FileSizeBytes) {
            ReportFailed(task, "Insufficient disk space")
            continue
        }
        
        // Download
        destPath := filepath.Join(config.DownloadDir, fmt.Sprintf("%d_%s", task.AppID, task.AppName))
        err := DownloadFile(task.DownloadURL, destPath, config.BandwidthLimitKBps, config.UUID, config.SecretKey)
        if err != nil {
            q.scheduleRetry(task.TaskID)
            ReportFailed(task, fmt.Sprintf("Download failed: %v", err))
            continue
        }
        
        // Verify
        valid, err := VerifyFileHash(destPath, task.FileHash)
        if err != nil || !valid {
            os.Remove(destPath)
            q.scheduleRetry(task.TaskID)
            ReportFailed(task, "Hash verification failed")
            continue
        }
        
        // Install
        ReportStatus(task.TaskID, "installing", 50, "Installing...")
        exitCode, err := Install(destPath, task.InstallArgs, config.InstallTimeoutSec)
        
        if err != nil || exitCode != 0 {
            q.scheduleRetry(task.TaskID)
            ReportFailed(task, fmt.Sprintf("Install failed: exit code %d", exitCode))
            continue
        }
        
        if config.EnableAutoCleanup {
            os.Remove(destPath)
        }
        
        ReportSuccess(task)
        delete(q.RetryMap, task.TaskID)
    }
}

func (q *TaskQueue) scheduleRetry(taskID int) {
    retry, exists := q.RetryMap[taskID]
    if !exists {
        retry = &RetryInfo{Count: 0}
        q.RetryMap[taskID] = retry
    }
    retry.Count++
    retryDelay := time.Duration(retry.Count*5) * time.Minute
    retry.NextRetryAt = time.Now().Add(retryDelay)
}
```

### 5.11 System Tray Application

```go
// internal/tray/tray.go

func Run() {
    systray.Run(onReady, onExit)
}

func onReady() {
    systray.SetIcon(getIconGreen())
    systray.SetTitle("AppCenter")
    systray.SetTooltip("AppCenter Agent - Online")
    
    mStore := systray.AddMenuItem("Store", "Open Application Store")
    mAbout := systray.AddMenuItem("About", "About AppCenter")
    systray.AddSeparator()
    mQuit := systray.AddMenuItem("Exit", "Exit AppCenter Tray")
    
    go func() {
        for {
            select {
            case <-mStore.ClickedCh:
                OpenStoreWindow()
            case <-mAbout.ClickedCh:
                ShowAboutDialog()
            case <-mQuit.ClickedCh:
                systray.Quit()
            }
        }
    }()
    
    go updateTrayStatus()
}

func updateTrayStatus() {
    ticker := time.NewTicker(10 * time.Second)
    for range ticker.C {
        // Named Pipe üzerinden service'e bağlan
        resp, err := ipc.SendIPCRequest(ipc.IPCRequest{
            Action: "get_status",
        })
        if err != nil || resp.Status != "ok" {
            systray.SetIcon(getIconRed())
            systray.SetTooltip("AppCenter Agent - Offline")
        } else {
            systray.SetIcon(getIconGreen())
            systray.SetTooltip("AppCenter Agent - Online")
        }
    }
}
```

### 5.12 Agent Config (config.yaml)

```yaml
server:
  url: "https://appcenter.company.com"
  verify_ssl: true

agent:
  uuid: ""          # Auto-generated on first run
  secret_key: ""    # Received from server on registration

heartbeat:
  interval_sec: 60

download:
  temp_dir: "C:\\ProgramData\\AppCenter\\downloads"
  chunk_size_kb: 1024

logging:
  level: "info"
  file: "C:\\ProgramData\\AppCenter\\logs\\agent.log"
  max_size_mb: 10
  max_backups: 5
```

---

## 6. WEB ARAYÜZÜ

### 6.1 Sayfa Yapısı

```
templates/
├── base.html              # Ana layout
├── components/
│   ├── navbar.html
│   ├── sidebar.html
│   └── stats_card.html
├── auth/
│   └── login.html
├── dashboard.html
├── agents/
│   ├── list.html
│   └── detail.html
├── applications/
│   ├── list.html
│   ├── upload.html
│   └── detail.html
├── deployments/
│   ├── list.html
│   └── create.html
└── settings.html
```

### 6.2 Ana Sayfalar

#### Dashboard
- Stats Cards: Total Agents, Online (yeşil), Offline (kırmızı), Pending Tasks, Failed Tasks (24h)
- Charts: Agent Status Pie, Deployment Success Rate Bar
- Recent Activity: Son 10 işlem tablosu

#### Agents List
- Filtre: Status, Group, Search (hostname/IP)
- Tablo: Status Icon, Hostname, IP, Group, User, Version, Last Seen, Actions
- Last Seen: 5 dakikadan eski ise kırmızı

#### Applications
- Grid/List toggle
- Upload form: drag-drop, auto SHA256 hesaplama
- Sadece .msi ve .exe kabul edilir

#### Deployments
- 3-step wizard: Select App → Select Target → Options
- Target: All / Group / Agent
- Options: Mandatory, Force Update, Priority (1-10)

#### Settings
- General: Heartbeat interval, Agent timeout, Log retention
- Bandwidth: KB/s limit
- Work Hours: Start/End (UTC timezone notu gösterilmeli)
- Agent Updates: Version, upload installer

### 6.3 Frontend

**Tech Stack:** Vanilla JS + TailwindCSS CDN + fetch API

```javascript
// static/js/api.js
const API_BASE = '/api/v1';

async function apiCall(endpoint, options = {}) {
    const token = localStorage.getItem('token');
    const headers = { ...options.headers };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    
    const response = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });
    if (response.status === 401) {
        window.location.href = '/login';
        return;
    }
    return response.json();
}

// Polling: her 10 saniyede agent durumları güncelle
setInterval(() => {
    if (document.getElementById('agents-table')) {
        refreshAgentList();
    }
}, 10000);
```

---

## 7. GÜVENLİK

### 7.1 Server Security

- **HTTPS:** Let's Encrypt, HSTS header zorunlu
- **Auth:** Web UI = JWT (1 saat), Agent = UUID + Secret Key (header)
- **Input Validation:** Pydantic schemas
- **File Upload:** Sadece .msi/.exe, max 2GB, güvenli filename formatı
- **SQL:** SQLAlchemy ORM (SQL injection koruması)
- **Rate Limiting:** 120 req/min per IP (heartbeat endpoint)

### 7.2 Agent Security

- Registry: Windows DPAPI ile secret key şifreleme
- TLS 1.2+ zorunlu
- Downloaded dosyalar: SHA256 doğrulama, kurulum sonrası silme

### 7.3 Filename Security (YENİ)

Upload edilen dosyalar **asla** orijinal isimleriyle saklanmaz:
```
Orijinal: ../../etc/passwd.msi
Saklanan: 15_a7b3c9d2.msi
```

---

## 8. DEPLOYMENT & DevOps (Native/Binary)

### 8.1 Server Kurulumu (Native Linux - Docker YOK)

#### Gereksinimler

```bash
# Ubuntu 22.04 / Debian 12
sudo apt update
sudo apt install -y python3.10 python3.10-venv python3-pip nginx sqlite3
```

#### Uygulama Kurulumu

```bash
# 1. Dizinleri oluştur
sudo mkdir -p /opt/appcenter
sudo mkdir -p /var/lib/appcenter/{uploads,backups}
sudo mkdir -p /var/log/appcenter
sudo mkdir -p /etc/appcenter

# 2. Uygulama kullanıcısı
sudo useradd -r -s /bin/false appcenter
sudo chown -R appcenter:appcenter /opt/appcenter /var/lib/appcenter /var/log/appcenter

# 3. Uygulama dosyalarını kopyala
sudo cp -r app/ /opt/appcenter/
sudo cp requirements.txt /opt/appcenter/

# 4. Python virtual environment
cd /opt/appcenter
sudo -u appcenter python3 -m venv venv
sudo -u appcenter ./venv/bin/pip install -r requirements.txt

# 5. Environment dosyası
sudo cp .env /etc/appcenter/.env
sudo chmod 600 /etc/appcenter/.env

# 6. Veritabanı başlat
sudo -u appcenter ./venv/bin/python -c "from app.database import init_db; init_db()"
```

#### systemd Service

```ini
# /etc/systemd/system/appcenter.service
[Unit]
Description=AppCenter Server
After=network.target

[Service]
Type=exec
User=appcenter
Group=appcenter
WorkingDirectory=/opt/appcenter
EnvironmentFile=/etc/appcenter/.env
ExecStart=/opt/appcenter/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5

# Güvenlik
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/appcenter /var/log/appcenter

[Install]
WantedBy=multi-user.target
```

```bash
# Service'i etkinleştir ve başlat
sudo systemctl daemon-reload
sudo systemctl enable appcenter
sudo systemctl start appcenter
```

#### Nginx Konfigürasyonu

```nginx
# /etc/nginx/sites-available/appcenter
upstream appcenter_backend {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name appcenter.company.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name appcenter.company.com;

    ssl_certificate /etc/letsencrypt/live/appcenter.company.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/appcenter.company.com/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    add_header Strict-Transport-Security "max-age=31536000" always;

    client_max_body_size 2G;

    location / {
        proxy_pass http://appcenter_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /opt/appcenter/app/static/;
        expires 30d;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/appcenter /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 8.2 Yönetim Komutları

```bash
# Servis yönetimi
sudo systemctl status appcenter
sudo systemctl restart appcenter
sudo journalctl -u appcenter -f          # Canlı loglar

# Veritabanı
sqlite3 /var/lib/appcenter/appcenter.db "PRAGMA integrity_check;"
sqlite3 /var/lib/appcenter/appcenter.db ".tables"

# Log kontrolü
tail -f /var/log/appcenter/server.log

# Disk kullanımı
du -sh /var/lib/appcenter/uploads/
```

### 8.3 Backup (Cron)

```bash
# /etc/cron.d/appcenter-backup
# Her gece 02:00'de veritabanı backup
0 2 * * * appcenter sqlite3 /var/lib/appcenter/appcenter.db ".backup '/var/lib/appcenter/backups/appcenter_$(date +\%Y\%m\%d).db'"
# 30 günden eski backup'ları sil
5 2 * * * appcenter find /var/lib/appcenter/backups -name "appcenter_*.db" -mtime +30 -delete
```

### 8.4 Agent Build & Deployment

**Build Script (build.bat):**
```batch
@echo off
echo Building AppCenter Agent...

cd cmd\service
go build -ldflags="-s -w" -o ..\..\build\appcenter-service.exe
cd ..\..

cd cmd\tray
go build -ldflags="-s -w -H=windowsgui" -o ..\..\build\appcenter-tray.exe
cd ..\..

copy configs\config.yaml.template build\config.yaml
echo Build complete!
```

**Service Installation (service-install.bat):**
```batch
@echo off
echo Installing AppCenter Agent Service...

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Must run as Administrator
    pause
    exit /b 1
)

mkdir "C:\Program Files\AppCenter" 2>nul
mkdir "C:\ProgramData\AppCenter\downloads" 2>nul
mkdir "C:\ProgramData\AppCenter\logs" 2>nul

copy appcenter-service.exe "C:\Program Files\AppCenter\" /Y
copy appcenter-tray.exe "C:\Program Files\AppCenter\" /Y
copy config.yaml "C:\ProgramData\AppCenter\" /Y

sc create AppCenterAgent binPath= "C:\Program Files\AppCenter\appcenter-service.exe" start= auto
sc description AppCenterAgent "AppCenter Agent Service"
sc start AppCenterAgent

reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" /v AppCenterTray /t REG_SZ /d "C:\Program Files\AppCenter\appcenter-tray.exe" /f

echo Installation complete!
pause
```

---

## 9. GELİŞTİRME PLANI (SPRINT BAZLI)

### SPRINT 1 (Hafta 1-2): Temel Altyapı

**Server:**
- [ ] Project setup (FastAPI, SQLAlchemy, systemd)
- [ ] Database schema oluştur (SQLite + WAL + busy_timeout)
- [ ] Agent registration endpoint
- [ ] Heartbeat endpoint (basit)
- [ ] Basic authentication (JWT)

**Agent:**
- [ ] Project setup (Go)
- [ ] UUID generation & registry storage
- [ ] Config file management
- [ ] Heartbeat sender (basit)
- [ ] System info collector

**Web:**
- [ ] Login sayfası
- [ ] Dashboard layout (navbar, sidebar)
- [ ] Agent list page (mock data)

### SPRINT 2 (Hafta 3-4): Uygulama Yönetimi

**Server:**
- [ ] Application CRUD endpoints
- [ ] Güvenli file upload handler (sanitized filename)
- [ ] File download endpoint (range support)

**Agent:**
- [ ] Bandwidth-limited downloader
- [ ] Hash verification
- [ ] Disk space check

**Web:**
- [ ] Application upload form
- [ ] Application list/grid view

### SPRINT 3 (Hafta 5-6): Deployment & Installation

**Server:**
- [ ] Deployment CRUD endpoints
- [ ] Task assignment logic (heartbeat entegre)
- [ ] Background scheduler (offline detection + log cleanup)

**Agent:**
- [ ] MSI/EXE installer executor
- [ ] Task queue with retry logic
- [ ] Time window checker (UTC)
- [ ] Progress reporting

**Web:**
- [ ] Deployment create wizard
- [ ] Real-time task status (polling)

### SPRINT 4 (Hafta 7-8): Agent UI & Store

**Server:**
- [ ] Store API endpoint (header-based auth)

**Agent:**
- [ ] Windows service wrapper
- [ ] System tray icon
- [ ] Named Pipe IPC server/client
- [ ] Store window UI

**Web:**
- [ ] Agent detail page
- [ ] UI/UX polish

### SPRINT 5 (Hafta 9-10): Self-Update & Polish

**Server:**
- [ ] Agent update upload endpoint
- [ ] Settings page (tüm ayarlar)
- [ ] Dashboard stats ve charts

**Agent:**
- [ ] Self-update mechanism
- [ ] apps_changed optimizasyonu

### SPRINT 6 (Hafta 11-12): Testing & Production

- [ ] Unit tests
- [ ] Integration tests
- [ ] Load testing (100+ agent)
- [ ] SSL setup (Let's Encrypt)
- [ ] Backup cron job
- [ ] Dokümantasyon

---

## 10. CLAUDE CODE GELİŞTİRME REHBERİ

### 10.1 Proje Yapısı

Bu proje **iki ayrı Claude Code session'ında** geliştirilmelidir:

```
appcenter/
├── server/          → Claude Code Session 1 (Linux)
│   ├── CLAUDE.md    → Server-specific talimatlar
│   └── ...
├── agent/           → Claude Code Session 2 (Windows cross-compile veya Windows)
│   ├── CLAUDE.md    → Agent-specific talimatlar
│   └── ...
└── README.md        → Genel proje açıklaması
```

### 10.2 CLAUDE.md Dosyaları

İki ayrı `CLAUDE.md` dosyası oluşturulmalı. Detaylar aşağıdaki ayrı dokümanlarda:

- **`server/CLAUDE.md`** → Bkz: `AppCenter_Server_CLAUDE.md`
- **`agent/CLAUDE.md`** → Bkz: `AppCenter_Agent_CLAUDE.md`

---

## 11. EKSTRA NOTLAR

### 11.1 Sık Kullanılan Exit Kodları (MSI/EXE)

```
0     - Success
1603  - Fatal error during installation
1618  - Another installation is in progress
1619  - Installation package could not be opened
1633  - This installation package is not supported
3010  - Restart required
```

### 11.2 Örnek Install Arguments

**MSI (Silent):** `/qn`, `/quiet`, `/norestart`, `/l*v log.txt`  
**EXE (Common):** `/S` (NSIS), `/VERYSILENT` (Inno), `/silent` (InstallShield), `/quiet`

### 11.3 Performance Tips

**Server:**
- SQLite: WAL mode + busy_timeout=5000 (ZORUNLU)
- File uploads: Stream to disk, don't buffer in memory
- Background tasks: APScheduler ile ayrı job'lar

**Agent:**
- Heartbeat: goroutine, non-blocking
- apps_changed: sadece değişiklik varsa full list gönder
- Downloads: Resume capability
- Named Pipe: bağlantı başına goroutine

### 11.4 Troubleshooting

**Agent Not Connecting:**
1. Network connectivity
2. Server URL in config.yaml
3. Firewall (port 443)
4. SSL certificate
5. Agent logs: `C:\ProgramData\AppCenter\logs\`

**Server Issues:**
1. `sudo systemctl status appcenter`
2. `sudo journalctl -u appcenter -f`
3. `sqlite3 /var/lib/appcenter/appcenter.db "PRAGMA integrity_check;"`
4. Disk space: `df -h` ve `du -sh /var/lib/appcenter/uploads/`
5. Nginx: `sudo nginx -t` ve `sudo tail -f /var/log/nginx/error.log`

---

**Doküman Versiyonu:** 1.1  
**Son Güncelleme:** 13 Şubat 2026  
**Geliştirme Aracı:** Claude Code
