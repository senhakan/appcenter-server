# LDAP Integration Preparation

Tarih: 2026-03-24
Durum: Faz 1 tamamlandi, canli login akisi aktif kod yolunda

## 1. Mevcut Durum

- Web login akisi tamamen lokal kullanici + `password_hash` + JWT modelindedir.
- LDAP / Active Directory icin repo icinde daha once eklenmis bir servis, ayar, dependency veya UI akisi yoktu.
- Kullanici yonetimi `admin` tarafindan elle yapiliyor:
  - `POST /api/v1/users`
  - `PUT /api/v1/users/{id}`
  - `DELETE /api/v1/users/{id}`

Temel referans dosyalari:

- `app/auth.py`
- `app/api/v1/auth.py`
- `app/api/v1/users.py`
- `app/models.py`
- `app/database.py`
- `config/server.ini`

## 2. Uygulananlar

LDAP/AD entegrasyonu icin kod tabaninda su adimlar uygulandi:

1. `users` tablosu LDAP-ready hale getirildi
- `auth_source`: `local | ldap`
- `ldap_dn`: dizindeki ayirt edici kullanici DN bilgisi
- `last_directory_sync`: son dizin esitleme zamani

2. Startup migration eklendi
- Eski veritabani ayakta iken idempotent olarak yeni kolonlari ve index'leri ekler.

3. Bootstrap config yuzeyi acildi
- `config/server.ini` ve `app/config.py` icine LDAP altyapi alanlari eklendi:
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
- Not:
  - runtime davranis ayarlari artik ikinci faz beklememektedir; DB `settings` + `/settings` uzerinden aktiftir
  - bootstrap alanlari process baslangicinda okunur; degisirse servis restart gerekir
  - repo icinde paylasim icin referans dosya: `config/server.ini.example`

4. Python dependency hazirlandi
- `requirements.txt` icine `ldap3` eklendi.

5. LDAP servis katmani eklendi
- `app/services/ldap_service.py`
- OpenLDAP ve AD icin ortak servis + dizin tipi bazli attribute secimi
- service bind + user search + user bind + grup listeleme akisi
- role profile secimi:
  - once grup esleme (`auth_ldap_group_admin|operator|viewer`)
  - sonra mevcut kullanicinin mevcut role profile'i
  - en sonda `auth_ldap_default_role_profile_key`

6. Login entegrasyonu eklendi
- `/api/v1/auth/login` lokal + LDAP branch ile calisir
- `auth_ldap_enabled=true` iken LDAP/AD branch devreye girebilir
- `auth_ldap_allow_local_fallback=true` ile lokal admin fallback korunur

7. Runtime settings + UI eklendi
- `auth_ldap_enabled`
- `auth_ldap_allow_local_fallback`
- `auth_ldap_jit_create_users`
- `auth_ldap_directory_type`
- `auth_ldap_default_role_profile_key`
- `auth_ldap_group_admin`
- `auth_ldap_group_operator`
- `auth_ldap_group_viewer`
- `/settings` ekranina `LDAP / Active Directory` bolumu eklendi

8. Guvenlik icin mevcut lokal login kisitlandi
- `auth_source != local` olan kullanicilar mevcut lokal parola akisi ile authenticate edilmez.
- Bu degisiklik bugunku davranisi bozmaz; gelecekte LDAP kullanicisinin yanlislikla lokal parola ile girisini engeller.

9. LDAP kaynakli kullanicilarda parola degistirme kisitlandi
- `auth_source=ldap` olan kullanicilar icin lokal parola degistirme desteklenmez.

## 2.1 Login Hata Matrisi

LDAP acikken login endpoint'inin guncel davranisi:

1. Lokal login basariliysa:
- `200`
- `auth_source=local`

2. LDAP config eksik / hataliysa:
- `503`
- ornek: `LDAP server URI is not configured`, `LDAP bind DN is not configured`

3. LDAP bind/search/user-bind basarisizsa:
- `401`
- kullaniciya genel mesaj doner: `Incorrect username or password`

4. Beklenmeyen LDAP exception'lari:
- su an savunmaci davranisla `401` olarak sonlanir
- operator ayirimi icin server loglari incelenmelidir

Audit kayitlari:

- lokal basarili login: `auth.login.local`
- LDAP basarili login: `auth.login.ldap`
- not: `auth.login.ldap_failed` su an plan notlarinda gecse de aktif kayit olarak garanti edilmemelidir

## 3. Neden Bu Model Secildi

LDAP entegrasyonu dogrudan login endpoint'ine yamalanmadi. Once veri modeli ve config yuzeyi acildi, cunku:

