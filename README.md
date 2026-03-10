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
- Zorunlu akış: Server tarafinda yapilan her degisiklik ayni oturumda canli ortama uygulanir (`/opt/appcenter/server`), servis restart edilir ve en az health/smoke kontrolu yapilir.
- Operasyonel kisayol: Kullanici `+1` yazdiginda bu repoda o ana kadarki degisiklikler icin `dokuman guncelle + commit + push + canli deploy + health/smoke` akisi uygulanir.

## Asset Registry Lab Izolasyon Kurali

- `server/docs/ASSET_REGISTRY_LAB/` altindaki dokuman seti ve ileride bu mod icin acilacak kod yolları varsayilan olarak diger server islerinin kapsaminda **degildir**.
- Bu alan sadece kullanici acikca `asset management`, `asset registry`, `cmdb`, `asset registry lab` veya ayni anlama gelen bir is istediginde isleme alinir.
- Bu is disindaki normal server gorevlerinde su yollar varsayilan olarak kapsam disi kabul edilir:
  - `server/docs/ASSET_REGISTRY_LAB/`
  - `server/app/api/v1/asset_registry.py`
  - `server/app/services/asset_registry_service.py`
  - `server/app/services/organization_service.py`
  - `server/app/services/location_service.py`
  - `server/app/services/person_registry_service.py`
  - `server/app/services/asset_matching_service.py`
  - `server/app/services/asset_reporting_service.py`
  - `server/app/templates/asset_registry/`
- Kural:
  - baska bir is yapilirken bu klasor ve kod yollarinda degisiklik yapilmaz
  - bu alanin test, refactor, tasarim veya kodlama isleri sadece ilgili asset management isi acildiginda ele alinir

## Konfig Modeli

- Bootstrap config dosyasi:
  - repo: `server/config/server.ini`
  - canli: `/opt/appcenter/server/config/server.ini`
- Bu dosyada sadece process baslangicinda gerekli altyapi ayarlari tutulur:
  - `database_url`
  - `secret_key`
  - `upload_dir`
  - `server_host` / `server_port`
  - `log_file`
  - `novnc_token_file`
- Runtime davranis ayarlari artik DB `settings` tablosunda tutulur ve `/settings` ekranindan yonetilir:
  - `remote_support_enabled`
  - `remote_support_approval_timeout_sec`
  - `remote_support_default_max_duration_min`
  - `remote_support_max_duration_min`
  - `remote_support_novnc_mode`
  - `remote_support_ws_mode`
- Kural:
  - davranis/config degisimi icin `.env` kullanilmaz
  - remote support runtime ayarlari servis restart gerektirmez

## CSS Kurali

- `app/static/css/app.css` legacy stil katmanidir.
- Bu dosyada `card`, `btn`, `input`, `select`, `textarea`, `label`, `table` gibi genel selector'ler
  sadece `body:not(.app-shell)` altinda tanimlanir.
- Tabler kullanan tum yeni sayfalar `app-shell` altinda calisir; bu sayfalara global legacy selector
  sizmamasi gerekir.
- Yeni UI gelistirirken:
  - Tabler class'larini kullan
  - gerekiyorsa sayfa-ozel scope (`.some-page ...`) ekle
  - `app.css` icine scope'suz genel form/button/table kurali ekleme

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
- PostgreSQL startup migration:
- eski veritabani icin `applications` tablosuna eksik kolonlari idempotent ekleme
- Agent detail: login session gosterimi:
  - Agent heartbeat payload'inda `logged_in_sessions` alani (local/RDP) ile gelir
  - Server agents tablosuna JSON olarak persist eder ve agent detail ekraninda gosterir
- Agent system profile + history:
  - Agent periyodik `system_profile` snapshot gonderir (OS/donanim/virtualization/disk)
  - Server snapshot'u saklar ve degisimleri `agent_system_profile_history` tablosunda izler
  - Agent detail ekraninda sistem bilgileri "Ajan Detay" alaninda gorunur
  - "Sistem Gecmisi" sekmesi yalnizca degisen alanlari listeler (eski → yeni diff)
  - Ayni "Sistem Gecmisi" tabinda hostname/IP degisimleri de gorunur (`agent_identity_history`)
  - Birlesik zaman cizelgesi endpoint'i: `GET /api/v1/agents/{agent_uuid}/timeline`
  - Status gecmisi: `agent_status_history` (offline/online gecisleri). Timeline'a dahildir.
