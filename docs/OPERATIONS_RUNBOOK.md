# Operations Runbook

Bu dokuman production ortami icin deploy, smoke ve rollback adimlarini tanimlar.

## 1. Environment

- App dizini: `/opt/appcenter/`
- Veri dizini: `/var/lib/appcenter/`
- Log dizini: `/var/log/appcenter/`
- Service: `appcenter` (systemd)
- Reverse proxy: nginx

### 1.1 Bu Sunucuda Aktif Deployment Profili

- Kaynak repo dizini: `/root/appcenter/server`
- Calisan uygulama dizini: `/opt/appcenter/server`
- Virtual env: `/opt/appcenter/server/venv`
- Environment file: `/opt/appcenter/server/.env`
- Uvicorn bind: `0.0.0.0:8000` (nginx upstream `127.0.0.1:8000`)
- systemd unit: `/etc/systemd/system/appcenter.service`
- nginx conf: `/etc/nginx/custom-conf/appcenter.akgun.com.tr.conf`

## 2. Deploy Adimlari

### 2.1 Git Pull ile Deploy (opsiyonel)

```bash
cd /opt/appcenter/server
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart appcenter
sudo systemctl status appcenter --no-pager
```

Not:
- `rsync --delete` ile deploy yapiliyorsa `.env` dosyasi korunmalidir.
- Ornek: `--exclude '.env'`
- `venv` kopyalama/overwrite, `uvicorn` shebang'lerini bozup systemd `203/EXEC` hatasi uretebilir. Bu nedenle `venv` dizinlerini deploy kapsamindan cikarin.

### 2.2 Bu Sunucuda Kullanilan Rsync Deploy Akisi

```bash
rsync -av --delete \
  --exclude '.git' \
  --exclude 'venv' \
  --exclude 'venv39' \
  --exclude '.env' \
  /root/appcenter/server/ /opt/appcenter/server/

sudo systemctl restart appcenter
sudo systemctl is-active appcenter
```

### 2.3 .env Kritik Notlari

- `CORS_ORIGINS` degeri JSON list formatinda olmali:
  - dogru: `CORS_ORIGINS=["*"]`
  - yanlis: `CORS_ORIGINS=*`
- `rsync --delete` `.env` dosyasini silebilir; mutlaka exclude edin.

## 3. Hizli Production Smoke

```bash
curl -f http://127.0.0.1:8000/health
```

Web login ve kritik akislar manuel kontrol edilir:
- `/login`
- app upload
- deployment create
- application/deployment/group edit ekranlari
- group create + dual-listbox agent assignment
- agent heartbeat/task flow
- agent detail: login session listesi (local/RDP) gorunumu
- settings update
  - `ui_timezone` (IANA) guncellemesi ve zaman gosterimlerinin dogrulanmasi
- agent update upload/download

Detayli checklist: `docs/SMOKE_CHECKLIST.md`.

### 3.1 Bu Sunucuda Dogrudan Uygulama Kontrolu

```bash
curl -sS http://127.0.0.1:8000/health
curl -sS http://127.0.0.1:8000/ | jq .
```

### 3.2 Inventory Dashboard Kart Dogrulamasi

- `GET /api/v1/inventory/dashboard` cevabinda asagidaki alanlar bulunmalidir:
  - `total_unique_software`
  - `agents_with_inventory`
  - `added_today`
  - `removed_today`
  - `license_violations`

## 4. Log ve Izleme

```bash
sudo journalctl -u appcenter -f
```

## 4.1 UI Bos Ekran / JS Cache Sorun Giderme

Deploy sonrasi UI bos gorunuyorsa (dashboard/agent listesi bos, kartlar dolmuyor) genelde tarayicinin eski `/static/js/api.js` dosyasini cache'lemesinden olur.

- Cozum: hard refresh (`Ctrl+F5`) veya cache temizleyip tekrar login olun.
- Not: Bu repo static asset'lerde `?v={{ app_version }}` cache-bust kullanir. Yine de proxy/tarayici cache'i bazen etkileyebilir.

DB saglik kontrolu:

```bash
sqlite3 /var/lib/appcenter/appcenter.db "PRAGMA integrity_check;"
```

Not: Bu hostta `sqlite3` binary her zaman kurulu olmayabilir. Alternatif olarak `/opt/appcenter/server/venv/bin/python` ile DB kontrol script'i calistirilabilir.

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

## 6. Nginx Notu (Bu Sunucu)

- Root path davranisi `/login`e yonlendirecek sekilde ayarlidir.
- App upstream: `127.0.0.1:8000`
