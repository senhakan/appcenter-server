# 12 - Implementation Backlog

Bu belge, Asset Registry / CMDB Lab modulunun kodlama backlog'unu tanimlar.

Amac:
- dokumanlari uygulama islerine cevirmek
- isleri dogru sira ve bagimlilikla parcala mak
- her is icin teslim beklentisini netlestirmek

## 1. Genel Uygulama Stratejisi

Uygulama fazlari:

1. Altyapi ve migration
2. Referans veriler ve temel CRUD
3. Asset ve kisi deneyimi
4. Eslestirme ve veri kalitesi
5. Raporlama
6. Menu entegrasyonu
7. Stabilizasyon

Kurallar:
- her faz deploy edilebilir parcalara bolunmeli
- mevcut sistem davranisini etkileyen degisiklik ilk fazlarda yapilmamali
- test kapsamı faz bazli artmali

## 2. Faz A - Iskelet Ve Migration

### A1. Dokuman referans kontrolu

Kapsam:
- dokumanlar arasi terminoloji tutarliligi son kez kontrol edilir
- implementasyonda referans alinacak dosyalar netlenir

Teslim:
- kodlama sirasinda referans alinacak belge listesi

Kabul:
- `08`, `09`, `10`, `11` ana referans belgeler olarak sabitlenmis olmali

### A2. Router ve template iskeleti

Kapsam:
- `asset_registry.py` eklenir
- `asset_registry/` template klasoru acilir
- placeholder UI sayfalari olusturulur

Teslim:
- bos ama calisan route agaci

Kabul:
- `/asset-registry`
- `/asset-registry/assets`
- `/asset-registry/organization`
- `/asset-registry/locations`
- `/asset-registry/people`
adresleri 200 donmeli

### A3. Migration altyapisi

Kapsam:
- yeni tablolar icin migration dosyalari olusturulur
- migration sirasi `11_MIGRATION_AND_API_PLAN.md` ile uyumlu olur

Teslim:
- migration dosyalari

Kabul:
- temiz veritabaninda tum migrationlar basarili calismali
- rollback senaryosu en az son migration icin test edilmeli

## 3. Faz B - Referans Tablolar Ve CRUD Temeli

### B1. Node type metadata tabloları

Kapsam:
- `organization_node_types`
- `location_node_types`

Teslim:
- tablo + seed

Kabul:
- varsayilan semantik kodlar DB'de olusmali

### B2. Organizasyon CRUD

Kapsam:
- service
- API
- temel liste/agac ekrani

Teslim:
- organizasyon dugumu ekleme, guncelleme, pasife alma

Kabul:
- parent-child kurallari calismali
- pasif dugum yeni baglam seciminde gelmemeli

### B3. Lokasyon CRUD

Kapsam:
- service
- API
- agac ve tablo gorunumu

Teslim:
- lokasyon dugumu ekleme, guncelleme, pasife alma

Kabul:
- lokasyon hiyerarsisi canonical modele uygun olmalı

### B4. Maliyet merkezi temel yapisi

Kapsam:
- `cost_centers` CRUD
- organizasyonla bag

Teslim:
- maliyet merkezi liste ve secici altyapisi

Kabul:
- organizasyona bagli filtreleme calismali

## 4. Faz C - Kisi Ve Asset CRUD

### C1. Kisi modulu

Kapsam:
- `person_registry_service`
- kisi listesi
- kisi detay
- kisi formu

Teslim:
- manuel kisi CRUD

Kabul:
- pasif kisi secilemez kurali calismali
- kisi detayinda bagli assetler listelenmeli

### C2. Asset tablo ve service katmani

Kapsam:
- `assets` tablosu
- `asset_registry_service`
- create/update/read mantigi

Teslim:
- asset CRUD API

Kabul:
- kanonik minimum zorunlu alanlar enforce edilmeli
- change log hook noktasi hazir olmali

### C3. Asset listesi

Kapsam:
- filtreli tablo
- pagination
- temel kolonlar

Teslim:
- asset liste ekrani

Kabul:
- organizasyon, lokasyon, kisi ve status filtreleri calismali

### C4. Asset detay

Kapsam:
- genel
- sahiplik
- teknik iliski placeholder
- veri kalitesi placeholder
- gecmis placeholder

Teslim:
- cok sekmeli detay ekrani

Kabul:
- asset baglam alanlari tek kaynaktan gosterilmeli

## 5. Faz D - Linkleme Ve Eslestirme

### D1. `asset_agent_links` tablosu ve service mantigi

Kapsam:
- link olusturma
- unlink
- aktif primary link kurali

Teslim:
- link service

Kabul:
- ayni agent icin birden fazla aktif primary link olusmamali

### D2. Eslestirme aday motoru

Kapsam:
- hostname
- serial
- login user
- lokasyon
- organizasyon ipucu

