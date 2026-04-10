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

- Viewer modu: DB `settings.remote_support_novnc_mode=embedded`
- WS bridge modu: DB `settings.remote_support_ws_mode=internal`
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
  - DB key: `session_recording_watermark_enabled` (`true|false`, varsayilan `false`)
- Calisma modeli:
  - noVNC baglantisi `connected` oldugunda kayit otomatik baslatilir.
  - M1 baglandiginda M1 kaydi baslar; M2 baglantisi acildiginda M2 kaydi ayrica baslar.
  - Her monitor bagimsiz kaydedilir (`M1` ve `M2` icin ayri kayit satiri/dosyasi).
  - Session sonlandiginda kayit otomatik durdurulur.
- Kayit motoru:
  - `gst-launch-1.0` + `rfbsrc` + `x264enc` + `mp4mux`
  - Cikti yolu: `/var/lib/appcenter/uploads/recordings/session_<session_id>/`
  - Dosya adinda monitor bilgisi bulunur: `recording_<id>_m1_*.mp4`, `recording_<id>_m2_*.mp4`
  - DB kayit alanlari:
    - `monitor_index` (`1|2`)
    - `target_fps`
- Servis durumu:
  - UI ayni Ayarlar ekraninda `Aktif/Pasif` rozetini gosterir.
  - Eksik bagimlilik varsa listelenir.
- API:
  - `GET /api/v1/remote-support/recording/service-status`
  - `POST /api/v1/remote-support/sessions/{id}/recording/start?monitor=1|2`
  - `POST /api/v1/remote-support/sessions/{id}/recording/stop`
  - `GET /api/v1/remote-support/recordings`
    - opsiyonel filtre: `monitor=1|2`
  - `GET /api/v1/remote-support/recordings/{recording_id}/stream`
  - `GET /api/v1/remote-support/recordings/{recording_id}/play-token`
  - `GET /api/v1/remote-support/recordings/{recording_id}/public-stream?play_token=...`
- Izleme (UI):
  - Session Recordings ekraninda kayitlar inline player ile acilir, yeni sekme acilmaz.
  - Oynatma `blob()` yerine stream URL ile yapilir (buyuk dosyada parca parca oynatma / buffering destegi).
  - Liste ekraninda `Monitör` sutunu ve `Monitör` filtresi bulunur.
- GStreamer paketleri (Ubuntu 20.04):
  ```bash
  apt-get install -y gstreamer1.0-tools gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly gstreamer1.0-libav
  ```

### 1.8 PostgreSQL Calisma Notu (2026-03-02)

- PostgreSQL:
  - Surum: `12` (Ubuntu 20.04 paketleri)
  - Data dizini: `/pg_data`
  - Cluster: `12/main`
  - Dinleme: sadece local (`127.0.0.1:5432`)
- Uygulama baglantisi:
  - `config/server.ini` icinde `database_url = postgresql+psycopg2://...@127.0.0.1:5432/appcenter`
  - Uygulama venv icinde `psycopg2-binary` kurulu olmalidir.
- DB ve kullanici:
  - DB adi: `appcenter`
  - DB user: `appcenter`
  - Erisim: local-only (`pg_hba.conf` local + 127.0.0.1/32)
- Migration:
  - Kaynak legacy DB dump/backup'lari: `/var/lib/appcenter/backups/`
  - Tasima sonrasi tablo satir sayilari kaynak->PostgreSQL dogrulanmistir.
- Not:
  - Sunucu PostgreSQL-only calisir.
  - `config/server.ini` icinde PostgreSQL disi `database_url` ile uygulama baslatilmaz.

### 1.9 PostgreSQL Performans/Bakim Ayarlari (2026-03-02)

- Sunucu profili:
  - CPU: 16 vCPU
  - RAM: 15 GB
- Uygulanan temel ayarlar (`ALTER SYSTEM`):
  - `shared_buffers=2GB`
  - `effective_cache_size=8GB`
  - `work_mem=16MB`
  - `maintenance_work_mem=512MB`

### 1.10 UI CSS Koruma Kurali (2026-03-10)

- `app/static/css/app.css` legacy/non-Tabler katmandir.
- `app-shell` altinda acilan sayfalarda global legacy selector sizmasi yasandigi icin su kural zorunludur:
  - `card`, `btn`, `input`, `select`, `textarea`, `label`, `table`, `th`, `td` gibi genel kurallar
    yalnizca `body:not(.app-shell)` scope'u ile yazilir.
