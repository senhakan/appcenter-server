# AppCenter Server - Claude Code Geliştirme Rehberi

## PROJE HAKKINDA

AppCenter, Windows bilgisayarlara uzaktan uygulama dağıtımı yapan bir Client-Server sistemidir.
Bu dosya **SERVER** tarafını kapsar. Agent tarafı ayrı bir repository/session'da geliştirilir.

**Teknoloji:** Python 3.10+, FastAPI, SQLAlchemy 2.0, SQLite (WAL mode), Jinja2, TailwindCSS  
**Deployment:** Native Linux (systemd), Docker YOK  
**Referans Doküman:** `../AppCenter_Technical_Specification_v1_1.md`

---

## DİZİN YAPISI

```
server/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application entry
│   ├── config.py               # Configuration (.env)
│   ├── database.py             # SQLAlchemy + WAL + busy_timeout
│   ├── models.py               # ORM models
│   ├── schemas.py              # Pydantic schemas
│   ├── auth.py                 # JWT authentication
│   ├── api/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── agent.py        # Agent endpoints (register, heartbeat, download, task status, store)
│   │       ├── web.py          # Web UI endpoints (agents, apps, deployments CRUD)
│   │       └── auth.py         # Login/logout endpoints
│   ├── services/
│   │   ├── __init__.py
│   │   ├── agent_service.py
│   │   ├── application_service.py
│   │   ├── deployment_service.py
│   │   └── heartbeat_service.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── file_handler.py     # Güvenli upload, sanitize filename
│   │   ├── hash_utils.py       # SHA256
│   │   └── logger.py
│   ├── tasks/
│   │   ├── __init__.py
│   │   └── scheduler.py        # APScheduler: offline check (2dk) + log cleanup (günlük)
│   ├── templates/              # Jinja2
│   │   ├── base.html
│   │   ├── components/
│   │   ├── auth/
│   │   ├── dashboard.html
│   │   ├── agents/
│   │   ├── applications/
│   │   ├── deployments/
│   │   └── settings.html
│   └── static/
│       ├── css/
│       ├── js/
│       └── icons/
├── requirements.txt
├── .env.example
├── setup.sh                    # Kurulum script'i
├── tests/
│   ├── test_agent_api.py
│   ├── test_heartbeat.py
│   └── test_upload.py
└── README.md
```

---

## KRİTİK KURALLAR

### Veritabanı
- **ZORUNLU:** Her bağlantıda `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=5000`, `PRAGMA foreign_keys=ON` çalıştır
- SQLAlchemy `event.listens_for(engine, "connect")` ile pragma'ları ayarla
- Tüm zaman damgaları **UTC** olmalı
- Log temizliği: trigger YOK, scheduler ile günde 1 kez (03:00 UTC)

### Dosya Güvenliği
- Upload edilen dosyalar `{app_id}_{hash[:8]}.{ext}` formatında saklanır
- Sadece `.msi` ve `.exe` uzantıları kabul edilir (`.zip` YOK)
- Max dosya boyutu: 2GB
- Orijinal dosya adı `original_filename` alanında saklanır

### API
- Agent auth: `X-Agent-UUID` + `X-Agent-Secret` header'ları
- Web auth: JWT Bearer token (1 saat geçerlilik)
- Store endpoint: `GET /api/v1/agent/store` (UUID path'te DEĞİL, header'da)
- Heartbeat'te `apps_changed` flag'i kontrol et: `false` ise installed_apps sync atla

### Task Yönetimi
- Task ID = `task_history` tablosundaki auto-increment ID
- Deployment oluşturulduğunda agent_applications'a kayıt ekle
- Heartbeat: sadece pending durumundakileri döndür
- Aynı task tekrar tekrar gönderilmemeli

### Deployment
- Docker YOK, native Linux kurulum
- systemd service olarak çalışır
- Nginx reverse proxy
- Path'ler: `/opt/appcenter/`, `/var/lib/appcenter/`, `/var/log/appcenter/`

---

## GELİŞTİRME SIRASI

### Faz 1: Temel Altyapı
1. `database.py` - SQLAlchemy engine + WAL pragma'ları
2. `models.py` - Tüm tablo modelleri
3. `config.py` - .env okuma
4. `main.py` - FastAPI app, CORS, static files, startup event
5. `auth.py` - JWT oluşturma/doğrulama
6. `api/v1/auth.py` - Login endpoint
7. `api/v1/agent.py` - Register + basit heartbeat

**Test:** Agent register olabiliyor mu? Heartbeat gönderiyor mu?

### Faz 2: Uygulama Yönetimi
1. `utils/file_handler.py` - Güvenli upload, sanitize filename, hash hesaplama
2. `services/application_service.py` - CRUD operasyonları
3. `api/v1/web.py` - Application upload/list/delete endpoints
4. Download endpoint (Range header desteği)

**Test:** Upload çalışıyor mu? Hash doğru mu? Download + resume çalışıyor mu?

### Faz 3: Deployment & Task
1. `services/deployment_service.py` - Deployment CRUD
2. `services/heartbeat_service.py` - Tam heartbeat logic (task assignment)
3. `tasks/scheduler.py` - Offline detection + log cleanup
4. Task status reporting endpoint

**Test:** Deployment oluştur → Agent heartbeat gönder → Task alıyor mu?

### Faz 4: Web UI
1. `templates/base.html` - Layout (TailwindCSS CDN)
2. `templates/auth/login.html`
3. `templates/dashboard.html`
4. `templates/agents/list.html` + `detail.html`
5. `templates/applications/list.html` + `upload.html`
6. `templates/deployments/list.html` + `create.html`
7. `templates/settings.html`
8. `static/js/api.js` - AJAX calls + polling

### Faz 5: Polish
1. Store API endpoint
2. Settings endpoint (okuma/yazma)
3. Dashboard istatistikleri
4. Agent update upload
5. Error handling iyileştirmesi

---

## KOMUTLAR

```bash
# Geliştirme
cd server
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Test
pytest tests/ -v

# Veritabanı kontrolü
sqlite3 /var/lib/appcenter/appcenter.db "PRAGMA integrity_check;"
sqlite3 /var/lib/appcenter/appcenter.db ".tables"
sqlite3 /var/lib/appcenter/appcenter.db "SELECT * FROM settings;"

# Production deploy
sudo systemctl restart appcenter
sudo journalctl -u appcenter -f
```

---

## NOTLAR

- Agent tarafı Go ile yazılıyor, bu repo'da DEĞİL
- Agent'ın beklediği API contract'ını değiştirirsen `../AppCenter_Technical_Specification_v1_1.md` güncelle
- Frontend'de framework YOK: Vanilla JS + TailwindCSS CDN + fetch API
- Polling: Agent list ve dashboard her 10 saniyede bir güncellenir
