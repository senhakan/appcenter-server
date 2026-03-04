# AppCenter Technical Specification (PostgreSQL Only)

Surum: 1.1.4  
Tarih: 2026-03-04

## 1. Kapsam

Bu dokuman AppCenter Server tarafinin guncel teknik durumunu ozetler.
Veritabani altyapisi tamamen PostgreSQL'dir.

## 2. Teknoloji

- Python 3.9+
- FastAPI
- SQLAlchemy 2.x
- PostgreSQL 12+
- Jinja2 + Tabler UI
- systemd + nginx

## 3. Veritabani Kurallari

- `DATABASE_URL` PostgreSQL olmali (`postgresql+psycopg2://...`).
- Uygulama startup asamasinda idempotent migration adimlari calisir.
- Migration kontrolleri `information_schema` uzerinden yapilir.
- Tum timestamp alanlari UTC olarak tutulur.

## 4. Cekirdek API Gruplari

- Auth: `/api/v1/auth/*`
- Agent: `/api/v1/agent/*`
- Web/UI API: `/api/v1/*`
- Inventory/Timeline: `/api/v1/agents/{uuid}/timeline`, `/api/v1/inventory/*`
- Remote Support: `/api/v1/remote-support/*`

## 5. Isletim

- Calisan servis: `appcenter.service`
- Canli dizin: `/opt/appcenter/server`
- Kaynak dizin: `/root/appcenter/server`
- Health endpoint: `GET /health`

## 6. Dogrulama Komutlari

```bash
systemctl is-active appcenter
curl -sS http://127.0.0.1:8000/health
PGPASSWORD='***' psql -h 127.0.0.1 -U appcenter -d appcenter -c "SELECT 1;"
```

## 7. Not

Bu dosya PostgreSQL-only modele gecis sonrasi sadeleştirilmis teknik referanstir.
Detayli operasyon adimlari icin `docs/OPERATIONS_RUNBOOK.md` kullanilir.
