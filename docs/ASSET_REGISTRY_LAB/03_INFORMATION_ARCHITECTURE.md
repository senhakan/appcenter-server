# 03 - Information Architecture

## Menu Stratejisi

Mevcut sistemi etkilememek icin yeni alan tek basina yeni bir ana menu olarak degil, daha genis bir cati altinda acilir:

- `Asset Management`

Bu ust menunun icinde iki grup bulunur:

- `Hardware`
  - `Asset Registry`
- `Software`
  - `SAM Dashboard`
  - `Yazilim Katalogu`
  - `Yazilim Ozeti`
  - `Normalizasyon Kurallari`
  - `Uyum ve Ihlaller`
  - `Rapor Merkezi`
  - `Risk ve Optimizasyon`
  - `Lisanslar`

`Asset Registry` alt modulleri:
- `Genel Bakis`
- `Organizasyon`
- `Lokasyonlar`
- `Kisiler`
- `Assetler`
- `Eslestirme Kuyrugu`
- `Veri Kalitesi`
- `Raporlar`
- `Ayarlar`

## Menu Agaci

### 1. Genel Bakis

Amac:
- tum yeni modun ozetini vermek

Icerik:
- toplam asset
- agent ile eslesmis asset
- eslesmemis agent
- eslesmemis asset
- sahipsiz cihazlar
- organizasyon / kampus / bina bazli dagilim

### 2. Organizasyon

Amac:
- kurumsal hiyerarsi yonetimi

Alt ekranlar:
- Organizasyon listesi
- Organizasyon detay
- Birim agaci
- Maliyet merkezi listesi

### 3. Lokasyonlar

Amac:
- fiziksel yerlesim hiyerarsisini yonetmek

Alt ekranlar:
- Lokasyon agaci
- Kampus listesi
- Bina / blok / kat / alan listesi
- Lokasyon detay

### 4. Kisiler

Amac:
- primary user ve owner olarak kullanilacak kurumsal kisi kayitlarini yonetmek

Alt ekranlar:
- Kisi listesi
- Kisi detay
- Import / eslestirme ozetleri

### 5. Assetler

Amac:
- kurumsal cihaz kaydini yonetmek

Alt ekranlar:
- Asset listesi
- Yeni asset
- Asset detay
- Asset gecmisi

### 6. Eslestirme Kuyrugu

Amac:
- teknik agent ile kurumsal asset arasindaki baglari yonetmek

Alt ekranlar:
- Eslesmeyen agentler
- Eslesmeyen assetler
- Onerilen eslesmeler
- Manuel baglama ekrani

### 7. Veri Kalitesi

Amac:
- eksik, hatali, tutarsiz kayitlari duzeltmek

Alt ekranlar:
- Sahipsiz cihazlar
- Lokasyonsuz cihazlar
- Maliyet merkezsiz cihazlar
- Duplicate / conflict listesi

### 8. Raporlar

Amac:
- baglamsal raporlar ve export

Alt ekranlar:
- Organizasyon bazli ozet
- Lokasyon bazli ozet
- Kullanim tipi raporu
- Lisans ve risk raporu
- Eslesme kalitesi raporu

### 9. Ayarlar

Amac:
- alan sozlukleri ve mod ayarlari

Alt ekranlar:
- cihaz tipleri
- sahiplik tipleri
- kullanim tipleri
- yasam dongusu durumlari
- eslestirme kurallari

## Ekranlar Arasi Iliski

Ana akis:

1. Organizasyon ve lokasyon yapisi tanimlanir
2. Kisi ve maliyet merkezi baglamlari yuklenir
3. Asset kayitlari acilir veya import edilir
4. Agent-asset eslestirmesi yapilir
5. Veri kalitesi sorunlari temizlenir
6. Raporlar ve dashboardlar kullanilir

## Kanonik Model Kararlari

Bu modun bilgi mimarisi su sabit kararlar uzerine kurulur:

- organizasyon ve lokasyon iki ayri agactir
- kisi kaydi ayri bir alt modul olarak ele alinir
- asset formu her zaman hem organizasyon hem lokasyon bagi tasir
- maliyet merkezi organizasyondan ayrik ama organizasyona bagli bir yapidir
- eslestirme kuyrugu teknik kimlik ile is kimligini birlestiren tek operasyon ekranidir

## Gelecekte Cekirdege Tasinabilecek Alanlar

Bu mod olgunlastiginda asagidaki ekranlara kontrollu bilgi eklenebilir:

- ajan detay
  - asset tag
  - primary user
  - organizasyon / lokasyon / birim
- remote support listesi
  - lokasyon
  - sahiplik
  - kullanim tipi
- dashboard
  - organizasyon bazli risk dagilimi
  - lokasyon bazli operasyon baskisi

Ancak ilk fazda bunlar **sadece bu yeni mod icinde** kalir.