- Tabler sayfa duzenleri icin:
  - ortak override -> `app/static/css/app-overrides.css`
  - sayfa ozel duzeltme -> template icinde scope'lu selector
- Belirti:
  - radio/checkbox yatayda uzar
  - `form-select` / `form-control` Tabler gorunumunden cikar
  - kart padding/border/radius degerleri beklenmedik olur
  - `wal_compression=on`
  - `max_wal_size=4GB`
  - `min_wal_size=1GB`
  - `checkpoint_completion_target=0.9`
  - `random_page_cost=1.1`
  - `effective_io_concurrency=200`
  - `autovacuum_naptime=20s`
  - `autovacuum_vacuum_scale_factor=0.05`
  - `autovacuum_analyze_scale_factor=0.02`
  - `autovacuum_vacuum_cost_limit=2000`
  - `log_min_duration_statement=500ms`
  - `shared_preload_libraries=pg_stat_statements`
- Bakim/isletim:
  - `CREATE EXTENSION IF NOT EXISTS pg_stat_statements`
  - Migration sonrasi `vacuumdb --analyze-in-stages` calistirildi.

### 1.9.1 PostgreSQL Gunluk Yedekleme (2026-03-25)

- Gunluk backup script:
  - repo: `server/scripts/postgres-backup-daily.sh`
  - canli: `/opt/appcenter/server/scripts/postgres-backup-daily.sh`
- Calisma modeli:
  - `pg_dump -Fc`
  - UTC timestamp ile dosya uretir
  - `pg_restore --list` ile dump okunabilirligini kontrol eder
  - `sha256` sidecar dosyasi olusturur
  - 30 gunden eski dump ve checksum dosyalarini siler
- Cron:
  - `/etc/cron.d/appcenter-postgres-backup`
  - varsayilan saat: her gun `02:15 UTC`
- Hedef dizin:
  - canli DB `appcenter`:
    - `/backup/appcenter-postgresql/appcenter/`
  - test DB `appcenter_test`:
    - `/backup/appcenter-postgresql/appcenter_test/`
- Kolay erisim:
  - her DB klasorunde `latest.dump` ve `latest.dump.sha256` symlink'leri guncel dosyayi gosterir
- Geri donus penceresi:
  - 30 gun
- Elle calistirma:

```bash
sudo /opt/appcenter/server/scripts/postgres-backup-daily.sh
```

- Geri yukleme ornegi:

```bash
PGPASSWORD='***' pg_restore -h 127.0.0.1 -U appcenter -d appcenter -c /backup/appcenter-postgresql/appcenter/latest.dump
```

### 1.11 LDAP / Active Directory Isletim Notu (2026-03-24)

- LDAP/AD entegrasyon modeli iki katmanlidir:
  - bootstrap/secret alanlari: `config/server.ini`
  - runtime davranis ve role mapping: DB `settings` + `/settings`
- `config/server.ini` icindeki LDAP alanlari:
  - `ldap_server_uri`
  - `ldap_use_ssl`
  - `ldap_start_tls`
  - `ldap_bind_dn`
  - `ldap_bind_password`
  - `ldap_user_base_dn`
  - `ldap_user_filter`
  - `ldap_group_base_dn`
  - `ldap_group_filter`
  - `ldap_ca_cert_file`
  - `ldap_timeout_sec`
- `/settings` uzerinden yonetilen LDAP runtime key'leri:
  - `auth_ldap_enabled`
  - `auth_ldap_allow_local_fallback`
  - `auth_ldap_jit_create_users`
  - `auth_ldap_directory_type`
  - `auth_ldap_default_role_profile_key`
  - `auth_ldap_group_admin`
  - `auth_ldap_group_operator`
  - `auth_ldap_group_viewer`
- Operasyon kurali:
  - bind password ve benzeri secret alanlar DB'ye tasinmaz
  - lokal break-glass admin her zaman korunur
  - LDAP acildiginda once local admin fallback ile smoke alinmadan rollout tamamlanmis sayilmaz
  - `config/server.ini` altindaki LDAP bootstrap alanlari degisirse `appcenter` servisi restart edilir
  - repo paylasimi icin `config/server.ini.example` kullanilir; gercek secret degerler commit edilmez
