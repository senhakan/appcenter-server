# Operations Runbook

Bu dokuman production ortami icin deploy, smoke ve rollback adimlarini tanimlar.

## 1. Environment

- App dizini: `/opt/appcenter/`
- Veri dizini: `/var/lib/appcenter/`
- Log dizini: `/var/log/appcenter/`
- Service: `appcenter` (systemd)
- Reverse proxy: nginx

### 1.2 Guacamole Durumu (2026-02-26)

- Guacamole viewer kod yolu alternatif cozum olarak korunur.
- Guacamole container'lari varsayilan olarak kapalidir (pasif profil).
- Guacamole'yi tekrar devreye almak icin tek referans:
  - `config/guacamole/REENABLE.md`
  - `config/guacamole/docker-compose.guacamole.yml`
  - `config/guacamole/nginx.guacamole.conf.snippet`

### 1.3 noVNC Calisma Durumu (2026-02-23)

- Viewer modu: `REMOTE_SUPPORT_NOVNC_MODE=embedded`
- WS bridge modu: `REMOTE_SUPPORT_WS_MODE=internal`
- `/novnc-ws` endpoint'i FastAPI uygulamasi icinde calisir (`:8000`).
- Harici noVNC/websockify servisleri varsayilan olarak kapali tutulur:
  - `appcenter-novnc-ws` -> disabled/inactive
  - `novnc-ws-172` docker container -> stopped
- Session UI davranisi:
  - Baglanti butonu toolbar uzerindedir (`tool-connect`).
  - Session state `approved/connecting/active` ise sayfa acilisinda auto-connect dener.
  - Session state `pending_approval` icin bekleme/aciklama metni gosterilir; onaylaninca otomatik baglanir.
  - Kullanici metinlerinde `noVNC` yerine `Canli ekran` terimi kullanilir.

### 1.4 Store Grubu + Tray Policy (2026-02-24)

- `Store` grubu sistem grubudur:
  - UI'dan silinemez.
  - Grup adi degistirilemez.
- Agent heartbeat `config` alaninda `store_tray_enabled` bayragi dondurulur.
  - Ajan `Store` grubundaysa: `true`
  - Degilse: `false`
- Agent service bu policy'i uygular:
  - `true` iken `appcenter-tray.exe` kullanici oturumunda calisiyor durumda tutulur.
  - `false` iken `appcenter-tray.exe` sonlandirilir.
- `/groups` ekraninda "Gruba Ajan Ata" kaydindan sonra secili grup korunur (dropdown resetlenmez); basari toast'i gosterilir.

### 1.5 Remote Support Akis Notlari (2026-02-26)

- Pending approval kapanis davranisi:
  - Session penceresi kapatilirsa `pending_approval` oturumlar `/cancel` endpoint'i ile sonlandirilir.
  - Acik pencere yokken ayni ajan icin tekrar `Baglan` tiklanirsa mevcut bekleyen session penceresi yeniden acilir.
  - Acik pencere varken tekrar `Baglan` tiklanirsa bilgi toast'i gosterilir.
- Session UI:
  - Ustteki session detay tablosu kaldirildi.
  - Kullanici reddederse modal gosterilir: `Baglanti Istegi Kabul Edilmedi`.
  - Modal `Tamam` ile session penceresi kapatilir.
  - Pending overlay icine `Iptal` butonu eklendi (istegi iptal + pencere kapatma akisi).
