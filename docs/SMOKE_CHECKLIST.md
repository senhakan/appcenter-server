# Smoke Checklist

Her deploy sonrasi minimum kontrol listesi.

## A. API Baslangic Kontrolu

- `GET /health` -> 200
- `POST /api/v1/auth/login` -> 200

## B. Uygulama Akisi

- `POST /api/v1/applications` -> 200
- `GET /api/v1/applications` -> 200
- `GET /api/v1/agent/download/{app_id}` -> 200
- `GET /api/v1/agent/download/{app_id}` + Range -> 206

## C. Deployment + Task Akisi

- `POST /api/v1/deployments` -> 200
- `POST /api/v1/agent/heartbeat` -> command doner
- ikinci heartbeat -> ayni command tekrar donmez
- `POST /api/v1/agent/task/{task_id}/status` -> 200

## D. Faz 5 Akislari

- `GET /api/v1/dashboard/stats` -> 200
- `GET /api/v1/settings` -> 200
- `PUT /api/v1/settings` -> 200
- `GET /api/v1/agent/store` -> 200
- `POST /api/v1/agent-update/upload` -> 200
- `GET /api/v1/agent/update/download/{filename}` -> 200

## E. UI Sayfalari

- `/login`, `/dashboard`, `/agents`, `/applications`, `/deployments`, `/settings` -> 200
