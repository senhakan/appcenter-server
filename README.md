# appcenter-server

## Durum

- Faz 1 tamamlandı.
- Faz 2 tamamlandı.
- Faz 3 tamamlandı.
- Faz 4 tamamlandı.
- Faz 5 tamamlandı.

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
- Son sonuc: `4 passed`