- Ust navigasyon sadeleştirmesi:
  - `Altyapi` ana menusu ust bardan kaldirildi.
  - Altyapi altindaki kalemler `Yonetim` dropdown'i altina tasindi.
  - Uzak destek menu girisi:
    - Ust menuye `Destek Merkezi` linki eklendi (`/remote-support`).
    - Sayfa basligi `Destek Merkezi` olarak guncellendi.
    - `Uzak Destek` liste sayfasi ilk adimda `Ajanlar` sayfasinin bire bir kopyasi olarak olusturuldu:
      - `app/templates/remote_support/list.html`
  - `Uzak Destek` liste tablosu sadeleştirildi:
    - `Helper` ve `Version` sutunlari kaldirildi.
    - Satirdaki `Detay` butonu kaldirildi.
    - `Baglan` buton ikonu `ti-device-laptop` olarak guncellendi.
    - Buton stili Tabler `Buttons with icon` desenine yaklastirildi (`btn-animate-icon`, shake).
  - `Uzak Destek` listesine `Son` alani eklendi:
    - Her ajan icin en son remote baglanti suresi goreli formatta gosterilir (`1dk once`, `1 gun once`).
    - Siralama alanina `Son baglanti` secenegi eklendi ve varsayilan yapildi.
    - Gosterim stili `Light badge` (Azure): `badge bg-azure-lt text-azure`.
  - Global badge uyumu:
    - Legacy `app.css` icindeki global `.badge` ezmesi `app-shell` disina scope'landi.
    - Boylece Tabler tema sayfalarinda badge koseleri/olculeri tema ile bire bir uyumlu kalir.
  - noVNC session sayfasi acikken aktif menu `Destek Merkezi` olarak isaretlenir.
  - Dinamik grup altyapisi:
    - Grup olustur/duzenle ekranina `Dinamik (Otomatik grup)` secenegi eklendi.
    - Kurallar: `hostname` ve `ip` wildcard desenleri (`*`) ile tanimlanir.
    - `Kosulu Kontrol Et` ile eslesen ajan sayisi + ilk 5 ornek listelenir.
    - Dinamik gruplarda manuel ajan atama backend/UI seviyesinde kapatilir.
    - Yeni/Duzenle grup modal genisligi artirildi; dinamik `Hostname` ve `IP` kosul alanlari yan yana kullanilir.
    - Global `.row` ezmesi etkisine karsi dinamik kural alani Bootstrap kolondan bagimsiz CSS grid ile yan yana sabitlendi.
    - Dinamik uyelikler scheduler job ile otomatik guncellenir.
      - Ayar anahtari: `dynamic_group_sync_interval_sec` (min `30`, varsayilan `120`)
    - Gruplar listesinde aktif/pasif yonetimi satir ici switch ile yapilir.
      - Durum degisimi modal onayi ile ilerler (`Onayla`/`Vazgec`).
    - Gruplar ekrani varsayilan filtre secimi `Tum Gruplar` olarak guncellendi (pasif gruplar ilk acilista gorunur).
    - Grup duzenleme modalinda sol tarafta `Sil` aksiyonu eklendi.
      - Gercek silme endpoint'i: `DELETE /api/v1/groups/{group_id}/hard`
      - Sistem gruplari silinemez.
      - Gruba bagli deployment varsa silme engellenir.
    - Grup tablosu `Ajan Sayisi` kolonunda iki basic badge gosterir:
      - Toplam ajan: `badge bg-blue text-blue-fg`
      - Pasif ajan: `badge bg-red text-red-fg`
  - Ajan detay ekrani:
    - `Kimlik ve Erisim` karti Tabler `Card with top ribbon` desenine alindi.
    - Ribbon rengi `Azure`, ikon `ti ti-shield-lock` olarak guncellendi.

## Faz 7 (RBAC + Kullanici Yonetimi)

- Roller:
  - `admin`
  - `operator`
  - `viewer`
- Backend RBAC:
  - Yetkilendirme permission-bazli calisir (`require_permission(...)`).
  - Rol profilleri icindeki `permissions` listesi endpoint bazli `403` enforcement uygular.
  - Izin modeli 3 katmandir:
    - `ui.menu.*`: ust/yan menu gorunurlugu
    - `ui.page.*`: sayfa route erisimi
    - `*.view/manage`: API islem yetkileri
  - Varsayilan sistem profilleri:
    - `viewer`: okuma odakli izinler
    - `operator`: operasyon + degisiklik izinleri
    - `admin`: `*` (tam yetki)
- Auth endpointleri:
  - `GET /api/v1/auth/me`
- Kullanici yonetimi:
  - `GET /api/v1/users`
  - `POST /api/v1/users`
  - `PUT /api/v1/users/{user_id}`
  - `DELETE /api/v1/users/{user_id}`
  - Son aktif admin'in silinmesi/pasiflestirilmesi engellenir.
- Web UI:
  - `GET /users` sayfasi aktif
  - `GET /roles` sayfasi aktif
  - `GET /audit` sayfasi aktif
  - `GET /profile` sayfasi aktif (kullanici kendi profilini yonetir)
  - Menu ve aksiyon butonlari permission'a gore gizlenir.
  - Route guard merkezi standart:
    - Server route context `page_permissions` verir.
    - Frontend sadece `AppCenterApi.protectPage();` cagirir.
    - `base.html` uzerinden otomatik permission kontrolu uygulanir.
  - Rol profilleri:
    - Sistem rolleri: `viewer`, `operator`, `admin`
    - Varsayilan ozel profil: `support_center_only` (Destek Merkezi odakli erisim)
    - Ozel rol profili ekleme/duzenleme/pasife alma akisi aktif
    - Her rol profili dogrudan `permissions` listesi ile tanimlanir
    - Kullanici olustur/duzenle ekraninda rol secimi `Rol Profili` uzerinden yapilir
    - Izin secimi `/roles` ekraninda katalog bazli checkbox'lar ile yapilir (`GET /api/v1/roles/catalog`).
  - Profil self-service:
    - `PUT /api/v1/auth/profile` ile kullanici kendi profil bilgisini gunceller:
      - `full_name`, `email`, `phone`, `phone_ext`, `organization`, `department`
    - `PUT /api/v1/auth/password` ile sifre degistirme
    - `PUT /api/v1/auth/avatar` ve `DELETE /api/v1/auth/avatar` ile profil fotografi yonetimi
    - Topbar kullanici karti `auth/me` verisi ile ad/rol/avatar bilgisini dinamik gosterir