Teslim:
- candidate listesi
- confidence seviyesi

Kabul:
- confidence sinyalleri UI'da aciklanabilir olmali

### D3. Eslestirme kuyrugu ekrani

Kapsam:
- sekmeler
- candidate aksiyonlari
- manuel secme modalı

Teslim:
- operasyon ekrani

Kabul:
- onay, red, manuel bagla aksiyonlari calismali

## 6. Faz E - Veri Kalitesi Ve Audit

### E1. `asset_data_quality_issues`

Kapsam:
- issue detection kurallari
- issue create/update/resolution mantigi

Teslim:
- issue motorunun ilk versiyonu

Kabul:
- asgari issue tipleri uretilmeli:
  - owner eksik
  - primary user eksik
  - organizasyon eksik
  - lokasyon eksik
  - duplicate serial

### E2. `asset_change_log`

Kapsam:
- asset degisiklik logu
- link history logu

Teslim:
- gecmis kaydi altyapisi

Kabul:
- create ve update operasyonlari log yazmali

### E3. Veri kalitesi ekrani

Kapsam:
- kartlar
- issue listesi
- tekil duzeltme

Teslim:
- veri kalitesi operasyon ekrani

Kabul:
- issue kartindan ilgili listeye inilebilmeli

## 7. Faz F - Raporlama

### F1. Organization report seti

Teslim:
- organizasyon bazli cihaz dagilimi
- organizasyon bazli sahiplik dagilimi

Kabul:
- org tree filtreleri descendant-inclusive calismali

### F2. Location report seti

Teslim:
- kampus / bina / kat kirilimli cihaz dagilimi
- lokasyonsuz cihaz listesi

Kabul:
- lokasyon path turetimi dogru olmali

### F3. Ownership ve quality report seti

Teslim:
- owner'siz cihaz
- primary user eksik cihaz
- eslesme kalitesi raporu

Kabul:
- alan otoritesi belgesine uygun hesaplama yapilmali

### F4. Export altyapisi

Teslim:
- CSV export
- buyuk exportlarda async hazirligi

Kabul:
- ekrandaki filtre ile export ayni sonucu vermeli

## 8. Faz G - UI Entegrasyonu

### G1. Ana menu entegrasyonu

Teslim:
- `Asset Management` ana menu girisi
- `Hardware > Asset Registry`
- `Software > Envanter / SAM` ekranlari

Kabul:
- mevcut menuler etkilenmemeli

### G2. Tasarim dili

Kapsam:
- Tabler ile uyumlu ama page-scoped stiller
- mevcut global CSS kirilmamali
- `Asset Management` dropdown'u grup basliklari ve daha rafine spacing ile ayristirilmali

Kabul:
- yeni sayfalar mevcut tema elemani gibi gorunmeli

### G3. Ayarlar editoru

Kapsam:
- node label editoru
- sozluklerin ayrik kaydetme aksiyonlari

Teslim:
- `Asset Registry > Ayarlar` ekraninda gercek duzenleme akisi

Kabul:
- organization node labels ve location node labels UI'dan degistirilebilmeli
- semantik kodlar korunmali

### G4. Agent detay baglam karti

Kapsam:
- mevcut ajan detay sayfasinda read-only asset baglami

Teslim:
- aktif primary link varsa `Asset Registry Baglami` karti

Kabul:
- ajan detay sayfasi asset modulu kapali mantigini bozmamali
- bagli asset yoksa kart hic gosterilmemeli

### G5. Liste toolbar olgunlastirma

Kapsam:
- asset listesi filtre toolbar'i
- kisi listesi filtre toolbar'i
- lokasyon listesi filtre toolbar'i

Teslim:
- istemci tarafinda hizli daraltma ve sayisal liste ozeti

Kabul:
- mevcut CRUD akislari bozulmadan ayni sayfada filtreleme yapilabilmeli

### G6. Matching hizli asset olusturma

Kapsam:
- `agent_without_asset` adayi icin yeni asset formu
- form sonrasinda otomatik linkleme

Teslim:
- `Yeni Asset` aksiyonu ile tek akista asset olustur ve bagla

Kabul:
- ayni ajan icin link isleminden sonra aday kuyruktan dusmeli

### G7. Overview trend deck

Kapsam:
- son 7 gun asset / eslesme / issue hareketi
- action required watchlist
- organizasyon ve lokasyon bazli risk yogunlugu

Teslim:
- overview ekraninda operasyon ritmini gosteren mini zaman serileri

Kabul:
- ek API cagrisi olmadan overview payload'i icinde trend verileri gelmeli

### G8. Ortak JS yardimci katmani

Kapsam:
- HTML escape
- option doldurma
- sayisal null donusumu
- form value doldurma