- Canli smoke minimumu:
  - `GET /health` -> `200`
  - lokal admin login -> `200`
  - LDAP/AD test kullanicisi login -> `200`
  - `GET /api/v1/auth/me` icinde `auth_source=ldap`
- AD/OpenLDAP notu:
  - `auth_ldap_directory_type=ad` iken arama attribute seti AD'ye gore secilir
  - `auth_ldap_directory_type=openldap` iken OpenLDAP uyumlu attribute seti kullanilir
- UPN login ihtiyaci varsa:
  - `ldap_user_filter` degeri acikca genisletilir
  - ornek:
    - `(&(objectClass=user)(|(sAMAccountName={username})(userPrincipalName={username})))`

### 1.12 LDAP Hata Davranisi ve Operator Notlari (2026-03-25)

- Login sonuc matrisi:
  - lokal login basarili -> `200`
  - LDAP config eksigi/hatasi -> `503`
  - LDAP auth/bind/search basarisiz -> `401`
  - beklenmeyen LDAP exception -> fiilen `401`, ayirim logdan yapilir
- Kullaniciya donen `401` mesaji bilerek geneldir:
  - `Incorrect username or password`
- Operator kontrol listesi:
  - `config/server.ini` LDAP alanlarini dogrula
  - `auth_ldap_enabled` / `auth_ldap_allow_local_fallback` runtime degerlerini kontrol et
  - local admin ile girisin halen acik oldugunu dogrula
  - server logunda LDAP configuration/bind hatalarini incele
- Guncel audit garantisi:
  - `auth.login.local`
  - `auth.login.ldap`
- Henuz standartlastirilmasi acik alanlar:
  - `auth.login.ldap_failed`
  - `user.sync_from_ldap`

### 1.13 LDAP Rollout ve Secret Hijyeni (2026-03-25)

- Onerilen rollout sirasi:
  1. `config/server.ini` bootstrap alanlarini hazirla
  2. `systemctl restart appcenter`
  3. `GET /health`
  4. local break-glass admin login
  5. `/settings` uzerinden LDAP runtime ayarlarini dogrula
  6. LDAP test kullanicisi login
  7. `GET /api/v1/auth/me` icinde `auth_source=ldap` kontrolu
- Secret hijyeni:
  - repo referansi olarak `config/server.ini.example` kullan
  - gercek bind password degerlerini ticket/chat/dokuman icine kopyalama
  - sizinti supesinde LDAP servis hesabi sifresini rotate et

### 1.10 PostgreSQL Uyumluluk Notu (Timeline)

- `GET /api/v1/dashboard/timeline` endpoint'i PostgreSQL'e geciste iki SQL uyumluluk guncellemesi aldi:
  - `FROM ( ... )` alt sorgusuna alias eklendi.
  - `UNION` icindeki `exit_code` kolonunda tip uyumu icin `CAST(NULL AS INTEGER)` kullanildi.
- Beklenen sonuc:
  - Endpoint `200` doner, dashboard timeline karti bos/500'e dusmez.

### 1.11 Ust Navigasyon Notu (2026-03-03)

- Ust bardaki `Altyapi` ana menusu kaldirildi.
- `Altyapi` altindaki tum linkler `Yonetim` dropdown'i altina tasindi.
- Beklenen davranis:
  - Topbar'da ayri bir `Altyapi` menusu gorunmez.
  - `Yonetim` acildiginda altyapi linkleri buradan erisilebilir.
  - Role/feature-flag filtreleme kurallari degismeden calismaya devam eder.

### 1.12 Uzak Destek Liste Sayfasi (2026-03-03)

- Ust menuye `Destek Merkezi` ana linki eklendi: `/remote-support`.
- Sayfa title/page header metni `Destek Merkezi` olarak guncellendi.
- Ilk surumde sayfa icerigi `Ajanlar` sayfasinin bire bir kopyasidir:
  - `app/templates/remote_support/list.html` <- `app/templates/agents/list.html`
- Uzak destek listesinde istenen sadeleştirme uygulandi:
  - `Helper` ve `Version` kolonlari kaldirildi.
  - Satir aksiyonlarindan `Detay` butonu kaldirildi.
  - Satir aksiyonu `Baglan`:
    - Ikon `ti-device-laptop` olarak guncellendi.
    - Tabler `Buttons with icon` animasyon siniflari (`btn-animate-icon`, `btn-animate-icon-shake`) kullanilir.