## Dashboard Timeline

- Dashboard sag tarafinda "Timeline (Son 10)" karti vardir.
- Bu alan history kaynaklarini birlestirir:
  - agent status gecisleri
  - hostname/IP degisimleri
  - sistem profili degisimleri
- API: `GET /api/v1/dashboard/timeline`
- Zaman gosterimleri UI timezone ayarina gore formatlanir:
  - Setting key: `ui_timezone` (IANA, or: `Europe/Istanbul`)

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
python3.9 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Test

```bash
./venv/bin/python -m pytest -q
```

## Agent Update Publish (Standart Komut)

Agent update paketi yayinlamak gerektiginde manuel `POST /api/v1/agent-update/upload`
yerine asagidaki script kullanilir:

```bash
cd /root/appcenter/server
APPCENTER_ADMIN_USERNAME='admin' APPCENTER_ADMIN_PASSWORD='admin123' \
./scripts/publish-agent-update.sh --version 0.1.19
```

Notlar:
- Script agent reposunda test + windows build yapar ve paketi API ile upload eder.
- Canli ortamdaki kopya: `/opt/appcenter/server/scripts/publish-agent-update.sh`
- Hazir artifact ile build atlamak icin:
  - `./scripts/publish-agent-update.sh --version 0.1.19 --no-build --file /tmp/appcenter-service.exe --username admin --password '***'`

- Test dosyalari:
- `tests/conftest.py`
- `tests/test_phase5_api.py`
- Son sonuc: `24 passed`

## Dokumantasyon

- `docs/DEVELOPMENT_WORKFLOW.md`
- `docs/OPERATIONS_RUNBOOK.md`
- `docs/DEPLOYED_SERVER_SNAPSHOT.md`
- `docs/SMOKE_CHECKLIST.md`
- `docs/TESTING_AND_CI.md`
- `docs/ROADMAP_AND_THEME.md`

## Remote Support Notu (2026-02-26)

- noVNC tumlesik (server icinde) akis birincil yol olarak kullanilir.
- Guacamole tabanli viewer akis kodu alternatif cozum olarak korunur (varsayilan pasif).
- Guacamole container'lari varsayilan olarak devre disidir (stop).
- noVNC embedded viewer + internal WS bridge aktif durumdadir.
- `/novnc-ws` artik dogrudan app (FastAPI) icinde calisir.
- Harici servisler kapatildi:
  - `appcenter-novnc-ws` (systemd) -> disabled/inactive
  - `novnc-ws-172` (docker) -> stopped
- Session ekrani guncellemeleri:
  - Baglanti kontrolleri ust toolbar icine tasindi.
  - Uygun durumda oturum acilisinda baglanti otomatik baslatilir.
  - `pending_approval` icin ozel durum/aciklama metni eklendi; onay sonrasi auto-connect tetiklenir.
  - Kullaniciya donen metinlerde `noVNC` ifadesi yerine `Canli ekran` terminolojisi kullanilir.
- Guacamole'yi hizli geri almak icin tek referans:
  - `config/guacamole/REENABLE.md`
  - `config/guacamole/docker-compose.guacamole.yml`
  - `config/guacamole/nginx.guacamole.conf.snippet`

Not:
- Tabler tabanli UI gecisi planlanmistir ve en son asama (Faz 6.4) olarak konumlandirilmistir.
- Bu asama icin geri donus referansi (git tag):
  - `remote-support-novnc-iframe-baseline-20260223`
  - Bu baseline, noVNC iframe akisinin calistigi ve Guacamole'nin alternatif/pasif tutuldugu noktadir.

## Grup/Tray Policy Notu (2026-02-24)

- `Store` grubu sistem grubudur:
  - API/UI seviyesinde silinemez.
  - Adi degistirilemez.
- Agent heartbeat `config` alanina `store_tray_enabled` bayragi eklenmistir.
  - Ajan `Store` grubundaysa `true`, degilse `false`.
- Agent service, bu bayraga gore `appcenter-tray.exe` prosesini servis seviyesinde yonetir.
  - `true`: tray prosesi kullanici oturumunda calisir durumda tutulur.
  - `false`: tray prosesi kapatilir.
- `/groups` ekraninda "Gruba Ajan Ata" kaydi sonrasi secili grup korunur (ilk gruba donmez).
