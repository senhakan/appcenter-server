# Roadmap and Theme

Bu dokuman iki amac icin tutulur:
- Projede kalinan noktayi ve sonraki asamalari netlestirmek
- UI tema kararlarini ve tasarimi nerede gorecegimizi tek yerde toplamak

## 1. Kalinan Nokta (2026-02-13)

- Faz 1-5 tamam.
- Faz 6 kapsaminda su iyilestirmeler aktif:
- Uygulama upload: `install_args`, `uninstall_args`, opsiyonel icon
- Uygulama adinda case-insensitive tekillik kontrolu
- Grup yonetimi: grup olusturma, grup duzenleme, ajan atama
- Deployment create/edit ekranlarinda app/group/agent secimleri combobox
- Full form edit ekranlari:
  - `/applications/{app_id}/edit`
  - `/deployments/{deployment_id}/edit`
  - `/groups/{group_id}/edit`
- Grup ajan atama: soldan saga dual-listbox

## 2. Sonraki Asamalar

### Faz 6.1 (Kisa Vade)
- Edit formlarinda zorunlu alan/format validasyonlarini guclendirme
- API hata mesajlarini form alanlarina daha acik yansitma
- Deployment listesinde `App ID` yerine uygulama adi gosterimi
- Deployment listesinde `Group/Agent` hedeflerinin isimle zenginlestirilmesi
- Agent detail: aktif login kullanicilarini (local/RDP session tipi ile) gosterme (heartbeat ile gonderim)

### Faz 6.2 (Orta Vade)
- Grup silme/pasife alma stratejisi
- Uygulama icon degistirme/silme UI akisi
- Liste ekranlarina arama/filtre/siralama

### Faz 6.3 (Yonetilebilirlik)
- Audit log: kim, neyi, ne zaman degistirdi
- Kritik operasyonlarda onay adimi
- Rol bazli erisim detaylandirma (admin/operator/viewer)

### Faz 6.4 (Final UI Modernizasyonu - En Son Asama)
- Tabler tabanli UI gecisi bu fazda yapilacak.
- Kural: Faz 6.1, 6.2 ve 6.3 tamamlanmadan Tabler gecisine baslanmaz.
- Kapsam:
  - `base.html`, topbar, kart, tablo, form yapilarinin Tabler uyumlu hale getirilmesi
  - dashboard + agents ekranlariyla pilot gecis
  - onay sonrasi tum ekranlara kademeli tasima

### Faz 7 (Planlandi - Beklemede): Kullanici Yonetimi ve Yetkilendirme
- Durum: Sadece planlandi, henuz implement edilmedi.
- Yaklasim: RBAC (role-based access control) + backend enforcement + UI gorunurluk kontrolu.
- Roller:
  - `admin`: tam yetki
  - `operator`: operasyonel yazma yetkileri (deploy/app/group/agent vb.), kritik sistem ayarlari ve kullanici yonetimi yok
  - `viewer`: salt-okunur
- Kapsam:
  - User management API (`/api/v1/users` CRUD + active/passive + password reset)
  - Role guard dependency (endpoint bazli `403` kontrolu)
  - UI menu/sayfa/aksiyon gorunurluk kurallari (role'a gore)
  - `/api/v1/auth/me` veya login response ile role bilgisi
  - Kendini kilitlemeyi onleyen korumalar (son admin silme/pasifleme engeli)
  - Audit log altyapisina baglanti
- Yetki matrisi (ozet):
  - Dashboard/Agents/Inventory/Licenses list: `admin`, `operator`, `viewer`
  - Uygulama/Deployment/Group yazma islemleri: `admin`, `operator`
  - Settings update + User management: sadece `admin`
  - Agent API: mevcut `X-Agent-UUID` + `X-Agent-Secret` modeli ile devam

## 3. UI Tema

Aktif tema:
- Tipografi:
  - Baslik: `Space Grotesk`
  - Govde: `IBM Plex Sans`
- Renk sistemi: acik tema, mavi aksiyon rengi, sari vurgu
- Arkaplan: radial-gradient katmanli hafif doku
- Kart tabanli layout + yumusak golge

Tema kaynaklari:
- CSS tokenlari: `app/static/css/app.css`
- Ana iskelet: `app/templates/base.html`
- Ust menu/nav: `app/templates/components/topbar.html`

## 4. Ornek Tasarimi Nerede Gorebilirim?

Calisan sunucuda su ekranlar referans alinabilir:
- Dashboard: `/dashboard`
- Uygulamalar: `/applications`
- Uygulama Duzenle: `/applications/1/edit`
- Dagitimlar: `/deployments`
- Dagitim Duzenle: `/deployments/1/edit`
- Gruplar: `/groups`
- Grup Duzenle: `/groups/1/edit`

Not:
- `1` id'li kayit yoksa URL'yi mevcut bir id ile degistirin.
