# 09 - Form And Workflow Specification

Bu belge, ekranlari uygulama gelistirmeye uygun ayrintiya indirir.

Amac:
- her ana ekran icin hangi alanlarin gosterilecegini netlestirmek
- hangi alanin zorunlu, opsiyonel veya kosullu oldugunu sabitlemek
- form davranislarini ve aksiyon sonuclarini tanimlamak

## 1. Ortak Form Kurallari

Tum formlar icin temel kurallar:

- zorunlu alanlar gorsel olarak ayrik isaretlenir
- pasif sozluk degerleri yeni kayitlarda secilemez
- referans alanlar arama destekli secici ile acilir
- silme yerine `pasife alma` varsayilan davranistir
- audit icin kritik degisikliklerde degistiren kullanici ve zaman kaydi tutulur

Alan durumlari:
- `zorunlu`
- `opsiyonel`
- `kosullu zorunlu`
- `salt okunur`

## 2. Organizasyon Dugumu Formu

Ekran:
- `Asset Registry > Organizasyon > Yeni Dugum`
- `Asset Registry > Organizasyon > Duzenle`

Alanlar:
- `node_type`
  - zorunlu
  - sozlukten secilir
- `parent_id`
  - kosullu zorunlu
  - en ust seviye degilse zorunlu
- `name`
  - zorunlu
- `code`
  - opsiyonel ama tavsiye edilir
- `is_active`
  - duzenlemede gosterilir
- `notes`
  - opsiyonel

Davranislar:
- parent secildiginde sadece uyumlu alt seviye tipler onerilir
- ayni parent altinda ayni `name` + `node_type` kombinasyonu engellenir
- pasife alma, cocuk dugum veya bagli aktif asset varsa uyari ile gelir

Kayit Sonucu:
- organizasyon agacina yeni dugum eklenir
- rapor filtrelerinde secilebilir hale gelir

## 3. Lokasyon Dugumu Formu

Ekran:
- `Asset Registry > Lokasyonlar > Yeni Dugum`
- `Asset Registry > Lokasyonlar > Duzenle`

Alanlar:
- `location_type`
  - zorunlu
- `parent_id`
  - kosullu zorunlu
- `org_node_id`
  - opsiyonel
  - belirli lokasyonun bagli oldugu organizasyon kirilimi icin kullanilir
- `name`
  - zorunlu
- `code`
  - opsiyonel
- `address_text`
  - opsiyonel
- `is_active`
  - duzenlemede gosterilir
- `notes`
  - opsiyonel

Davranislar:
- parent secildiginde sadece uyumlu alt lokasyon tipleri onerilir
- ayni parent altinda ayni `name` + `location_type` kombinasyonu engellenir
- lokasyon pasife alinmadan once bagli aktif asset sayisi gosterilir

## 4. Kisi Formu

Ekran:
- `Asset Registry > Kisiler > Yeni Kisi`
- `Asset Registry > Kisiler > Duzenle`

Alanlar:
- `person_code`
  - opsiyonel
- `username`
  - kosullu zorunlu
  - import / identity eslestirme yapilacaksa zorunlu kabul edilir
- `full_name`
  - zorunlu
- `email`
  - opsiyonel
- `phone`
  - opsiyonel
- `title`
  - opsiyonel
- `org_node_id`
  - opsiyonel
- `cost_center_id`
  - opsiyonel
- `source_type`
  - zorunlu
- `is_active`
  - duzenlemede gosterilir

Davranislar:
- `source_type = ldap | entra` ise kritik alanlarin bir bolumu salt-okunur modda olabilir
- pasif kisi yeni asset atamalarinda secilemez

## 5. Asset Formu

Ekran:
- `Asset Registry > Assetler > Yeni Asset`
- `Asset Registry > Assetler > Duzenle`

### 5.1 Temel Alanlar

- `asset_tag`
  - zorunlu
- `serial_number`
  - opsiyonel
- `inventory_number`
  - opsiyonel
- `device_type`
  - zorunlu
- `usage_type`
  - zorunlu
- `ownership_type`
  - zorunlu
- `lifecycle_status`
  - zorunlu
- `criticality`
  - opsiyonel
- `manufacturer`
  - opsiyonel
- `model`
  - opsiyonel
- `purchase_date`
  - opsiyonel
- `warranty_end_date`
  - opsiyonel

### 5.2 Baglam Alanlari

- `org_node_id`
  - zorunlu
- `location_node_id`
  - zorunlu
- `cost_center_id`
  - opsiyonel ama raporlama icin tavsiye edilir
- `primary_person_id`
  - kosullu zorunlu
  - `usage_type = personal` ise guclu zorunlu
- `owner_person_id`
  - opsiyonel