Teslim:
- `static/js/asset-registry.js`

Kabul:
- asset detail ve person detail icindeki tekrar eden yardimci fonksiyonlar bu dosyaya tasinmis olmali

### G9. Asset detail teknik ozet genisletme

Kapsam:
- cost center duzenleme
- teknik baglanti metrikleri

Teslim:
- asset detail ekraninda cost center secilebilir olmali
- teknik baglanti paneli agent IP, last seen, match source, confidence ve linked time gostermeli

Kabul:
- detail ekrani listeye donmeden baglam ve teknik iliskiyi birlikte yonetebilir olmali

### G10. Uygulama ici yardim merkezi

Kapsam:
- son kullanici odakli wiki/yardim ekrani
- subnav ve overview uzerinden erisim

Teslim:
- `asset-registry/help` sayfasi

Kabul:
- kullanici dokuman aramadan uygulama icinden modul akisini gorebilmeli
- kullanici farkli ekrana gitmeden eslestirmeyi tamamlayabilmeli

### G7. Matching confidence zenginlestirme

Kapsam:
- confidence sinyallerine inventory number ve owner person eslesmesi eklemek
- neden listesini daha acik hale getirmek

Teslim:
- daha savunulabilir aday confidence modeli

Kabul:
- UI'da gorunen nedenler confidence ile uyumlu olmali

### G8. Asset detay link operasyonlari

Kapsam:
- asset detay ekranindan aktif agent linkini kesme
- baglama ve ayirma aksiyonlarini ayni panelde toplama

Teslim:
- detay ekraninda bagli agent uzerinden unlink akisi

Kabul:
- unlink sonrasi asset detay durumu hemen guncellenmeli

### G9. Organizasyon ve lokasyon operasyon aksiyonlari

Kapsam:
- organizasyon ekraninda duzenle ve pasife al aksiyonlari
- lokasyon ekraninda duzenle ve pasife al aksiyonlari

Teslim:
- liste satirlarindan operasyonel duzenleme akisi

Kabul:
- yeni ekran acmadan hizli duzenleme yapilabilmeli

### G10. Veri kalitesi operasyon toolbar'i

Kapsam:
- issue arama
- severity filtresi
- secili asset KPI gostergeleri
- recompute-only aksiyonu

Teslim:
- veri kalitesi ekraninda daha operasyonel toplu islem deneyimi

Kabul:
- secili asset yoksa toplu islem engellenmeli

### G11. Cost center operasyon akisi

Kapsam:
- cost center duzenleme
- cost center pasife alma

Teslim:
- organizasyon ekraninda cost center satir aksiyonlari

Kabul:
- yeni modal gerektirmeden duzenleme yapilabilmeli

### G12. Kisi detay duzenleme

Kapsam:
- kisi detay ekraninda edit formu
- aktif/pasif guncelleme

Teslim:
- kisi detay uzerinden kayit guncelleme

Kabul:
- detay ve form ayni ekranda tutarli guncellenmeli

## 9. Faz H - Stabilizasyon

### H1. Permission kontrolleri

Teslim:
- tum yeni ekran ve API'lerde izin kontrolu

### H2. Testler

Teslim:
- unit test
- integration test
- UI smoke test

### H3. Pilot veri ile dogrulama

Teslim:
- ornek organization/lokasyon yapisi
- ornek asset ve kisi verisi

Kabul:
- temel pilot senaryolari demonstrable olmali

## 10. Bagimlilik Zinciri

Bagimlilik sirasi:
- A2, A3 -> B1
- B1 -> B2, B3
- B2, B3 -> B4
- B2, B3, B4 -> C1, C2
- C2 -> C3, C4
- C2 -> D1
- D1 -> D2, D3
- C2, D1 -> E1, E2
- E1, E2 -> E3
- C2, D1, E1 -> F1, F2, F3
- F1, F2, F3 -> F4
- A2 + temel ekranlar -> G1, G2, G3
- D1 + mevcut agent detay sayfasi -> G4
- tum fazlar -> H1, H2, H3

## 11. Minimum Viable Lab Kapsami

Kodlamaya baslarken minimum hedef:
- organizasyon CRUD
- lokasyon CRUD
- kisi CRUD
- asset CRUD
- manuel asset-agent link
- temel veri kalite issue'lari
- 2 temel rapor
- menu entegrasyonu

Bu kapsam sonraki cekirdek entegrasyon fazindan bagimsiz calisabilir olmali.

## 12. Kodlama Baslangic Paketi

Kodlamaya baslarken ilk acilacak is paketi:

1. router iskeleti
2. template placeholder'lari
3. migration dosyalari
4. node type seed mekanizmasi
5. organizasyon CRUD ilk versiyonu

Bu paket bittiginde modul artik repo icinde gorunur ve ilerlenebilir hale gelir.
