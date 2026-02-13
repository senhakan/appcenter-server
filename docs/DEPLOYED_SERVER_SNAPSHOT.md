# Deployed Server Snapshot

Bu dokuman mevcut production sunucuda uygulanan deployment topolojisini ozetler.

## 1. Sunucu Bilesenleri

- App user: `appcenter`
- App root: `/opt/appcenter/server`
- Data root: `/var/lib/appcenter`
- Upload root: `/var/lib/appcenter/uploads`
- Logs: `/var/log/appcenter`

## 2. Runtime

- Python venv: `/opt/appcenter/server/venv`
- ASGI: `uvicorn app.main:app`
- Bind: `127.0.0.1:8000`
- systemd service: `appcenter`

Service dosyasi:
- `/etc/systemd/system/appcenter.service`

## 3. Reverse Proxy

- nginx uzerinden yayin
- config:
  - `/etc/nginx/custom-conf/appcenter.akgun.com.tr.conf`
- root request davranisi:
  - `/` -> `/login`

## 4. Deploy Modeli

- Kaynak:
  - `/root/appcenter/server`
- Hedef:
  - `/opt/appcenter/server`
- rsync ile senkron:
  - `.env` mutlaka exclude edilir

Ornek:

```bash
rsync -av --delete \
  --exclude '.git' \
  --exclude 'venv' \
  --exclude 'venv39' \
  --exclude '.env' \
  /root/appcenter/server/ /opt/appcenter/server/
sudo systemctl restart appcenter
```

## 5. Sık Hata ve Cozum

1. Service acilmiyor, `Failed to load environment files`
- Neden: `.env` silinmis
- Cozum: `/opt/appcenter/server/.env` geri olustur, izinleri duzelt, restart

2. App startup'ta config parse hatasi
- Neden: `CORS_ORIGINS=*` gibi hatali format
- Cozum: `CORS_ORIGINS=["*"]` kullan