- `support_team`
  - kosullu zorunlu
  - `usage_type = shared | kiosk | field` ise tavsiye edilir
- `notes`
  - opsiyonel

### 5.3 Davranis Kurallari

- `usage_type = personal` secilirse form `primary_person_id` alanini one cikarir
- `usage_type = shared` secilirse `support_team` alani one cikarir
- `lifecycle_status = retired` ise yeni aktif agent linki kurma ekranda kisitlanabilir
- `org_node_id` degistiginde, uyumsuz `cost_center_id` secimi sifirlanir
- `location_node_id` degistiginde, data quality yeniden hesaplanir

### 5.4 Kayit Sonucu

- yeni asset kaydi acilir
- change log kaydi yazilir
- data quality kontrolu tetiklenir

## 6. Asset Detay Ekrani Davranisi

Kurallar:
- ustte hero KPI kartlari yer alir:
  - asset
  - yasam dongusu
  - data quality
  - issue sayisi
- ana govdede operasyon ozeti 4 blokta sunulur:
  - kimlik ve yasam dongusu
  - baglam ve sorumluluk
  - teknik baglanti
  - veri kalitesi
- sag panelde:
  - duzenleme formu
  - agent baglama formu
  - aktif link varsa unlink aksiyonu
  - acik issue listesi
- gecmis alani kronolojik degisiklikleri ayrica listeler

## 7. Eslestirme Kuyrugu Davranisi

Sekmeler:
- `Agent var / Asset yok`
- `Asset var / Agent yok`
- `Eslesme onerileri`
- `Conflict`

Kolon davranislari:
- confidence renk ile gosterilir
- hostname, serial, login user ve lokasyon ipucu ayri sinyal rozetleri olarak gosterilir
- operator neden bu onerinin geldigini gorebilir
- `agent_without_asset` kaydi icin ayni ekranda yeni asset olusturma paneli acilabilir
- yeni asset olusturuldugunda ayni islem zincirinde primary link kurulur

Aksiyonlar:
- `Onayla`
  - aktif link olusturur
  - onceki aktif link varsa kapatma onayi ister
- `Reddet`
  - oneriyi suppress eder
- `Manuel Sec`
  - asset arama modalini acar
- `Yeni Asset`
  - secili agent ipuclariyla asset formunu on doldurur

## 8. Veri Kalitesi Ekrani Davranisi

Kartlar:
- `Primary user eksik`
- `Owner eksik`
- `Organizasyon eksik`
- `Lokasyon eksik`
- `Maliyet merkezi eksik`
- `Duplicate serial`
- `Catisan eslesme`

Kurallar:
- her kart tiklanabilir listeye gider
- toplu islem sadece ayni issue type icin acilir
- toplu islem oncesi etkilenecek kayit sayisi gosterilir

## 9. Rapor Ekrani Davranisi

Filtre paneli:
- tarih araligi
- organizasyon
- lokasyon
- device type
- usage type
- lifecycle status

Cikti kurallari:
- ekrandaki tablo ile export ayni filtre setini kullanir
- export loglanir
- buyuk exportlar async is olarak planlanabilir

## 10. Ayarlar Ekrani Davranisi

Alt alanlar:
- sozluk yonetimi
- node label yonetimi
- zorunlu alan politikasi
- eslestirme kurallari
- veri kalite kurallari

Kurallar:
- varsayilan semantik node tipleri silinemez
- sadece display label degistirilebilir
- aktif kullanimdaki sozluk degeri dogrudan silinemez, pasife alinabilir

## 11. Onemli Kullanici Akislari

### Akis 1: Yeni kurulum

1. Organizasyon agaci kurulur
2. Lokasyon agaci kurulur
3. Kisi importu yapilir
4. Asset kayitlari acilir veya import edilir
5. Eslestirme kuyrugu temizlenir
6. Veri kalitesi duzeltilir

### Akis 2: Help desk inceleme

1. Operator asset arar
2. Asset detayda organizasyon, lokasyon ve primary user gorur
3. Teknik iliskiden bagli agenti kontrol eder
4. Gerekirse mevcut cekirdek ekranlara gecer

### Akis 3: Veri kalitesi operasyonu

1. Operator karttan issue listesine girer
2. Filtreyi daraltir
3. Toplu veya tekil duzeltme yapar
4. Sonucu raporda dogrular

## 12. Kodlama Oncesi Donusmeyecek Kararlar

Kodlamaya baslamadan once sabit kabul edilmesi gereken ekran kararlar:
- asset formunda organizasyon ve lokasyon ayni ekranda olacak
- kisi yonetimi ayri menu olacak
- eslestirme kuyrugu ayri operasyon ekrani olacak
- veri kalitesi ayri ekran olacak
- ayarlar ekraninda node label degisikligi semantik model yerine sadece gorunumu etkileyecek
