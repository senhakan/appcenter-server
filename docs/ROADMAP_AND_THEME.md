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