- dizin kaynagi ile lokal kaynagin ayrilmasi gerekiyor
- bind sirri gibi alanlar DB yerine bootstrap config'te tutulmali
- ileride JIT provisioning veya role sync eklendiginde kullanici tablosunda kimlik kaynagi alanlari gerekli olacak

## 4. Canli Dogrulananlar

1. OpenLDAP lab
- Repo icinde lab dosyalari eklendi:
  - `config/ldap/Dockerfile`
  - `config/ldap/seed.ldif`
  - `config/ldap/README.md`
- OpenLDAP container uzerinde:
  - service bind
  - user search
  - user bind
  - AppCenter login
  dogrulandi.

2. Active Directory
- Servis hesabi ile bind basarili dogrulandi.
- Test kullanicisi lookup basarili dogrulandi.
- Test kullanicisi direct bind basarili dogrulandi.
- AppCenter icinden LDAP auth smoke basarili dogrulandi.

3. Canli login davranisi
- local admin fallback korunur
- LDAP login basariliysa:
  - `auth_source=ldap`
  - JIT user create/update
  - role profile atamasi

4. Ayar degisikliklerinin etkisi
- `config/server.ini` altindaki LDAP bootstrap alanlari:
  - servis restart gerektirir
- DB `settings` altindaki LDAP runtime alanlari:
  - restart gerektirmez
- rollout sirasinda onerilen sira:
  - once `server.ini` bootstrap alanlarini dogrula
  - sonra local break-glass admin ile login dogrula
  - sonra `/settings` uzerinden `auth_ldap_enabled=true` yap
  - LDAP test kullanicisi ile smoke al

## 5. Halen Eksik Olan / Bilincli Olarak Ertelenen Isler

Bu fazdan sonra henuz yapilmamis veya bilincli olarak ertelenmis isler:

1. Test connection UI/API
- `/settings` ekraninda bagimsiz `Test Connection` akisi yok

2. Secret ayarlari UI uzerinden yonetme
- `ldap_bind_password` ve benzeri alanlar DB/UI tarafina tasinmadi
- masked/write-only secret modeli henuz eklenmedi

3. Audit genisletmesi
- `auth.login.local` / `auth.login.ldap`
- `auth.login.ldap_failed`
- `user.sync_from_ldap`
- Guncel durum:
  - `auth.login.local` ve `auth.login.ldap` aktif
  - `auth.login.ldap_failed` ve `user.sync_from_ldap` icin ek standartlastirma halen acik is

4. UPN login varsayilan modeli
- su an giris davranisi aktif `ldap_user_filter` degerine baglidir
- UPN login ihtiyaci varsa filtre acikca genisletilmelidir

5. Grup bazli role sync policy
- su an varsayilan role profile + opsiyonel grup isim esleme modeli vardir
- daha detayli kurumsal policy ikinci fazda ele alinmali

## 6. Uygulanan Tasarim Kararlari

1. Giris adi ne olacak
- `sAMAccountName`
- `userPrincipalName`
- ikisini de kabul eden strateji
- Guncel durum:
  - varsayilan davranis aktif `ldap_user_filter` ile belirlenir
  - canli AD testinde `sAMAccountName` bazli filtre kullanildi

2. Kullanici olusturma modeli
- sadece pre-provisioned user
- ilk login'de otomatik user create
- Guncel durum:
  - JIT user create desteklenir ve test edilmistir

3. Rol esleme modeli
- tek varsayilan role profile
- LDAP grup -> role profile esleme
- Guncel durum:
  - her ikisi de desteklenir
  - grup esleme verilmezse varsayilan role profile kullanilir

4. Lokal admin fallback
- En az bir lokal `admin` kullanici her zaman korunmali.
- LDAP arizasi durumunda sisteme giris icin lokal break-glass admin zorunlu.

5. Secret yonetimi
- `ldap_bind_password` gibi alanlar DB/UI tarafina tasinmaz.
- Repo icinde example/placeholder dosya kullanimi tercih edilir:
  - `config/server.ini.example`
- Canli degerler hedef hostta tutulur ve sizinti supesinde aninda rotate edilir.
- Dokuman/ekran goruntusu/log paylasiminda:
  - bind DN maskele
  - bind password tam gizle
  - gercek user/password orneklerini kalici dokumana yazma

## 7. Uygulama Notu

Bu repo icin en guvenli ilk canli rollout modeli:

- bootstrap LDAP/AD baglanti ayarlari `config/server.ini` icinde tutulur
- runtime davranis `/settings` ekranindan yonetilir
- lokal admin login korunur
- ilk fazda sadece login auth + JIT provisioning + role mapping ele alinir
- kullanici/rol yonetimi ana olarak AppCenter tarafinda kalir

Grup bazli role sync ikinci fazda ele alinmali.
