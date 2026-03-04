# Linux Agent (Debian) - Detayli Uygulama Plani

Tarih: 2026-03-03
Durum: v2 (kod analizi sonrasi guncellenmis)
Kapsam: Ubuntu 24.04 LTS ve Pardus 25.0 (Debian tabanli) ajan destegi

---

## 1. Kararlar ve Sinirlar

Bu plan asagidaki kesinlesmis kararlar uzerine kilitlenmistir:

1. **VNC helper:** `x11vnc` (kesin). Wayland kapsam disi.
2. **Oturum tipi:** Yalnizca `X11`.
3. **Build tag stratejisi:** `//go:build linux` — yeni dosyalar `_linux.go` son ekiyle olusturulacak.
4. **IPC mekanizmasi:** Unix Domain Socket (`/var/run/appcenter-agent/ipc.sock`). Named Pipe yalnizca Windows.
5. **Uygulama modeli:** Her `Application` kaydinin tek bir `target_platform` alani olur. Ayni yazilimin Windows ve Linux versiyonu icin ayri `Application` kayitlari olusturulur. Coklu-platform artifact destegi yoktur.
6. **Tray uygulamasi:** Linux'ta tray uygulamasi **yoktur**. Agent yalnizca headless systemd servisi olarak calisir.
7. **Agent config dagitimi:** deb paketi `postinst` script'i ile yapar. Ortam degiskeni fallback desteklenir.
8. **Desteklenen platformlar:** Ubuntu 24.04 LTS, Pardus 25.0 (Debian tabanli).
9. **Ana ilke:** Core ajan parity ilk faz, store en son faz.

---

## 2. Hedef Mimari

### 2.1 Genel Yapi

```
Admin Tarayici (Web UI)
  |  HTTPS / WSS
  v
Nginx reverse proxy
  |-- /            --> FastAPI (:8000)
  |-- /novnc-ws    --> FastAPI WS bridge
  v
FastAPI Server (tek backend, platform-aware)
  |-- /api/v1/agent/*    Tum agent endpoint'leri (Windows + Linux)
  |-- /api/v1/web/*      Admin UI endpoint'leri
  |-- platform filtresi  register/heartbeat'te platform alani ile
  v
+-----------------------+    +-----------------------+
| Windows Agent         |    | Linux Agent           |
| Go binary (.exe)      |    | Go binary (ELF)       |
| Windows Service       |    | systemd service       |
| Named Pipe IPC        |    | Unix Socket IPC       |
| rshelper.exe (VNC)    |    | x11vnc (VNC)          |
| System Tray (GUI)     |    | Tray YOK (headless)   |
| MSI installer         |    | deb paketi            |
+-----------------------+    +-----------------------+
```

### 2.2 Linux Ajan Temel Ozellik Seti

| Ozellik | Endpoint | Faz |
|---------|----------|-----|
| Register | `POST /agent/register` | 1 |
| Heartbeat | `POST /agent/heartbeat` | 1 |
| Signal long-poll | `GET /agent/signal` | 1 |
| Command alma | heartbeat response `commands[]` | 1 |
| Task status raporu | `POST /agent/task/{id}/status` | 1 |
| Uygulama indirme | `GET /agent/download/{app_id}` | 1 |
| Envanter gonderimi | `POST /agent/inventory` | 1 |
| Self-update | heartbeat config + download | 4 |
| Remote support | approve/ready/ended endpoint'leri | 2 |

---

## 3. Fazlandirma

---

### Faz 0 — Analiz, Kontrat ve Tasarim Dondurma

**Amac:** Kod degisikligine gecmeden veri modeli, API kontrati ve paketleme kararlarini dondurmak.

**Teslimler:**

1. DB migration listesi (kesinlesmis kolon adi, tip, default deger)
2. API schema degisiklikleri (Pydantic model field listesi)
3. Go agent dosya matrisi (hangi `_linux.go` dosyalari olusturulacak)
4. Upload extension matrisi (platform → izin verilen uzantilar)
5. x11vnc helper surec akisi (onay → baslat → monitor secimi → bitis)
6. deb paket yapisi ve dosya yollari
7. Unix domain socket IPC kontrati

**Kabul kriteri:**

- Tum maddeler bu dokumanda yazili ve onaylanmis.

---

### Faz 1 — Server: Platform-Aware Altyapi

**Amac:** Server tarafinda Linux agent'i destekleyecek tum DB, API ve is mantigi degisikliklerini tamamlamak. Bu faz tamamlanmadan agent kodu yazilmaz.

#### 1.1 DB Migration'lari

Mevcut migration yontemi: `app/database.py` icinde `_run_startup_migrations()` fonksiyonu, `information_schema` kontrolu ile kolon varligini dogrulayip gerekli `ALTER TABLE` adimlarini idempotent uygular.

**`agents` tablosuna eklenecek kolonlar:**

```sql
ALTER TABLE agents ADD COLUMN platform TEXT NOT NULL DEFAULT 'windows';
-- Degerler: 'windows' | 'linux'

ALTER TABLE agents ADD COLUMN arch TEXT DEFAULT NULL;
-- Degerler: 'amd64' | 'arm64'

ALTER TABLE agents ADD COLUMN distro TEXT DEFAULT NULL;
-- Degerler: 'ubuntu' | 'pardus' | 'debian' | NULL (Windows icin)

ALTER TABLE agents ADD COLUMN distro_version TEXT DEFAULT NULL;
-- Degerler: '24.04' | '25.0' | NULL
```

**`applications` tablosuna eklenecek kolonlar:**

```sql
ALTER TABLE applications ADD COLUMN target_platform TEXT NOT NULL DEFAULT 'windows';
-- Degerler: 'windows' | 'linux'
```

**`applications.file_type` CHECK constraint guncelleme:**

Mevcut constraint: `file_type IN ('msi', 'exe')`

PostgreSQL'ta CHECK constraint degisimi migration ile yonetilir. Cozum:
- Startup migration'da tablo yeniden olusturma **yapilmayacak**.
- `file_type` kontrolu uygulama katmaninda (Pydantic + service layer) zorunlu tutulacak.
- DB tarafinda yeni platform kurallarina uygun constraint migration'i idempotent uygulanacak.
- Gecis stratejisi: mevcut Windows kayitlari korunur; Linux icin `deb`, `tar.gz`, `sh` yalnizca `target_platform='linux'` ile kabul edilir.

**Platform-aware file_type validation matrisi:**

| target_platform | Izin verilen file_type degerleri |
|----------------|--------------------------------|
| windows | `msi`, `exe` |
| linux | `deb`, `tar.gz`, `sh` |

**Settings tablosuna eklenecek anahtarlar:**

```
agent_latest_version_windows  (mevcut agent_latest_version'dan migrate)
agent_download_url_windows    (mevcut agent_download_url'den migrate)
agent_hash_windows            (mevcut agent_hash'ten migrate)
agent_latest_version_linux    (yeni, bos)
agent_download_url_linux      (yeni, bos)
agent_hash_linux              (yeni, bos)
```

