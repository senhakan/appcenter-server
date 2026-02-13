# Operations Runbook

Bu dokuman production ortami icin deploy, smoke ve rollback adimlarini tanimlar.

## 1. Environment

- App dizini: `/opt/appcenter/`
- Veri dizini: `/var/lib/appcenter/`
- Log dizini: `/var/log/appcenter/`
- Service: `appcenter` (systemd)
- Reverse proxy: nginx

## 2. Deploy Adimlari

```bash
cd /opt/appcenter/server
git pull
source venv39/bin/activate
pip install -r requirements.txt
sudo systemctl restart appcenter
sudo systemctl status appcenter --no-pager
```

## 3. Hizli Production Smoke

```bash
curl -f http://127.0.0.1:8000/health
```

Web login ve kritik akislar manuel kontrol edilir:
- `/login`
- app upload
- deployment create
- agent heartbeat/task flow
- settings update
- agent update upload/download

Detayli checklist: `docs/SMOKE_CHECKLIST.md`.

## 4. Log ve Izleme

```bash
sudo journalctl -u appcenter -f
```

DB saglik kontrolu:

```bash
sqlite3 /var/lib/appcenter/appcenter.db "PRAGMA integrity_check;"
```

## 5. Rollback

- Onceki stabil commit'e don.
- Deploy adimlarini tekrar uygula.
- Service restart + smoke tekrar.

```bash
git checkout <stable_commit>
source venv39/bin/activate
pip install -r requirements.txt
sudo systemctl restart appcenter
```