- Uzak destek listesine `Son` kolonu eklendi:
  - Veri kaynagi: `/api/v1/agents` icinde `last_remote_connected_at` alanidir.
  - UI gosterimi: goreli sure (`1dk once`, `1 gun once` vb.).
  - Siralama secenegi: `Son baglanti` (en yeni baglanti ustte, varsayilan secim).
  - Renk/stil: `Light badge` Azure (`badge bg-azure-lt text-azure`).
- Tema uyumlulugu:
  - `app/static/css/app.css` icindeki global `.badge` kurali sadece `app-shell` disina alindi.
  - Tabler tabanli tum sayfalarda badge radius/padding temadaki varsayilan ile uyumludur.
- Session detay sayfasi (`/remote-support/sessions/{id}`) acikken aktif menu anahtari `remote_support` olur.

### 1.13 Ajan Detay Kart Gorsel Guncellemesi (2026-03-03)

- `Ajan Detay` ekraninda `Kimlik ve Erisim` karti Tabler `Card with top ribbon` yapisina alindi.
- Ust ribbon:
  - Renk: `bg-azure`
  - Ikon: `ti ti-shield-lock`
- Kart icerigi (`UUID`, `IP`, `Versiyon`, `Login kullanici`, remote alanlari) degistirilmedi; sadece gorsel sunum guncellendi.

### 1.14 Dinamik Grup Kurallari (2026-03-03)

- Gruplar ekraninda `Dinamik (Otomatik grup)` secenegi eklendi.
- Kural alanlari:
  - `Hostname Kosullari` (wildcard destekli)
  - `IP Kosullari` (wildcard destekli, or: `10.10.*`)
- `Kosulu Kontrol Et` aksiyonu:
  - Eslesen toplam ajan sayisini gosterir.
  - Ilk 5 ajan ornek olarak listelenir.
- UI:
  - Grup create/edit modal genisletildi.
  - Dinamik kural alanlarinda `Hostname Kosullari` ve `IP Kosullari` yan yana gosterilir.
  - Uygulamadaki global `.row` stil ezmesine karsi bu alanlar `CSS grid` ile sabitlendi (her zaman yan yana).
- Dinamik grup davranisi:
  - Ajan uyelikleri scheduler tarafinda otomatik guncellenir.
  - Manuel grup atama akisi dinamik gruplar icin kapatilir.
- Genel ayar:
  - `dynamic_group_sync_interval_sec` (min `30`, varsayilan `120`)
  - Ayarlar ekraninda yonetilebilir.

### 1.15 Rol Profilleri (2026-03-03)

- `/roles` ekrani ile rol profili yonetimi aktif (`roles.manage` izni).
- Sistem rol profilleri:
  - `viewer`
  - `operator`
  - `admin`
- Ozel rol profilleri olusturulabilir:
  - Her profil dogrudan `permissions` listesi ile tanimlanir.
  - Yetki enforcement endpoint bazinda `require_permission(...)` ile calisir.
  - UI yetkileri API yetkilerinden ayridir:
    - `ui.menu.*`: menu gorunurlugu
    - `ui.page.*`: sayfa route erisimi
  - `support_center_only` preset'i:
    - `Destek Merkezi`
    - `Session Recordings`
    - remote support session/recording view-manage akislarini kapsar
    - API izinleri: `*.view/manage`
  - Varsayilan ozel preset: `support_center_only` (yalnizca Destek Merkezi akislari).
- Kullanici yonetimi:
  - `/users` ekraninda kullanici olustur/duzenle akisi `Rol Profili` secimi ile calisir.
  - Rol profili listesi `roles.manage` veya `users.manage` izniyle okunabilir.
  - Rol profili kullanimda ise pasife alma/silme backend tarafinda engellenir.

### 1.16 Gruplar Ekrani Durum/Silme Akisi (2026-03-03)

- Gruplar listesinde aktif/pasif yonetimi satir ici checkbox switch ile yapilir.
  - Durum degisikligi modal onayi ile uygulanir (`Onayla` / `Vazgec`).
- Varsayilan filtre secimi `Tum Gruplar` oldugu icin pasif gruplar da ilk acilista listelenir.
- Grup duzenleme modalina sol tarafta `Sil` aksiyonu eklendi.
  - Bu aksiyon kalici silme yapar: `DELETE /api/v1/groups/{group_id}/hard`
  - Sistem gruplari silinemez.
  - Gruba bagli deployment varsa backend `400` doner; once deployment hedefleri temizlenmelidir.
