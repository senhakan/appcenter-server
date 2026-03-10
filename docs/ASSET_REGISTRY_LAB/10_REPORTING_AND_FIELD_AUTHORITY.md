# 10 - Reporting And Field Authority

Bu belge, hangi alanin hangi ekranda referans alan oldugunu ve raporlamada hangi tablonun dogruluk kaynagi kabul edilecegini sabitler.

Amac:
- ayni bilginin farkli ekranlarda farkli yerlerden uretilmesini engellemek
- kodlama sirasinda alan anlam kaymasini onlemek

## 1. Alan Otoritesi

### Asset baglam alanlari

Asagidaki alanlarin ana kaynagi `assets` tablosudur:
- `asset_tag`
- `device_type`
- `usage_type`
- `ownership_type`
- `lifecycle_status`
- `org_node_id`
- `location_node_id`
- `cost_center_id`
- `primary_person_id`
- `owner_person_id`
- `support_team`

Kural:
- bu alanlar raporlarda `agents` veya diger runtime kaynaklardan turetilmez

### Teknik runtime alanlari

Asagidaki alanlarin ana kaynagi mevcut cekirdek teknik tablolardir:
- `online/offline`
- `last_seen`
- `hostname`
- `remote_support_status`
- inventory ozetleri

Kural:
- bu alanlar `assets` icinde duplicate edilmez

## 2. Liste Ve Detay Ekranlarinda Kaynak Kurali

### Asset listesi

Kurallar:
- organizasyon ve lokasyon `assets` uzerinden gelir
- hostname ve online/offline gibi teknik alanlar bagli agent varsa join ile gelir
- bagli agent yoksa teknik kolonlar bos veya `-` gorunur

### Asset detay

Kurallar:
- is baglami her zaman asset kaydindan okunur
- teknik iliski her zaman bagli agent ve runtime tablolardan okunur
- veri kalitesi issue listesi `asset_data_quality_issues` tablosundan gelir
- degisiklik gecmisi `asset_change_log` ve link history'den gelir

### Kisi detay

Kurallar:
- kisiye bagli asset listesi `assets.primary_person_id` ve `assets.owner_person_id` uzerinden bulunur
- kisi aktifligi pasif ise yeni atama yapilamaz

## 3. Raporlama Dogruluk Kaynaklari

### Organizasyon bazli cihaz dagilimi

Kaynak:
- `assets.org_node_id`

### Lokasyon bazli cihaz dagilimi

Kaynak:
- `assets.location_node_id`

### Maliyet merkezi bazli raporlar

Kaynak:
- `assets.cost_center_id`

### Sahipsiz cihaz raporu

Kaynak kurali:
- `usage_type = personal` ise `primary_person_id is null` olanlar
- ortak kullanim cihazlarda bu rapora dahil edilme kurali ayardan kontrol edilebilir

### Ownersiz cihaz raporu

Kaynak:
- `owner_person_id is null`

### Eslesme kalitesi raporu

Kaynak:
- `asset_agent_links`
- `asset_data_quality_issues`

## 4. Turetilen Alanlar

Asagidaki alanlar veri modelinde fiziksel kolon olmak zorunda degildir, servis katmaninda turetilir:
- `organization_path`
- `location_path`
- `has_active_agent`
- `data_quality_score`
- `last_linked_agent_hostname`

Kural:
- turetilen alanlar primary storage alanina donusturulmez

## 5. Filtreleme Kurallari

Filtre davranislari:
- organizasyon filtresi secilirse tum alt dugumleri kapsayabilir
- lokasyon filtresi secilirse tum alt lokasyonlari kapsayabilir
- bu davranis UI'da acikca belirtilir

Varsayilan:
- agac filtresi descendant-inclusive calisir

## 6. Tarihsel Tutarlilik

Raporlama icin iki zaman ekseni vardir:
- `mevcut durum`
- `tarihsel degisim`

Ilk faz kurali:
- tum standart dashboard ve liste ekranlari `mevcut durum` odaklidir
- tarihsel raporlar daha sonra `asset_change_log` ve link history uzerinden acilir

## 7. Kodlama Karari

Kodlama sirasinda su anti-patternlerden kacilacak:
- ayni alanin hem `assets` hem `agents` icinde baglamsal anlamla tutulmasi
- organizasyon yolunun farkli servislerde farkli sekilde hesaplanmasi
- rapor SQL'lerinde runtime alanlari ile asset alanlarinin dogrudan karistirilmasi
- UI tarafinda alan otoritesinin template icinde yeniden yorumlanmasi