- Ajanlar sayfasi:
  - `Baglanti Talebi` modalinda:
    - `Enter` (Shift'siz): talep gonder
    - `Shift+Enter`: yeni satir
    - `Escape`: modal kapat

### 1.6 Dual-Monitor noVNC Davranisi (2026-02-26)

- noVNC ticket endpoint monitor parametresi destekler:
  - `GET /api/v1/remote-support/sessions/{id}/novnc-ticket?monitor=1` -> `vnc_port=20010`
  - `GET /api/v1/remote-support/sessions/{id}/novnc-ticket?monitor=2` -> `vnc_port=20011`
  - `monitor=2` ve ajan `monitor_count < 2` ise `monitor_not_available` doner.
- Session UI davranisi:
  - Baglanti baslarken M1 hemen baglanir ve aktif goruntu olarak kalir.
  - M2, M1 baglandiktan yaklasik 2 sn sonra arka planda preconnect olur.
  - M2 preconnect asamasinda aktif ekran otomatik degismez (M1 gorunumu sabit kalir).
  - Monitor degisimi sadece kullanici seciminde olur; M1<->M2 gecis animasyonu iki yonlu calisir.

### 1.7 Session Recording Servisi (2026-03-02)

- Konfigurasyon:
  - UI: `Ayarlar > Session Recording > Session Recording Aktif`
  - DB key: `session_recording_enabled` (`true|false`)
  - DB key: `session_recording_fps` (`1-30`, varsayilan `10`)
- Calisma modeli:
  - noVNC baglantisi `connected` oldugunda kayit otomatik baslatilir.
  - Session sonlandiginda kayit otomatik durdurulur.
- Kayit motoru:
  - `gst-launch-1.0` + `rfbsrc` + `x264enc` + `mp4mux`
  - Cikti yolu: `/var/lib/appcenter/uploads/recordings/session_<session_id>/`
- Servis durumu:
  - UI ayni Ayarlar ekraninda `Aktif/Pasif` rozetini gosterir.
  - Eksik bagimlilik varsa listelenir.
- API:
  - `GET /api/v1/remote-support/recording/service-status`
  - `POST /api/v1/remote-support/sessions/{id}/recording/start`
  - `POST /api/v1/remote-support/sessions/{id}/recording/stop`
  - `GET /api/v1/remote-support/recordings`
  - `GET /api/v1/remote-support/recordings/{recording_id}/stream`
- GStreamer paketleri (Ubuntu 20.04):
  ```bash
  apt-get install -y gstreamer1.0-tools gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly gstreamer1.0-libav
  ```

### 1.1 Bu Sunucuda Aktif Deployment Profili

- Kaynak repo dizini: `/root/appcenter/server`
- Calisan uygulama dizini: `/opt/appcenter/server`
- Virtual env: `/opt/appcenter/server/venv`
- Environment file: `/opt/appcenter/server/.env`
- Uvicorn bind: `0.0.0.0:8000` (nginx upstream `127.0.0.1:8000`)
- systemd unit: `/etc/systemd/system/appcenter.service`
- nginx conf: `/etc/nginx/custom-conf/appcenter.akgun.com.tr.conf`

## 2. Deploy Adimlari

Zorunlu kural (bu sunucu):
- Server kodunda yapilan her degisiklik ayni oturumda `/opt/appcenter/server` dizinine uygulanir.
- Deploy sonrasi `appcenter` servisi restart edilir.
- En az `GET /health` ve ilgili akis icin smoke kontrolu yapilir.

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
- noVNC calisma modu:
  - `REMOTE_SUPPORT_NOVNC_MODE=embedded` -> noVNC iframe yerine session sayfasinda dogrudan RFB (embed)
  - `REMOTE_SUPPORT_NOVNC_MODE=iframe` -> onceki stabil iframe akisi (hizli fallback)
- WS bridge modu:
  - `REMOTE_SUPPORT_WS_MODE=internal` -> `/novnc-ws` FastAPI icinde calisir (ayri websockify servisi gerekmez)
  - `REMOTE_SUPPORT_WS_MODE=external` -> harici websockify (6082) akisi

### 2.4 Agent Update Publish (Zorunlu Standart)

Agent update yayinlarken manuel upload yerine her zaman bu script kullanilir:

```bash
cd /root/appcenter/server
APPCENTER_ADMIN_USERNAME='admin' APPCENTER_ADMIN_PASSWORD='admin123' \
./scripts/publish-agent-update.sh --version 0.1.19
```

Alternatif (canli dizin):

```bash
cd /opt/appcenter/server
APPCENTER_ADMIN_USERNAME='admin' APPCENTER_ADMIN_PASSWORD='admin123' \
./scripts/publish-agent-update.sh --version 0.1.19
```

Not:
- Script: test (`go test ./...`) + windows agent build + `POST /api/v1/agent-update/upload`
- Build atlamak icin: `--no-build --file <path/to/exe|msi>`

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
  - remote support alanlari gorunumu:
    - `Remote State`
    - `Remote Session ID`
    - `Remote Helper`
    - `Remote Guncelleme`
- settings update
  - `ui_timezone` (IANA) guncellemesi ve zaman gosterimlerinin dogrulanmasi
- agent update upload/download
- RBAC smoke:
  - viewer: mutating endpointlerde `403` (or: `POST /api/v1/groups`)
  - operator: operasyon endpointlerinde `200`, settings/users endpointlerinde `403`
  - admin: users/settings endpointlerinde `200`

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

### 5.1 Remote Support Snapshot (2026-02-20)

- Server runtime snapshot:
  - `/opt/appcenter/server/.backup_remote_support_runtime_20260220_194350`
  - Icerik: `app/models.py`, `app/schemas.py`, `app/database.py`, `app/services/heartbeat_service.py`, `app/templates/agents/detail.html`, `.env`, `appcenter.db`
- Agent runtime snapshot (Windows test host `10.6.20.172`):
  - `C:\\Temp\\appcenter-backup-20260220_224401`
  - Icerik: `appcenter-service.exe`, `acremote-helper.exe`, `config.yaml`

### 5.2 noVNC Baseline Snapshot (2026-02-23)

- Hedef: noVNC iframe tabanli mevcut calisan duruma hizli geri donus.
- Referans git tag: `remote-support-novnc-iframe-baseline-20260223`
- Baseline kapsam:
  - Guacamole alternatif kod yolu korunur (runtime'da pasif)
  - noVNC session ekrani aktif
  - Session UI tablo duzeni + baglanti badge/mesaj akisi

Geri donus adimlari:

```bash
cd /opt/appcenter/server
git fetch --all --tags
git checkout remote-support-novnc-iframe-baseline-20260223
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart appcenter
curl -f http://127.0.0.1:8000/health
```

## 6. Nginx Notu (Bu Sunucu)

- Root path davranisi `/login`e yonlendirecek sekilde ayarlidir.
- App upstream: `127.0.0.1:8000`