- Grup tablosu `Ajan Sayisi` kolonunda iki adet Tabler `Basic badge` kullanir:
  - Toplam ajan: `bg-blue text-blue-fg`
  - Pasif ajan: `bg-red text-red-fg`

### 1.1 Bu Sunucuda Aktif Deployment Profili

- Kaynak repo dizini: `/root/appcenter/server`
- Calisan uygulama dizini: `/opt/appcenter/server`
- Virtual env: `/opt/appcenter/server/venv`
- Bootstrap config: `/opt/appcenter/server/config/server.ini`
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
- `config/server.ini` deploy edilen dosyanin bir parcasidir; hedefte guncel kalmali.
- `venv` kopyalama/overwrite, `uvicorn` shebang'lerini bozup systemd `203/EXEC` hatasi uretebilir. Bu nedenle `venv` dizinlerini deploy kapsamindan cikarin.

### 2.2 Bu Sunucuda Kullanilan Rsync Deploy Akisi

Tercih edilen yol:

```bash
cd /root/appcenter/server
./scripts/deploy-live.sh
```

Manuel alternatif:

```bash
rsync -av --delete \
  --exclude '.git' \
  --exclude 'venv' \
  --exclude 'venv39' \
  /root/appcenter/server/ /opt/appcenter/server/

sudo systemctl restart appcenter
sudo systemctl is-active appcenter
```

### 2.3 Config Kritik Notlari

- `config/server.ini` icindeki `cors_origins` JSON list formatinda olmali:
  - dogru: `cors_origins=["*"]`
  - yanlis: `cors_origins=*`
- noVNC calisma modu DB `settings` tablosundan yonetilir:
  - `remote_support_novnc_mode=embedded` -> noVNC iframe yerine session sayfasinda dogrudan RFB (embed)
  - `remote_support_novnc_mode=iframe` -> legacy iframe akisi
- WS bridge modu DB `settings` tablosundan yonetilir:
  - `remote_support_ws_mode=internal` -> `/novnc-ws` FastAPI icinde calisir
  - `remote_support_ws_mode=external` -> harici websockify akisi
- `remote_support_enabled`, timeout ve max duration gibi davranis ayarlari `/settings` ekranindan degistirilir.

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
  - `Destek Merkezi > Ajan Bilgilendirme` ayarlari:
    - `Baglanti Ekraninda kirmizi cerceve ekle`
    - `Baglanan kisi ismini ekranda goster`
  - remote support helper davranisi:
    - ayar 1 acikken Windows agent helper komut satirinda `-connectionoverlay`
    - ayar 2 acikken Windows agent helper komut satirinda `-user <AppCenter username>`
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

## 4.2 Inventory 500 (PostgreSQL) Sorun Giderme

Belirti:

- `Yazilim Envanteri` acilirken `Internal Server Error`.
- Log: `psycopg2.errors.UndefinedFunction: function group_concat(...) does not exist`.

Kok neden:

- PostgreSQL fonksiyonu `group_concat` PostgreSQL'de bulunmaz.

Cozum:

- `app/services/inventory_service.py` yazilim ozetinde PostgreSQL `string_agg(distinct ...)` kullanir.

Hizli kontrol:

```bash
cd /opt/appcenter/server
/opt/appcenter/server/venv/bin/python - <<'PY'
from app.database import SessionLocal
from app.services.inventory_service import get_software_summary
s = SessionLocal()
try:
    items, total = get_software_summary(s, search='', page=1, per_page=5)
    print('ok', total, len(items))
finally:
    s.close()
PY
```

DB saglik kontrolu:

```bash
PGPASSWORD='***' psql -h 127.0.0.1 -U appcenter -d appcenter -c "SELECT 1;"
```

### 1.11 PostgreSQL-Only Dogrulama (2026-03-04)

- API regression (izole test DB):
  - `appcenter_test` PostgreSQL veritabani olusturulup testler bu DB'de kosuldu.
  - Komut:
    - `config/server.ini` icindeki `database_url` gecici olarak `appcenter_test` DB'sine point edecek sekilde degistirilip `python -m pytest -q tests --ignore=tests/test_signal_db_status.py` kosuldu.
  - Sonuc: `46 passed`.
  - Not: `tests/test_signal_db_status.py` eski signal helper fonksiyon adlarini import ettigi icin collect asamasinda ayri takip edilmelidir.