Migration notu: Mevcut `agent_latest_version`, `agent_download_url`, `agent_hash` anahtarlari **korunacak** (backward compat). Eger `agent_latest_version_windows` bulunamazsa `agent_latest_version` fallback olarak kullanilacak.

**Migration implementasyon yeri:** `app/database.py` → `_run_migrations()` fonksiyonuna ek blok.

#### 1.2 Pydantic Schema Degisiklikleri

**Dosya:** `app/schemas.py`

**`AgentRegisterRequest` — yeni alanlar (tumu Optional, backward compat):**

```python
platform: Optional[str] = None        # 'windows' | 'linux'
arch: Optional[str] = None            # 'amd64' | 'arm64'
distro: Optional[str] = None          # 'ubuntu' | 'pardus' | 'debian'
distro_version: Optional[str] = None  # '24.04' | '25.0'
```

Platform None/bos gelirse `'windows'` olarak varsayilir (mevcut agent'lar icin).

**`HeartbeatRequest` — yeni alanlar (tumu Optional):**

```python
platform: Optional[str] = None
```

Heartbeat'te platform bilgisi opsiyonel olarak gonderilir. Server her heartbeat'te agent kaydindaki `platform` alanini okur, heartbeat'teki deger varsa gunceller.

**`HeartbeatConfig` — degisiklik:**

Mevcut alanlar:
```python
latest_agent_version: Optional[str]
agent_download_url: Optional[str]
agent_hash: Optional[str]
```

Bu alanlar korunur. Heartbeat service, agent'in `platform` degerine gore dogru settings anahtarini secer ve bu alanlara yazar. Agent tarafi degisiklik gerektirmez.

**`ApplicationCreate` / `ApplicationUpdate` — yeni alan:**

```python
target_platform: str = "windows"  # 'windows' | 'linux'
```

#### 1.3 API Endpoint Degisiklikleri

**Dosya:** `app/api/v1/agent.py`

**`POST /agent/register`:**
- Yeni alanlari parse et: `platform`, `arch`, `distro`, `distro_version`
- Agent model'e yaz (platform None ise 'windows' ata)
- Mevcut davranis korunur, yeni alanlar opsiyonel

**`POST /agent/heartbeat`:**
- Request'ten `platform` okunursa agent kaydinda guncellenir
- Mevcut davranis tamamen korunur

**Dosya:** `app/api/v1/web.py`

**`POST /applications` (upload):**
- Form'a `target_platform` alani eklenir (default: `"windows"`)
- Upload validation: `target_platform` + `file_type` matrisi kontrol edilir
- Mevcut Windows upload'lari aynen calisir

**`POST /agent-update/upload`:**
- Form'a `platform` alani eklenir (default: `"windows"`)
- Settings anahtarlari: `agent_latest_version_{platform}`, `agent_download_url_{platform}`, `agent_hash_{platform}`
- Mevcut eski anahtarlar da guncellenir (fallback uyumlulugu)

#### 1.4 Service Layer Degisiklikleri

**Dosya:** `app/services/heartbeat_service.py`

**`_build_heartbeat_config()` icinde:**

```python
# Mevcut:
config.latest_agent_version = _get_setting(db, "agent_latest_version")
config.agent_download_url = _get_setting(db, "agent_download_url")
config.agent_hash = _get_setting(db, "agent_hash")

# Yeni (platform-aware):
platform = agent.platform or "windows"
config.latest_agent_version = (
    _get_setting(db, f"agent_latest_version_{platform}")
    or _get_setting(db, "agent_latest_version")  # fallback
)
config.agent_download_url = (
    _get_setting(db, f"agent_download_url_{platform}")
    or _get_setting(db, "agent_download_url")
)
config.agent_hash = (
    _get_setting(db, f"agent_hash_{platform}")
    or _get_setting(db, "agent_hash")
)
```

**Dosya:** `app/services/deployment_service.py`

**`_seed_agent_applications()` degisiklik:**

```python
# Mevcut: tum hedef agent'lar icin AgentApplication olustur
# Yeni: agent.platform ile app.target_platform eslesmezse ATLA + log yaz

for agent in target_agents:
    if app.target_platform != (agent.platform or "windows"):
        logger.info(
            "Deployment %d: platform mismatch, agent=%s (%s), app=%s (%s) — skipped",
            deployment.id, agent.uuid, agent.platform, app.id, app.target_platform,
        )
        continue
    # ... mevcut AgentApplication olusturma mantigi
```

**Dosya:** `app/utils/file_handler.py`

**`ALLOWED_EXTENSIONS` guncelleme:**

```python
# Mevcut:
ALLOWED_EXTENSIONS = {".msi", ".exe"}

# Yeni:
ALLOWED_EXTENSIONS_BY_PLATFORM = {
    "windows": {".msi", ".exe"},
    "linux":   {".deb", ".sh"},
}
# tar.gz icin ozel kontrol: uzanti ".gz" ama orijinal dosya adi ".tar.gz" ile bitmeli
ALLOWED_EXTENSIONS = {".msi", ".exe", ".deb", ".sh", ".gz"}
```

`save_upload_to_temp()` fonksiyonunda: `target_platform` parametresi eklenir, platform'a gore uzanti kontrolu yapilir.

**`sanitize_filename()` guncelleme:**

```python
# Mevcut format:  {app_id}_{hash[:8]}.{ext}
# Yeni format:    {app_id}_{hash[:8]}.{ext}
# Degisiklik yok — target_platform dosya adinda yer almaz,
# Application kaydindaki target_platform alani yeterli.
```

#### 1.5 UI Degisiklikleri

**Uygulama upload formu (`templates/applications/upload.html`):**
- "Hedef Platform" select eklenir: Windows (default) | Linux
- Platform secimi `file_type` ve uzanti validasyonunu etkiler
- Linux secildiginde kabul edilen uzantilar `.deb`, `.tar.gz`, `.sh` olarak guncellenir

**Uygulama listesi (`templates/applications/list.html`):**
- Platform kolonu eklenir (ikon veya metin: Windows/Linux)
- Filtreleme: platform bazli

**Agent listesi (`templates/agents/list.html`):**
- Platform kolonu eklenir
- Filtreleme: platform bazli

**Agent detay (`templates/agents/detail.html`):**
- Platform, distro, distro_version gosterimi

**Deployment olusturma (`templates/deployments/create.html`):**
- Uygulama seciminde platform filtrelemesi (secilen hedef'e gore)
- Platform uyumsuzluk uyarisi

**Settings (`templates/settings.html`):**
- Agent guncelleme bolumune platform sekmesi: Windows | Linux
- Her platform icin ayri versiyon/dosya yukleme

**Kabul kriterleri:**

- [x] Migration'lar idempotent ve mevcut veriyi bozmaz
- [x] Mevcut Windows agent'lar degisiklik olmadan calisir (backward compat)
- [x] Linux platform'lu agent register olabilir
- [x] Platform-uyumsuz deployment skip edilir ve loglanir
- [x] Linux dosya tipleri (`.deb`, `.tar.gz`, `.sh`) upload edilebilir
- [x] Heartbeat config platform bazli update bilgisi dondurur
- [x] UI'da platform ayrimi gorunur

---

### Faz 2 — Agent: Linux Core Parity

**Amac:** Go agent'in Linux'ta Windows'la esit temel islevleri yerine getirmesi. Remote support **haric** — sadece register, heartbeat, signal, download, install, inventory, self-update.

#### 2.1 Yeni Go Dosyalari (`_linux.go`)

**Olusturulacak dosyalar:**

| Dosya | Amac | Mevcut Stub |
|-------|------|-------------|
| `internal/system/info_linux.go` | CPU/RAM/disk toplama | `info_nonwindows.go` (bos return) |
| `internal/system/uuid_linux.go` | Kalici UUID `/etc/appcenter-agent/uuid` | `uuid_nonwindows.go` (her seferinde yeni) |
| `internal/system/sessions_linux.go` | `who`/utmp ile oturum listesi | `sessions_nonwindows.go` (nil return) |
| `internal/system/profile_linux.go` | OS/donanim profili toplama | `profile_nonwindows.go` (nil return) |
| `internal/ipc/unixsocket_linux.go` | UDS server/client | `namedpipe_nonwindows.go` (error) |
| `internal/installer/deb_linux.go` | `dpkg -i` / `apt install -f` | Yeni |
| `internal/installer/script_linux.go` | `.sh` script ve `.tar.gz` extract | Yeni |
| `internal/config/runtime_overrides_linux.go` | Linux path default'lari | `runtime_overrides_nonwindows.go` (bos) |
| `cmd/service/main_linux.go` | systemd entegrasyonu | Yeni |

**Mevcut `_nonwindows.go` dosyalari korunacak mi?**

Hayir. Build tag stratejisi:
- Mevcut `_nonwindows.go` dosyalari `//go:build !windows` olarak kalir (macOS, FreeBSD vb. icin fallback).
- Yeni `_linux.go` dosyalari `//go:build linux` ile olusturulur.
- Go build sistemi `linux` tag'i `!windows`'tan daha spesifiktir, dolayisiyla `_linux.go` dosyasi varsa o kullanilir, yoksa `_nonwindows.go` fallback olur.

#### 2.2 Sistem Bilgisi Toplama (`internal/system/info_linux.go`)

```go
//go:build linux

package system

// collectHostExtras Linux'ta /proc ve standart komutlardan bilgi toplar.
```

**Toplama yontemleri:**

| Bilgi | Kaynak |
|-------|--------|
| CPU model | `/proc/cpuinfo` → `model name` satiri |
| RAM (GB) | `/proc/meminfo` → `MemTotal` satiri |
| Disk free (GB) | `syscall.Statfs("/")` |
| OS version | `runtime.GOOS + "/" + runtime.GOARCH` |

#### 2.3 Kalici UUID (`internal/system/uuid_linux.go`)

```go
//go:build linux

package system

// UUID dosyasi: /etc/appcenter-agent/uuid
// Yoksa olustur, varsa oku.
// Dosya izni: 0600, sahiplik: root:root
```

**Akis:**
1. `/etc/appcenter-agent/uuid` dosyasini oku
2. Gecerli UUID mi kontrol et
3. Gecerli degilse veya dosya yoksa yeni UUID olustur ve yaz
4. Dizin yoksa olustur (`0755`)

#### 2.4 Oturum Listesi (`internal/system/sessions_linux.go`)

```go
//go:build linux

package system

// GetLoggedInSessions: `who` komutu parse ederek aktif oturumlari dondurur.
// Alternatif: utmp dosyasi binary parse (/var/run/utmp)
```

**Cikti formati:**
```go
[]LoggedInSession{
    {Username: "ahmet", SessionType: "local", LogonID: "tty1"},
    {Username: "mehmet", SessionType: "rdp", LogonID: "pts/2"},
}
```

`SessionType` mapping:
- `tty*` veya `:0` → `"local"`
- `pts/*` → `"rdp"` (SSH/uzak erisim)

#### 2.5 Sistem Profili (`internal/system/profile_linux.go`)

```go
//go:build linux

package system

// CollectSystemProfile Linux sistem bilgisini toplar.
```

**Toplama kaynaklari:**

| Alan | Kaynak |
|------|--------|
| `os_full_name` | `/etc/os-release` → `PRETTY_NAME` |
| `os_version` | `/etc/os-release` → `VERSION_ID` |
| `build_number` | `uname -r` (kernel version) |
| `architecture` | `runtime.GOARCH` |
| `manufacturer` | `/sys/class/dmi/id/sys_vendor` |
| `model` | `/sys/class/dmi/id/product_name` |
| `cpu_model` | `/proc/cpuinfo` → `model name` |
| `cpu_cores_physical` | `/proc/cpuinfo` → unique `physical id` + `core id` |
| `cpu_cores_logical` | `runtime.NumCPU()` |
| `total_memory_gb` | `/proc/meminfo` → `MemTotal` |
| `disk_count` | `/sys/block/` altindaki disk sayisi (loop haric) |
| `disks[]` | `lsblk -J` veya `/sys/block/*/size` |
| `virtualization` | `systemd-detect-virt` veya `/sys/class/dmi/id/product_name` icerik kontrolu |
| `distro` | `/etc/os-release` → `ID` |
| `distro_version` | `/etc/os-release` → `VERSION_ID` |

#### 2.6 Unix Domain Socket IPC (`internal/ipc/unixsocket_linux.go`)

```go
//go:build linux

package ipc

// Socket yolu: /var/run/appcenter-agent/ipc.sock
// Mesaj formati: mevcut JSON Request/Response ile ayni
// Guvenlik: dosya izni 0660, grup: appcenter-agent
```

**Desteklenen action'lar (Windows parity):**

| Action | Aciklama |
|--------|----------|
| `get_status` | Service durumu, agent version, UUID |
| `remote_support_status` | RS state, session ID |
| `remote_support_end` | Aktif RS oturumunu sonlandir |

Store/tray action'lari Linux'ta **yok** (tray yok karari).

**Implementasyon:**
- `net.Listen("unix", socketPath)` ile dinle
- Her baglantida JSON decode → handler → JSON encode
- `Server` interface'i mevcut `namedpipe.go`'daki ile ayni
- Socket dosyasi service baslatildiginda olusturulur, durduruldugunda silinir

#### 2.7 Linux Installer'lar

**`internal/installer/deb_linux.go`:**

```go
//go:build linux

package installer

// installDeb: dpkg -i ile kurar, basarisiz olursa apt-get install -f dener.
// Komut: dpkg -i {filePath}
// Fallback: apt-get install -f -y (bagimliliklari coz)
// Basari kodlari: 0
// Log: /var/log/appcenter-agent/install_{taskID}.log
```

**`internal/installer/script_linux.go`:**

```go
//go:build linux

package installer

// installScript: .sh dosyalarini calistirir.
// Komut: /bin/bash {filePath} {args}
// Guvenlik: dosya executable yapilir (0755), /tmp'de calistirilmaz
// Timeout: install.timeout_sec config'den

// installTarGz: .tar.gz arsivlerini acar.
// Komut: tar xzf {filePath} -C {targetDir}
// targetDir: /opt/ altina veya install_args ile belirtilen dizine
```

**`internal/installer/installer.go` guncelleme:**

```go
// Mevcut switch case:
case ".msi": return installMSI(ctx, filePath, args)
case ".exe": return installEXE(ctx, filePath, args)

// Eklenecek (sadece linux build'de):
case ".deb": return installDeb(ctx, filePath, args)
case ".sh":  return installScript(ctx, filePath, args)
case ".gz":  return installTarGz(ctx, filePath, args)  // .tar.gz
```

Not: `.msi` ve `.exe` case'leri `_windows.go` build tag'i ile sinirli kalir. `_linux.go` icinde sadece `.deb`, `.sh`, `.gz` tanimlanir. `installer.go`'daki switch mevcut haliyle her iki platformu da kapsar (fonksiyonlar build tag'e gore linklenir).

#### 2.8 Linux Config Default'lari (`internal/config/runtime_overrides_linux.go`)

```go
//go:build linux

package config

func applyOSOverrides(c *Config) {
    if c.Download.TempDir == "" || c.Download.TempDir == `C:\ProgramData\AppCenter\downloads` {
        c.Download.TempDir = "/var/lib/appcenter-agent/downloads"
    }
    if c.Logging.File == "" || c.Logging.File == `C:\ProgramData\AppCenter\logs\agent.log` {
        c.Logging.File = "/var/log/appcenter-agent/agent.log"
    }
    if c.Update.HelperPath == "" || strings.Contains(c.Update.HelperPath, `C:\`) {
        c.Update.HelperPath = "/opt/appcenter-agent/appcenter-update-helper"
    }
    if c.Update.ServiceName == "" || c.Update.ServiceName == "AppCenterAgent" {
        c.Update.ServiceName = "appcenter-agent"
    }
}
```

**Linux dizin yapisi:**

| Amac | Yol |
|------|-----|
| Binary | `/opt/appcenter-agent/appcenter-agent` |
| Config | `/etc/appcenter-agent/config.yaml` |
| UUID | `/etc/appcenter-agent/uuid` |
| Downloads | `/var/lib/appcenter-agent/downloads/` |
| Logs | `/var/log/appcenter-agent/agent.log` |
| IPC socket | `/var/run/appcenter-agent/ipc.sock` |
| PID file | `/var/run/appcenter-agent/agent.pid` |

#### 2.9 systemd Entegrasyonu (`cmd/service/main_linux.go`)

```go
//go:build linux

package main

// Linux'ta Windows service wrapper'i yerine dogrudan main() calisir.
// Graceful shutdown: SIGTERM ve SIGINT handler'lari context.Cancel() cagirir.
// sd_notify: "READY=1" startup, "STOPPING=1" shutdown, watchdog destegi.
```

**systemd unit dosyasi (`packaging/systemd/appcenter-agent.service`):**

```ini
[Unit]
Description=AppCenter Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
ExecStart=/opt/appcenter-agent/appcenter-agent --config /etc/appcenter-agent/config.yaml
Restart=always
RestartSec=10
WatchdogSec=120
User=root
Group=root
LimitNOFILE=65536

# Guvenlik sertlestirme
ProtectSystem=strict
ReadWritePaths=/var/lib/appcenter-agent /var/log/appcenter-agent /var/run/appcenter-agent /etc/appcenter-agent
ProtectHome=yes
NoNewPrivileges=no
# NoNewPrivileges=no: x11vnc ve dpkg icin gerekli

[Install]
WantedBy=multi-user.target
```

#### 2.10 deb Paket Yapisi

```
packaging/deb/
├── DEBIAN/
│   ├── control
│   ├── preinst
│   ├── postinst
│   ├── prerm
│   └── postrm
├── opt/
│   └── appcenter-agent/
│       └── appcenter-agent          # Go binary
├── etc/
│   ├── appcenter-agent/
│   │   └── config.yaml.default      # Sablondan kopyalanir
│   └── systemd/
│       └── system/
│           └── appcenter-agent.service
└── var/
    ├── lib/appcenter-agent/
    │   └── downloads/               # Bos dizin
    └── log/appcenter-agent/         # Bos dizin
```

**`DEBIAN/control`:**
```
Package: appcenter-agent
Version: {{VERSION}}
Section: admin
Priority: optional
Architecture: amd64
Depends: libc6 (>= 2.34)
Recommends: x11vnc, zenity
Description: AppCenter Agent - Merkezi yonetim ajani
 Merkez sunucudan komut alarak uygulama kuran,
 envanter toplayan ve uzak destek saglayan ajan.
Maintainer: AppCenter Team
```

**`DEBIAN/postinst`:**
```bash
#!/bin/bash
set -e

# Config dosyasi yoksa sablon'dan olustur
if [ ! -f /etc/appcenter-agent/config.yaml ]; then
    cp /etc/appcenter-agent/config.yaml.default /etc/appcenter-agent/config.yaml
    chmod 600 /etc/appcenter-agent/config.yaml
fi

# Ortam degiskenlerinden config guncelle
if [ -n "$APPCENTER_SERVER_URL" ]; then
    sed -i "s|url:.*|url: \"$APPCENTER_SERVER_URL\"|" /etc/appcenter-agent/config.yaml
fi

# Gerekli dizinleri olustur
mkdir -p /var/run/appcenter-agent
mkdir -p /var/lib/appcenter-agent/downloads
mkdir -p /var/log/appcenter-agent

# systemd
systemctl daemon-reload
systemctl enable appcenter-agent.service
systemctl start appcenter-agent.service || true
```

**`DEBIAN/prerm`:**
```bash
#!/bin/bash
set -e
systemctl stop appcenter-agent.service || true
systemctl disable appcenter-agent.service || true
```

**`DEBIAN/postrm`:**
```bash
#!/bin/bash
set -e
if [ "$1" = "purge" ]; then
    rm -rf /etc/appcenter-agent
    rm -rf /var/lib/appcenter-agent
    rm -rf /var/log/appcenter-agent
    rm -rf /var/run/appcenter-agent
fi
systemctl daemon-reload || true
```

**Build scripti (`scripts/build-linux-deb.sh`):**

```bash
#!/bin/bash
set -e
VERSION="${1:?Usage: $0 <version>}"
ARCH="amd64"

# Go binary derle
cd agent
GOOS=linux GOARCH=$ARCH CGO_ENABLED=0 go build -ldflags="-s -w -X main.version=$VERSION" \
    -o ../packaging/deb/opt/appcenter-agent/appcenter-agent ./cmd/service/

# deb paketi olustur
cd ../packaging/deb
sed -i "s/{{VERSION}}/$VERSION/" DEBIAN/control
dpkg-deb --build . "../appcenter-agent_${VERSION}_${ARCH}.deb"
# control dosyasini geri al
git checkout DEBIAN/control
```

#### 2.11 Agent Self-Update Linux Mekanizmasi

Mevcut Windows mekanizmasi: `updater.go` → `pending_update.json` → `appcenter-update-helper.exe` ile binary degistirme.

**Linux icin:**
- `updater.go` mevcut StageIfNeeded akisi aynen calisir (platform-agnostic)
- `ApplyIfPending()` Linux'ta farkli calisir:
  1. Staged binary'yi `/opt/appcenter-agent/appcenter-agent.new` olarak dogrula
  2. `os.Rename()` ile atomik degistir (ayni filesystem'de)
  3. `os.Exit(0)` ile cik — systemd `Restart=always` ile yeniden baslatir
- Windows'taki `appcenter-update-helper.exe` Linux'ta gerekmez (systemd restart yeterli)

**Yeni dosya:** `internal/updater/apply_linux.go`
```go
//go:build linux

package updater

// applyUpdate: staged binary'yi yerlestirir ve exit(0) ile servisin
// systemd tarafindan yeniden baslatilmasini saglar.
```

**Kabul kriterleri:**

- [x] Linux agent register/heartbeat/signal akisi sorunsuz
- [x] UUID kalici (reboot sonrasi ayni)
- [x] Sistem bilgisi (CPU/RAM/disk/OS/distro) dogru toplanir
- [x] System profile periyodik gonderiliyor
- [x] Logged-in sessions dogru raporlaniyor
- [x] `.deb` paketi kurulumu calisir (dpkg -i + bagimliliklari coz)
- [x] `.sh` script kurulumu calisir
- [x] Unix socket IPC uzerinden `get_status` calisir
- [x] Self-update staging + apply calisir (systemd restart)
- [x] Task status raporlama dogru
- [x] Mevcut Windows akisinda regresyon yok

---

### Faz 3 — Agent: Linux Remote Support (x11vnc)

**Amac:** Windows'taki rshelper.exe modeline benzer, Linux icin on-demand x11vnc yardimci sureci.

#### 3.1 Isletim Sistemi Kisitlari

- Desteklenen oturum: **yalnizca X11**
- Wayland: kapsam disi (tespit edilirse log mesaji + session reject)
- Oturum tespiti: `echo $XDG_SESSION_TYPE` veya `loginctl show-session`

#### 3.2 Yeni Go Dosyalari

| Dosya | Amac |
|-------|------|
| `internal/remotesupport/vnc_linux.go` | x11vnc process baslatma/durdurma |
| `internal/remotesupport/dialog_linux.go` | zenity/kdialog onay dialog |
| `internal/remotesupport/helper_status_linux.go` | x11vnc process durum kontrolu |
| `internal/remotesupport/process_linux.go` | Kullanici oturumunda process baslatma |

#### 3.3 x11vnc Helper Yonetimi (`internal/remotesupport/vnc_linux.go`)

**Gerekli paketler (deb Recommends):** `x11vnc`, `zenity`

**Opsiyonel:** `xauth` (ortama gore), `netcat-openbsd` (diagnostic)

**Process baslatma — Tek Monitor:**
```bash
x11vnc \
  -display :0 \
  -rfbport 20010 \
  -passwd {session_vnc_password} \
  -once \
  -noxdamage \
  -noxfixes \
  -shared \
  -forever \
  -timeout 300
```

**Process baslatma — Coklu Monitor:**
```bash
# Monitor 1
x11vnc -display :0 -clip xinerama0 -rfbport 20010 -passwd {pw} -once -shared -forever

# Monitor 2
x11vnc -display :0 -clip xinerama1 -rfbport 20011 -passwd {pw} -once -shared -forever
```

**Port atamalari (Windows ile uyumlu):**

| Monitor | Port | Notlar |
|---------|------|--------|
| Monitor 1 | 20010 | Mevcut `defaultHelperPort` |
| Monitor 2 | 20011 | Mevcut `defaultSecondaryPort` |

**Process lifecycle:**
1. `exec.Command("x11vnc", args...)` ile baslat
2. PID kaydet
3. Port dinleme kontrolu: `net.DialTimeout("tcp", "127.0.0.1:20010", 5*time.Second)` ile teyit
4. Basarili ise `ReportRemoteReady()` cagir
5. Session bitisinde cleanup

**Cleanup sirasi:**
1. `SIGTERM` gonder
2. 3 saniye bekle
3. Hala calisiyor mu kontrol et
4. Evet ise `SIGKILL` gonder
5. Socket dosyasi temizle

#### 3.4 Onay Dialog (`internal/remotesupport/dialog_linux.go`)

```go
//go:build linux

package remotesupport

// ShowApprovalDialogFromService: X11 oturumunda kullaniciya onay dialog gosterir.
// Siralama: zenity → kdialog → fallback (otomatik kabul + log uyarisi)
```

**zenity komutu:**
```bash
DISPLAY=:0 zenity --question \
  --title="AppCenter - Uzak Destek Istegi" \
  --text="IT Destek - {adminName} bilgisayariniza uzaktan baglanmak istiyor.\n\nSebep: {reason}" \
  --ok-label="Onayla" \
  --cancel-label="Reddet" \
  --timeout={timeoutSec}
```

**Exit code mapping:**
- `0` → onaylandi
- `1` → reddedildi
- `5` → timeout (zenity timeout)

**kdialog fallback:**
```bash
DISPLAY=:0 kdialog --yesno \
  "IT Destek - {adminName} bilgisayariniza uzaktan baglanmak istiyor.\n\nSebep: {reason}" \
  --title "AppCenter - Uzak Destek Istegi" \
  --yes-label "Onayla" \
  --no-label "Reddet"
```

**Dialog tool tespiti:**
```go
func detectDialogTool() string {
    if _, err := exec.LookPath("zenity"); err == nil {
        return "zenity"
    }
    if _, err := exec.LookPath("kdialog"); err == nil {
        return "kdialog"
    }
    return "" // fallback: log uyarisi, otomatik reject
}
```

**Monitor sayisi tespiti:**
```bash
DISPLAY=:0 xrandr --query | grep " connected" | wc -l
```
Veya: `xdpyinfo` ile screen sayisi.

#### 3.5 X11 Oturum Tespiti ve DISPLAY Bulma

```go
// findActiveX11Display: aktif X11 display'ini bulur.
// 1. /tmp/.X11-unix/ altinda socket dosyalarini tara
// 2. loginctl ile aktif grafik oturumu bul
// 3. Oturum sahipinin DISPLAY env'ini oku: /proc/{pid}/environ
```

**Akis:**
1. `loginctl list-sessions --no-pager` → aktif oturumlar
2. Her oturum icin `loginctl show-session {id} -p Type -p Display -p User`
3. `Type=x11` olan ilk oturumu sec
4. `DISPLAY` degerini al (genellikle `:0`)

Bu bilgi x11vnc ve zenity icin `DISPLAY` env olarak kullanilir.

#### 3.6 Tam Session Akisi (Linux)

```
T+0s   Admin UI         "Uzak Destek Baslat" butonuna tiklar
       Server           Session olusturur (mevcut akis, degisiklik yok)

T+3s   Linux Agent      Heartbeat → remote_support_request alir
       SessionManager   HandleRequest() cagirilir

T+3s   Agent            X11 display tespit: DISPLAY=:0
       Agent            Wayland kontrolu: XDG_SESSION_TYPE == "x11" ✓

T+4s   Agent            zenity onay dialog gosterir (DISPLAY=:0)

T+8s   Kullanici        "Onayla" tiklar
       Agent            POST /agent/remote-support/{id}/approve
                        {approved: true, monitor_count: 2}

T+8s   Server           Session → approved
       Server           Response: {vnc_password: "Xk9mP2wQ"}

T+9s   Agent            x11vnc baslatir:
                        M1: -display :0 -clip xinerama0 -rfbport 20010 -passwd Xk9mP2wQ
                        M2: -display :0 -clip xinerama1 -rfbport 20011 -passwd Xk9mP2wQ

T+10s  Agent            Port 20010 dinliyor mu? → evet
       Agent            POST /agent/remote-support/{id}/ready
                        {vnc_ready: true, local_vnc_port: 20010}

T+10s  Server           Session → active
       Admin UI         noVNC baglantisi kurar (mevcut akis, degisiklik yok)
                        agent_ip:20010 → WebSocket bridge → noVNC canvas

...    Admin            Uzak destek verir

T+900s Admin UI         "Oturumu Bitir" tiklar
       Server           Session → ended, end_signal_pending=True

T+903s Agent            Heartbeat: remote_support_end alir
       Agent            x11vnc SIGTERM → 3s → SIGKILL (gerekirse)
       Agent            POST /agent/remote-support/{id}/ended
       Agent            State → idle
```

**Kabul kriterleri:**

- [x] Tek monitor x11vnc session Ubuntu 24.04'te calisir
- [x] Cift monitor x11vnc session calisir (xinerama0/1)
- [x] zenity onay dialog gosterilir ve yanit alinir
- [x] Session sonlandirmada x11vnc process temiz kapatilir (leak yok)
- [x] Wayland oturumu tespit edilirse session reddedilir
- [x] noVNC UI'da Linux agent remote support aynen Windows gibi gorunur
- [x] Remote support state heartbeat'te dogru raporlanir

---

### Faz 4 — Server + Agent: Self-Update Platform Ayrimi

**Amac:** Linux ve Windows ajan guncellemelerini ayri artifact zinciri ile yonetmek.

#### 4.1 Server Degisiklikleri

**`POST /agent-update/upload` endpoint guncelleme:**

```python
@router.post("/agent-update/upload")
async def upload_agent_update(
    version: str = Form(...),
    platform: str = Form("windows"),  # YENi: 'windows' | 'linux'
    file: UploadFile = File(...),
    ...
):
    # Platform validation
    if platform not in ("windows", "linux"):
        raise HTTPException(400, "Invalid platform")

    # Uzanti kontrolu
    if platform == "windows" and ext not in (".msi", ".exe"):
        raise HTTPException(400, "Windows agent update must be .msi or .exe")
    if platform == "linux" and ext not in (".deb", ".tar.gz"):
        raise HTTPException(400, "Linux agent update must be .deb or .tar.gz")

    # Dosya adlandirma
    filename = f"agent_{platform}_{version}_{digest_hex[:8]}.{file_type}"

    # Platform-bazli settings anahtarlari
    pairs = {
        f"agent_latest_version_{platform}": version,
        f"agent_download_url_{platform}": download_url,
        f"agent_hash_{platform}": f"sha256:{digest_hex}",
        f"agent_update_filename_{platform}": filename,
    }
    # Backward compat: Windows icin eski anahtarlari da guncelle
    if platform == "windows":
        pairs.update({
            "agent_latest_version": version,
            "agent_download_url": download_url,
            "agent_hash": f"sha256:{digest_hex}",
        })
```

**Settings UI guncelleme:**
- Agent guncelleme bolumune platform sekmesi eklenir
- Her platform icin ayri upload formu

#### 4.2 Publish Script'leri

**`scripts/publish-agent-update.sh` guncelleme:**
```bash
#!/bin/bash
# Mevcut: --version parametresi
# Yeni: --version + --platform parametresi

PLATFORM="${PLATFORM:-windows}"
# Kullanim:
# PLATFORM=linux ./scripts/publish-agent-update.sh --version 0.2.0
# PLATFORM=windows ./scripts/publish-agent-update.sh --version 1.5.0
```

**Yeni: `scripts/build-and-publish-linux-agent.sh`:**
```bash
#!/bin/bash
set -e
VERSION="${1:?Usage: $0 <version>}"

# 1. Binary derle
./scripts/build-linux-deb.sh "$VERSION"

# 2. Server'a upload et
curl -X POST "https://appcenter.akgun.com.tr/api/v1/agent-update/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "version=$VERSION" \
  -F "platform=linux" \
  -F "file=@packaging/appcenter-agent_${VERSION}_amd64.deb"
```

#### 4.3 Agent Tarafi

Agent tarafinda degisiklik gerekmez. Mevcut `updater.go`:
- Heartbeat config'den `latest_agent_version`, `agent_download_url`, `agent_hash` alir
- Server zaten platform-aware deger dondurur (Faz 1'de implemente edildi)
- Linux agent .deb dosyasini indirir, hash dogrular, staging yapar
- `ApplyIfPending()` Linux'ta `apply_linux.go` calisir

**Kabul kriterleri:**

- [x] Linux agent Linux update artifact'i aliyor
- [x] Windows agent Windows update artifact'i aliyor
- [x] Capraz platform update dagitilmiyor
- [x] Publish script her iki platform icin calisir

---

### Faz 5 — Test, CI ve Regresyon Sertlestirme

**Amac:** Linux eklenirken mevcut sistemin bozulmadigini guvenceye almak.

#### 5.1 Server Unit Test'leri

**Yeni test dosyasi:** `tests/test_linux_agent.py`

```python
# Test senaryolari:

# 1. Registration
def test_register_linux_agent():
    """Linux platform bilgisiyle register"""
    # platform=linux, arch=amd64, distro=ubuntu, distro_version=24.04

def test_register_backward_compat():
    """Platform bilgisi olmadan register (mevcut Windows agent)"""
    # platform otomatik 'windows' atanmali

# 2. Heartbeat
def test_heartbeat_linux_config():
    """Linux agent'a Linux update metadata'si donmeli"""

def test_heartbeat_windows_config():
    """Windows agent'a Windows update metadata'si donmeli"""

def test_heartbeat_config_fallback():
    """Platform-bazli setting yoksa eski anahtara fallback"""

# 3. Deployment
def test_deployment_platform_match():
    """Linux app → Linux agent'a task olusur"""

def test_deployment_platform_mismatch():
    """Linux app → Windows agent'a task OLUSMAZ"""

def test_deployment_group_mixed_platform():
    """Karisik platformlu grupta yalnizca uyumlu agent'lara task olusur"""

# 4. Upload
def test_upload_deb_linux():
    """target_platform=linux ile .deb yukleme"""

def test_upload_deb_windows_rejected():
    """target_platform=windows ile .deb yukleme REDDEDILIR"""

def test_upload_msi_linux_rejected():
    """target_platform=linux ile .msi yukleme REDDEDILIR"""

# 5. Self-Update
def test_agent_update_upload_linux():
    """Linux platform ile agent update upload"""

def test_agent_update_upload_cross_platform_isolation():
    """Linux update, Windows settings'i DEGISTIRMEZ"""
```

#### 5.2 Agent Unit Test'leri

**Yeni test dosyalari:**

```
internal/system/info_linux_test.go        # CPU/RAM/disk okuma
internal/system/uuid_linux_test.go        # UUID kaliciligi
internal/system/sessions_linux_test.go    # who parse
internal/system/profile_linux_test.go     # /etc/os-release parse
internal/ipc/unixsocket_linux_test.go     # UDS server/client
internal/installer/deb_linux_test.go      # dpkg mock
internal/installer/script_linux_test.go   # sh execution mock
internal/remotesupport/vnc_linux_test.go  # x11vnc mock
internal/remotesupport/dialog_linux_test.go # zenity mock
```

#### 5.3 Integration Test Senaryolari

| Senaryo | Aciklama |
|---------|----------|
| Linux register → heartbeat → signal | Temel yasam dongusu |
| Linux deployment → download → deb install → status | Uygulama kurulum dongusu |
| Linux remote support → approve → x11vnc → end | RS tam dongusu |
| Linux self-update → staging → apply → restart | Guncelleme dongusu |
| Mixed group deployment | Karisik platformlu gruptaki davranis |

#### 5.4 E2E/Smoke Checklist Ekleri

```
## Linux Agent Smoke
- [x] Linux agent register → agents listesinde platform=linux gorunur
- [x] Heartbeat → sistem bilgisi (distro, CPU, RAM) dogru
- [x] Linux .deb uygulama upload → applications listesinde platform=linux
- [x] Deployment → Linux agent'a task iletilir
- [x] Deployment → platform uyumsuzluk skip + log
- [x] Remote support → x11vnc session → noVNC viewer
- [x] Remote support → cift monitor
- [x] Self-update → Linux agent yeni versiyona gecer
- [x] Agent update upload (platform=linux) → settings dogru
```

#### 5.5 CI Genisletmesi

```yaml
# .github/workflows/test-linux-agent.yml
jobs:
  server-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
      - name: Run server tests (Linux senaryolari dahil)
        run: cd server && pytest tests/ -v

  agent-build-linux:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Go
        uses: actions/setup-go@v5
      - name: Build Linux binary
        run: cd agent && GOOS=linux GOARCH=amd64 go build -o build/appcenter-agent ./cmd/service/
      - name: Run Linux tests
        run: cd agent && go test ./... -v -tags linux
```

**Kabul kriterleri:**

- [x] Tum server test seti green (mevcut + yeni Linux testleri)
- [x] Agent Linux build basarili
- [x] Agent Linux testleri basarili
- [x] Mevcut Windows testlerinde regresyon yok
- [x] CI pipeline her iki platform icin calisir

---

### Faz 6 — Operasyonel Hazirlik ve Rollout

**Amac:** Kontrollu canli gecis.

#### 6.1 On Hazirlik

- `Linux Pilot` grubu olustur (server UI)
- `Remote Support` grubuna Linux agent'lari ekle (RS icin)
- deb paketini pilot makinelere dagit

#### 6.2 Pilot Kurulumu

```bash
# Her pilot makinede:
sudo APPCENTER_SERVER_URL="https://appcenter.akgun.com.tr" \
     dpkg -i appcenter-agent_0.2.0_amd64.deb

# Bagimliliklari coz (x11vnc, zenity)
sudo apt-get install -f -y

# Kontrol
systemctl status appcenter-agent
journalctl -u appcenter-agent -f
```

#### 6.3 Rollout Dalga Plani

| Dalga | Kapsam | Sure | Geri donus kriteri |
|-------|--------|------|--------------------|
| Dalga-1 | 5 ajan (pilot) | 7 gun | Herhangi bir critical bug |
| Dalga-2 | 25 ajan | 7 gun | >%5 basarisiz heartbeat |
| Dalga-3 | Genis yayin | Surekli | Karar bazli |

#### 6.4 Rollback Proseduru

**Server tarafi:**
1. `.env` → `REMOTE_SUPPORT_ENABLED=false` (gerekirse)
2. Acik Linux RS oturumlarini sonlandir
3. Son stabil server release'e donus (gerekirse)

**Agent tarafi:**
```bash
sudo systemctl stop appcenter-agent
sudo dpkg -r appcenter-agent
# veya: onceki versiyonu kur
sudo dpkg -i appcenter-agent_0.1.0_amd64.deb
```

**Deployment freeze:**
- Linux target_platform'lu deployment'lari devre disi birak

#### 6.5 Izleme

- Dashboard'da platform bazli agent sayilari
- Heartbeat basarisizlik orani izleme (Linux vs Windows)
- Remote support session basari orani izleme

#### 6.6 Runbook Guncelleme

Guncellenecek dosyalar:
- `server/docs/OPERATIONS_RUNBOOK.md` — Linux agent bolumleri
- `server/docs/SMOKE_CHECKLIST.md` — Linux smoke maddeleri

Yeni dokumanlar:
- `server/docs/LINUX_AGENT_RUNBOOK.md` — kurulum, guncelleme, sorun giderme
- `server/docs/LINUX_REMOTE_SUPPORT_X11VNC.md` — x11vnc yapisi ve sorun giderme

**Kabul kriterleri:**

- [x] Pilot 7 gun incidentsiz
- [x] Rollback adimlari tatbik edilmis ve dogrulanmis
- [x] Runbook guncel

---

### Faz 7 — Store (En Son Faz, Opsiyonel)

**Amac:** Linux Store entegrasyonu ihtiyac olursa eklemek.

**Not:** Bu faz intentionally en sona alinmistir. Core ajan/deployment/remote support stabil olmadan baslatilmaz. Linux'ta tray uygulamasi olmadigindan store erisimleri farkli bir mekanizma ile saglanabilir (web UI, CLI tool, veya Unix socket uzerinden IPC komutu).

**Isler:**

- Linux store listeleme kurallari (platform filtrelemesi)
- `GET /agent/store` endpoint'inde platform filtrelemesi
- Store install komutu: IPC uzerinden `install_from_store` action'i (Unix socket)
- CLI araci: `appcenter-agent --store-list`, `appcenter-agent --store-install {app_id}`
- Package uninstall capability matrisi:
  - `.deb`: `dpkg -r {package_name}` (package name bilgisi gerekli)
  - `.sh`/`.tar.gz`: uninstall destegi sinirli (uygulama bazli uninstall script gerekliligi)

**Kabul kriterleri:**

- [x] Linux store install akisi hatasiz
- [x] Platform disi paketler store'da gorunmez
- [x] CLI ile store erisimi calisir

---

## 4. x11vnc Uygulama Detayi (Agent Tarafi)

### 4.1 Gereken Paketler

| Paket | Durum | Amac |
|-------|-------|------|
| `x11vnc` | Zorunlu | VNC server |
| `zenity` | Onerilen | Onay dialog (GNOME/GTK) |
| `kdialog` | Alternatif | Onay dialog (KDE) |
| `xauth` | Ortama gore | X11 auth |
| `xdotool` | Opsiyonel | Monitor tespiti |
| `netcat-openbsd` | Opsiyonel | Port diagnostic |

### 4.2 Komut Ornekleri

**Tek monitor:**
```bash
x11vnc \
  -display :0 \
  -rfbport 20010 \
  -passwd {session_password} \
  -once \
  -noxdamage \
  -shared \
  -forever \
  -timeout 300 \
  -nopw
```

Not: `-passwd` parametresi kullanildiginda `-nopw` ile birlikte olmali (x11vnc parola uyarisi engeli).

**Coklu monitor:**
```bash
# Monitor 1 (sol)
x11vnc -display :0 -clip xinerama0 -rfbport 20010 -passwd {pw} -shared -forever

# Monitor 2 (sag)
x11vnc -display :0 -clip xinerama1 -rfbport 20011 -passwd {pw} -shared -forever
```

### 4.3 Operasyon Notlari

- Helper sadece active session boyunca calisir
- PID tracking zorunlu (`cmd.Process.Pid`)
- Oturum kapanisinda zorla cleanup:
  1. `syscall.Kill(pid, syscall.SIGTERM)`
  2. 3 saniye bekle
  3. `syscall.Kill(pid, syscall.SIGKILL)` (hala calisiyor ise)
- Port kullanilabilirlik kontrolu: baslat → 5 sn icinde port dinleme teyidi → basarisiz ise hata

### 4.4 Allowlist

Agent'in calistirabilecegi helper komutlari:

```go
var allowedCommands = map[string]bool{
    "x11vnc":   true,
    "zenity":   true,
    "kdialog":  true,
    "xrandr":   true,
    "loginctl": true,
    "xdpyinfo": true,
}
```

Baska komut calistirilmaz. Tum argumanlar `exec.Command(name, args...)` ile parcali liste olarak verilir (shell injection onlemi).

---

## 5. Guvenlik ve Uyumluluk Gereksinimleri

| Gereksinim | Uygulama |
|-----------|----------|
| Artifact hash verify | sha256, download sonrasi zorunlu |
| Komut allowlist | Yalnizca belirlenmis komutlar calistirilir |
| Shell injection | exec.Command parcali arguman — shell yok |
| IPC guvenlik | Unix socket 0660 izin, root sahiplik |
| Config guvenlik | `/etc/appcenter-agent/config.yaml` 0600 izin |
| UUID guvenlik | `/etc/appcenter-agent/uuid` 0600 izin |
| VNC password | Her oturumda rastgele, oturum sonunda temizlenir |
| systemd sertlestirme | ProtectSystem=strict, ProtectHome=yes |
| Audit log | RS session create/approve/end, deployment platform mismatch, update publish |
| Permission modeli | Mevcut RBAC ile uyumlu |

---

## 6. Dokumantasyon Teslimleri

**Guncellenecek mevcut dosyalar:**

| Dosya | Degisiklik |
|-------|-----------|
| `PLAN.md` | Linux agent fazlari eklenir |
| `server/CLAUDE.md` | Platform-aware kurallar eklenir |
| `agent/CLAUDE.md` | Linux build/deploy komutlari eklenir |
| `docs/OPERATIONS_RUNBOOK.md` | Linux agent bolumleri |
| `docs/SMOKE_CHECKLIST.md` | Linux smoke maddeleri |
| `docs/TESTING_AND_CI.md` | Linux test senaryolari |
| `AppCenter_Technical_Specification_v1_1.md` | Platform alanlari, yeni uzantilar |

**Yeni dokumanlar:**

| Dosya | Icerik |
|-------|--------|
| `docs/LINUX_AGENT_RUNBOOK.md` | Kurulum, config, guncelleme, sorun giderme |
| `docs/LINUX_REMOTE_SUPPORT_X11VNC.md` | x11vnc yapisi, komut referansi, troubleshoot |

---

## 7. Acik Riskler ve Azaltma Planlari

| # | Risk | Etki | Azaltma |
|---|------|------|---------|
| 1 | Wayland yayginligi (Ubuntu 24.04 default) | x11vnc calismaz | X11 oturum tespiti zorunlu; Wayland ise RS reddedilir ve log yazilir. Kullanicilar `GDM_X11` veya `Session=ubuntu-xorg` ile giris yapmali. |
| 2 | Distro farklari (Ubuntu vs Pardus paket yollari) | Kurulum basarisizligi | Ortak Debian tabani + capability check (x11vnc, zenity varligini teyit) |
| 3 | x11vnc bakimi durmus | Guvenlik acigi, uyumsuzluk | Ubuntu/Pardus repo'sundaki son kararlı surumu kullan. Gelecekte alternatif (wayvnc vb.) mimari abstraction ile eklenebilir. |
| 4 | Coklu monitor performansi | Yavaslik, yuksek CPU | Monitor sayisi limiti (max 4), FPS/sikistirma ayarlari |
| 5 | Regresyon riski (Windows) | Mevcut Windows akisi bozulur | Platform-aware test matrix, tum mevcut testler korunur, rollout dalgasi |
| 6 | CGO_ENABLED=0 ile derleme | Bazi Go kutuphaneleri CGO gerektirir | Pure Go kutuphaneleri tercih et; syscall.Statfs, /proc parsing gibi platform API'leri CGO gerektirmez |
| 7 | systemd-detect-virt bagimliligi | Tum distro'larda olmayabilir | Fallback: DMI bilgisi okuma (/sys/class/dmi/id/) |

---

## 8. Uygulama Sirasina Gore Is Paketi Ozet

| Sira | Faz | Kapsam | Bagimlilk |
|------|-----|--------|-----------|
| 1 | Faz 0 | Kontrat + tasarim dondurma | — |
| 2 | Faz 1 | **Server:** DB migration, schema, API, deployment filtreleme, upload validation, UI | Faz 0 |
| 3 | Faz 2 | **Agent:** Linux core parity (register/heartbeat/signal/install/IPC/systemd/deb) | Faz 1 |
| 4 | Faz 3 | **Agent:** Linux remote support (x11vnc, zenity, monitor tespiti) | Faz 2 |
| 5 | Faz 4 | **Server + Agent:** Self-update platform ayrimi | Faz 1 |
| 6 | Faz 5 | Test/CI sertlestirme | Faz 1-4 |
| 7 | Faz 6 | Pilot rollout + runbook | Faz 5 |
| 8 | Faz 7 | Store (en son, opsiyonel) | Faz 6 |

**Paralel calisma imkani:**
- Faz 1 (server) ve Faz 2 (agent) sirayla yapilmali (server API'si agent'dan once hazir olmali)
- Faz 3 (RS) ve Faz 4 (self-update) birbirine bagimsiz, Faz 2'den sonra paralel yapilabilir

**Bu sira degistirilmeyecek ana ilkeler:**
1. **Server API degisiklikleri agent'dan once**
2. **Core ajan parity ilk faz**
3. **Store en son faz**
4. **Mevcut Windows akisi hicbir fazda kirilmaz**
