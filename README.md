# appcenter-server

## Durum

- Faz 1 tamamlandı.
- Faz 2 tamamlandı.
- Faz 3 tamamlandı.
- Faz 4 tamamlandı.
- Faz 5 tamamlandı.

## Bu Sunucuda Canli Calisma Notu

- Bu repo bu sunucuda canli olarak kullanilir:
  - kaynak: `/root/appcenter/server`
  - calisan uygulama: `/opt/appcenter/server`
  - servis: `appcenter` (`127.0.0.1:8000`)
- Yapilan degisiklikler deploy edilmeden tamamlanmis sayilmaz.
- Testler ve smoke dogrulamalari bu sunucuda calisan servis uzerinde yapilmalidir.

## Faz 1 Tamamlananlar

- Cekirdek altyapi: `app/database.py`, `app/models.py`, `app/config.py`, `app/main.py`, `app/auth.py`
- API baslangici: `app/api/v1/auth.py`, `app/api/v1/agent.py`
- `GET /health`
- `POST /api/v1/auth/login`
- `POST /api/v1/agent/register`
- `POST /api/v1/agent/heartbeat`

## Faz 2 Tamamlananlar

- Guvenli dosya islemleri: `app/utils/file_handler.py`
- Uygulama servis katmani: `app/services/application_service.py`
- `POST /api/v1/applications` (multipart upload)
- `GET /api/v1/applications`
- `GET /api/v1/applications/{app_id}`
- `DELETE /api/v1/applications/{app_id}`
- `GET /api/v1/agent/download/{app_id}` (`Range` destegi)

## Faz 3 Tamamlananlar

- Deployment servis katmani: `app/services/deployment_service.py`
- Heartbeat task atama: `app/services/heartbeat_service.py`
- Scheduler: `app/tasks/scheduler.py`
- Yeni endpointler:
- `POST /api/v1/deployments`
- `GET /api/v1/deployments`
- `GET /api/v1/deployments/{deployment_id}`
- `PUT /api/v1/deployments/{deployment_id}`
- `DELETE /api/v1/deployments/{deployment_id}`
- `POST /api/v1/agent/task/{task_id}/status`

## Faz 4 Tamamlananlar

- UI sayfalari ve route'lari:
- `GET /login`
- `GET /dashboard`
- `GET /agents`
- `GET /agents/{agent_uuid}`
- `GET /applications`
- `GET /applications/upload`
- `GET /deployments`
- `GET /deployments/create`
- `GET /settings`
- Template dosyalari:
- `app/templates/base.html`
- `app/templates/auth/login.html`
- `app/templates/dashboard.html`
- `app/templates/agents/list.html`
- `app/templates/agents/detail.html`
- `app/templates/applications/list.html`
- `app/templates/applications/upload.html`
- `app/templates/deployments/list.html`
- `app/templates/deployments/create.html`
- `app/templates/settings.html`
- Ortak UI varliklari:
- `app/static/css/app.css`
- `app/static/js/api.js`

## Faz 5 Tamamlananlar

- Store endpoint:
- `GET /api/v1/agent/store`
- Settings endpointleri:
- `GET /api/v1/settings`
- `PUT /api/v1/settings`
- Dashboard istatistik endpointi:
- `GET /api/v1/dashboard/stats`
- Agent update upload:
- `POST /api/v1/agent-update/upload`
- Agent update download:
- `GET /api/v1/agent/update/download/{filename}`
- Error handling:
- API exception formati standardlastirildi (`status` + `detail`)

## Faz 6 Tamamlananlar (UI + Yönetim Iyilestirmeleri)

- Uygulama yukleme akisi:
- `install_args` / `uninstall_args` alanlari eklendi
- opsiyonel ikon yukleme eklendi
- `/uploads` static mount ile ikon servisleme aktif
- Uygulama adi tekilligi:
- `display_name` case-insensitive unique kontrolu (create/update)
- Grup yonetimi:
- `GET /api/v1/groups`
- `GET /api/v1/groups/{group_id}`
- `POST /api/v1/groups`
- `PUT /api/v1/groups/{group_id}`
- `PUT /api/v1/groups/{group_id}/agents`
- Duzenleme ekranlari (full form):
- `GET /applications/{app_id}/edit`
- `GET /deployments/{deployment_id}/edit`
- `GET /groups/{group_id}/edit`
- Deployment form iyilestirmesi:
- uygulama/grup/agent secimi combobox uzerinden
- Group assignment:
- soldan saga dual-listbox akisi (atanmamis -> gruptaki ajanlar)
- SQLite startup migration:
- eski veritabani icin `applications` tablosuna eksik kolonlari idempotent ekleme
- Agent detail: login session gosterimi:
  - Agent heartbeat payload'inda `logged_in_sessions` alani (local/RDP) ile gelir
  - Server agents tablosuna JSON olarak persist eder ve agent detail ekraninda gosterir
- Agent system profile + history:
  - Agent periyodik `system_profile` snapshot gonderir (OS/donanim/virtualization/disk)
  - Server snapshot'u saklar ve degisimleri `agent_system_profile_history` tablosunda izler
  - Agent detail ekraninda sistem bilgileri "Ajan Detay" alaninda gorunur
  - "Sistem Gecmisi" sekmesi yalnizca degisen alanlari listeler (eski → yeni diff)

## Son Dogrulama (2026-02-13)

- `POST /api/v1/auth/login` -> `200`
- `POST /api/v1/applications` -> `200`
- `GET /api/v1/applications` -> `200`
- `GET /api/v1/applications/{app_id}` -> `200`
- `GET /api/v1/agent/download/{app_id}` -> `200`
- `GET /api/v1/agent/download/{app_id}` + `Range: bytes=0-31` -> `206`
- `DELETE /api/v1/applications/{app_id}` -> `200`
- `POST /api/v1/deployments` -> `200`
- `POST /api/v1/agent/heartbeat` (task assignment) -> `200` + command
- ikinci heartbeat (tekrar task yok) -> `200` + `0 command`
- `POST /api/v1/agent/task/{task_id}/status` -> `200`
- `GET /login`, `GET /dashboard`, `GET /agents`, `GET /applications`, `GET /deployments`, `GET /settings` -> `200`
- `GET /api/v1/dashboard/stats` -> `200`
- `GET /api/v1/settings` -> `200`
- `PUT /api/v1/settings` -> `200`
- `GET /api/v1/agent/store` -> `200`
- `POST /api/v1/agent-update/upload` -> `200`
- `GET /api/v1/agent/update/download/{filename}` -> `200`

## Kurulum

```bash
python3.9 -m venv venv39
source venv39/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Test

```bash
source venv39/bin/activate
pytest -q
```

- Test dosyalari:
- `tests/conftest.py`
- `tests/test_phase5_api.py`
- Son sonuc: `8 passed`
- Son sonuc: `19 passed`

## Dokumantasyon

- `docs/DEVELOPMENT_WORKFLOW.md`
- `docs/OPERATIONS_RUNBOOK.md`
- `docs/DEPLOYED_SERVER_SNAPSHOT.md`
- `docs/SMOKE_CHECKLIST.md`
- `docs/TESTING_AND_CI.md`
- `docs/ROADMAP_AND_THEME.md`