- Canli smoke API kontrolleri:
  - `/health`, `/api/v1/dashboard/stats`, `/api/v1/settings`, `/api/v1/groups`, `/api/v1/agents`, `/api/v1/inventory/dashboard`, `/api/v1/remote-support/sessions`, `/api/v1/audit/logs`, `/api/v1/agents/{uuid}/timeline` endpointleri `200` dondu.
- PostgreSQL dosya isimleri devre-disi:
  - Eski yerel veritabani artefaktlari kaldirildi; canli sistem yalnizca PostgreSQL kullanir.
  - Bu adim sonrasi servis restart + health kontrolu basarili.

## 4.3 Agent Status Flapping (signal_disconnect) Sorun Giderme

Belirti:

- Agent detayda status cok kisa aralikla `online/offline` degisir.
- `agent_status_history` kayitlarinda `reason=signal_disconnect` ile heartbeat kayitlari birbirine cok yakin gorulur (1-10 sn).

Kok neden:

- `/api/v1/agent/signal` long-poll timeout dongusu status degisimi uretiyordu.

Cozum (2026-03-04):

- `app/api/v1/agent.py` icinde signal endpointten status guncelleyen path kaldirildi.
- Signal endpoint sadece wake-up mekanizmasi olarak birakildi.
- Online/offline source of truth heartbeat oldu.

Hizli kontrol:

```bash
cd /opt/appcenter/server
./venv/bin/python - <<'PY'
from app.database import SessionLocal
from app.models import AgentStatusHistory
from sqlalchemy import desc
uid='54d2ad5c-5b66-477d-82da-e5a22ef6dc01'  # ornek
s=SessionLocal()
try:
    for r in s.query(AgentStatusHistory).filter(AgentStatusHistory.agent_uuid==uid).order_by(desc(AgentStatusHistory.id)).limit(20):
        print(r.id, r.reason, r.old_status, '->', r.new_status, r.detected_at)
finally:
    s.close()
PY
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

### 5.1 Remote Support Snapshot (2026-02-20)

- Server runtime snapshot:
  - `/opt/appcenter/server/.backup_remote_support_runtime_20260220_194350`
  - Icerik: `app/models.py`, `app/schemas.py`, `app/database.py`, `app/services/heartbeat_service.py`, `app/templates/agents/detail.html`, `config/server.ini`
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

## 7. Sistem/Servis Gecmisi Ayrimi (2026-03-05)

- Ajan detayinda `Sistem Gecmisi` sekmesi yalnizca:
  - `GET /api/v1/agents/{uuid}/system/history`
  endpointini kullanir.
- Servis durum/startup degisimleri yalnizca:
  - `GET /api/v1/agents/{uuid}/services/history`
  sekmesinde gorunur.
- Canli temizlik sorgusu:
  - `agent_system_profile_history` icindeki servis metni tasiyan legacy satirlar silindi.
  - 2026-03-05 calistirmasinda silinen satir: `0`.

## 8. Remote Support Onay Politikasi (2026-03-07)

- Merkezi parametre:
  - `remote_support_approval_required` (default `true`)
- Agent override endpoint:
  - `PUT /api/v1/agents/{agent_uuid}/remote-support-approval`
  - `{"enabled": null}` -> global ayar
  - `{"enabled": true}` -> bu agentta onay zorunlu
  - `{"enabled": false}` -> bu agentta promptsiz auto-approve
- Heartbeat payload:
  - `remote_support_request.requires_approval`
  - Agentlar bu alana gore prompt acar veya direkt approve+ready akisina gecer.

Canli dogrulama:

- Linux `d85705fd-d8ee-4654-9879-d982141e558c`:
  - inherit (`enabled=null`) -> `pending_approval`
  - override false (`enabled=false`) -> `active`
- Windows `54d2ad5c-5b66-477d-82da-e5a22ef6dc01`:
  - inherit (`enabled=null`) -> `pending_approval`
  - override false (`enabled=false`) -> `active`
- Not:
  - Windows `03dff9e6-0d3a-4bc5-baec-3b3b121ea919` testinde timeout goruldu (agent tarafi signal/heartbeat gecikmesi).
