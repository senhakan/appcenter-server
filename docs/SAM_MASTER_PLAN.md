# SAM Master Plan (Windows/Linux Ayrimli)

## 1. Hedef

Envanter modulu kurumsal Software Asset Management (SAM) akisina alinacak:

- Kesif ve normalizasyon
- Yazilim katalog yonetimi
- Lisans/uyum kontrolu
- Risk ve ihlal takibi
- Raporlama ve denetim

Windows ve Linux ayrimi dashboard, katalog ve raporlarda zorunlu gorunur olacak.

## 2. Bilgi Mimarisi

- SAM Dashboard
- Yazilim Katalogu
- Yazilim Ozeti (mevcut envanter listesi)
- Normalizasyon Kurallari
- Rapor Merkezi
- Lisanslar (ayri menu, SAM ile entegre)

## 3. Fazlar

### Faz 1 (Baslatildi)
- [x] Menu/alt menu SAM yapisi
- [x] SAM Dashboard (platform bazli KPI + top software)
- [x] Yazilim Katalogu (platform filtreli, Windows/Linux kolonlari)
- [x] Rapor Merkezi iskeleti

### Faz 2
- [x] Lisans ve entitlement verilerini SAM dashboard/katalogla birlestirme
- [x] Uyum/ihlal workflow (`new -> triaged -> accepted_risk -> remediated -> closed`)
- [x] Yasakli yazilim paneli (Uyum ve Ihlaller ekrani)

### Faz 3
- [x] Rapor export (CSV)
- [x] Zamanlanmis rapor tanimi (CRUD)
- [x] Dagitim alicilari alanlari (schedule recipients)

### Faz 4
- [x] EOL/EOS surum riski (lifecycle policy + risk overview)
- [x] Maliyet ve optimizasyon gorunumu (cost profile + aylik tahmin)
- [x] Role-based rapor erisimi

### Faz 5
- [x] Zamanlanmis raporlarin otomatik calistirilmasi (scheduler)
- [x] CSV ciktilarinin sunucuda saklanmasi (`uploads/reports/sam`)
- [x] Rapor Merkezi uzerinden olusan dosyalari listeleme/indirme

## 4. Veri ve KPI Standartlari

- Ham ve normalize yazilim adlari birlikte saklanir.
- SAM KPI’lar her zaman `Windows`, `Linux`, `Toplam` kiriliminda sunulur.
- Tekillestirme etkisi olcumu:
  - `unique_raw`
  - `unique_normalized`
  - `normalized_rows`

## 5. UI/Tema Kurallari

- Tabler bileşenleri birebir kullanilir (`card`, `badge`, `table`, `datagrid`, `form-select`, `input-icon`).
- Ozel stil minimumda tutulur; tema tokenlari tercih edilir.
- Renk semantigi:
  - `blue`: genel KPI
  - `azure`: linux
  - `green`: olumlu/artis
  - `red`: risk/azalis

## 6. Basari Kriterleri

- SAM dashboard 2 saniye altinda acilmali.
- Katalog sorgulari pagination ile stabil calismali.
- Windows/Linux kirilimlari tum ana raporlarda gorunmeli.
- Normalizasyon degisikligi lisans/uyum ekranlarinda tutarli yansimali.

## 7. Bu Sprintte Tamamlananlar

- SAM Dashboard sayfasi ve API
- Yazilim Katalogu sayfasi ve API (Windows/Linux kirilimli)
- Uyum ve Ihlaller sayfasi, senkronizasyon endpoint'i, workflow durum guncelleme
- Rapor Merkezi: CSV export endpointleri
- Zamanlanmis rapor tanimlari (CRUD)
- Risk ve Optimizasyon sayfasi
- Lifecycle policy CRUD (`/api/v1/sam/lifecycle-policies`)
- Cost profile CRUD (`/api/v1/sam/cost-profiles`)
- Risk overview API (`/api/v1/sam/risk-overview`)
- Scheduler tabanli SAM rapor uretimi ve dosya listesi API (`/api/v1/sam/reports/generated`)
