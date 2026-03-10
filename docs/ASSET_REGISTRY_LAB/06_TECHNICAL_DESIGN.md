# 06 - Technical Design

## Hedef

Mevcut AppCenter sistemini bozmadan yeni bir `Asset Registry / CMDB Lab` modulu eklemek.

## Teknik Sinirlar

Ilk fazda mevcut alanlara mudahale edilmez:
- mevcut dashboard
- mevcut ajan listesi
- deployment akislari
- remote support akislari
- mevcut inventory isleme hatlari

Yeni mod:
- yeni menu
- yeni route grubu
- yeni template klasoru
- yeni servisler
- yeni tablolar
ile yasar.

Menu gorunumu:
- `Asset Management` ust menusu tek basliktir
- dropdown icinde `Hardware` ve `Software` iki kolonlu gorunumle ayrisir

## Onerilen Dizin Yapisi

```
server/
  app/
    api/v1/
      asset_registry.py
    services/
      asset_registry_service.py
      organization_service.py
      location_service.py
      person_registry_service.py
      asset_matching_service.py
      asset_reporting_service.py
    templates/
      asset_registry/
        overview.html
        people_list.html
        person_detail.html
        assets_list.html
        asset_detail.html
        org_tree.html
        locations.html
        matching_queue.html
        data_quality.html
        reports.html
        settings.html
    static/
      js/
        asset-registry.js
```

## Onerilen Route Yapisi

UI:
- `/asset-registry`
- `/asset-registry/people`
- `/asset-registry/assets`
- `/asset-registry/assets/{asset_id}`
- `/asset-registry/organization`
- `/asset-registry/locations`
- `/asset-registry/matching`
- `/asset-registry/data-quality`
- `/asset-registry/reports`
- `/asset-registry/settings`

API:
- `/api/v1/asset-registry/overview`
- `/api/v1/asset-registry/people`
- `/api/v1/asset-registry/assets`
- `/api/v1/asset-registry/assets/{id}`
- `/api/v1/asset-registry/organization`
- `/api/v1/asset-registry/locations`
- `/api/v1/asset-registry/matching/candidates`
- `/api/v1/asset-registry/matching/link`
- `/api/v1/asset-registry/data-quality`
- `/api/v1/asset-registry/reports/*`

Notlar:
- overview endpoint'i snapshot KPI'lara ek olarak son 7 gun trend serilerini de doner
- ayni payload icinde organizasyon ve lokasyon bazli risk yogunlugu listeleri de doner
- detail ekranlarindaki ortak client-side yardimci fonksiyonlar `static/js/asset-registry.js` altinda toplanir

## Servis Ayristirma

### `asset_registry_service`

Sorumluluklar:
- asset CRUD
- detay veri birlestirme
- liste filtreleme
- data quality ozetleri
- zorunlu alan kontrolu

### `organization_service`

Sorumluluklar:
- organizasyon agaci CRUD
- node type semantiklerini koruma
- maliyet merkezi baglari

### `location_service`

Sorumluluklar:
- lokasyon agaci CRUD
- lokasyon path hesaplama
- org-location bag kontrolu

### `person_registry_service`

Sorumluluklar:
- kisi CRUD
- import / update kurallari
- person-asset baglam query'leri

### `asset_matching_service`

Sorumluluklar:
- eslesme adaylarini uretme
- confidence skoru hesaplama
- manuel baglama / ayirma
- confidence sinyallerini acik neden listesi olarak UI'a tasima

Varsayilan confidence sinyalleri:
- hostname = asset tag
- hostname = inventory number
- hostname = serial number
- login user = primary person
- login user = owner person

### `asset_reporting_service`

Sorumluluklar:
- organizasyon bazli ozetler
- lokasyon bazli ozetler
- maliyet merkezi raporlari
- veri kalite raporlari

## Kanonik Kurallar

Bu teknik tasarimda asagidaki kurallar sabittir:

- mevcut `agents` runtime modeli degistirilmez
- yeni modul kendi tablolarina yazar
- `org_nodes` ve `location_nodes` ayri servislerce yonetilir
- UI etiketleri kuruma gore degisebilir ama semantik node tipleri korunur
- eslestirme mantigi servis katmaninda kalir, template icine dagitilmaz

## Entegrasyon Katmanlari

### 1. Salt-okunur teknik baglanti

Yeni mod asagidaki mevcut verileri okur:
- `agents`
- `agent_software_inventory`
- `remote_support_sessions`
- `task_history`

Ancak ilk fazda bunlara yazmaz.

### 2. Ayrik yazma modeli

Yazma operasyonlari sadece yeni tablolara gider:
- `assets`
- `org_nodes`
- `location_nodes`
- `asset_agent_links`
- `person_registry`
- `cost_centers`
- `asset_change_log`
- `organization_node_types`
- `location_node_types`

### 3. Sonradan birlesme noktasi

Olgunluk sonrasi:
- ajan detayina asset ozet paneli eklenebilir
- remote support listesine lokasyon bilgisi eklenebilir
- dashboard'a organizasyon bazli dagilim eklenebilir

Ama bunlar ayri bir fazdir.

## Eslestirme Mantigi

Ilk fazda eslesme motoru yardimci olacaktir; karar mekanizmasi operator ekranindadir.

Eslestirme sinyalleri:
- hostname benzerligi
- serial number
- model / manufacturer
- login user
- lokasyon kurali
- organizasyon ipucu
- manuel import

Confidence seviyesi:
- `high`
- `medium`
- `low`

Kural:
- `high` bile olsa otomatik baglama varsayilan davranis olmamali
- operator onayi ile kesinlesmeli

## Yetkilendirme

Onerilen yeni izinler:
- `asset_registry.view`
- `asset_registry.assets.manage`
- `asset_registry.organization.manage`
- `asset_registry.locations.manage`
- `asset_registry.people.manage`
- `asset_registry.matching.manage`
- `asset_registry.reports.view`
- `asset_registry.settings.manage`

## Fazlara Gore Gelisim

### Faz A - Lab / Izole modul
- yeni tablolar
- yeni menu
- overview
- people list / detail
- asset list / detail
- organization / locations

### Faz B - Matching
- eslestirme kuyrugu
- confidence kurallari
- veri kalite ekrani
- audit ve change log altyapisi

### Faz C - Reporting
- raporlar
- exportlar
- dashboardlar

### Faz D - Controlled Core Integration
- ajan detayda asset ozet
- remote support'ta lokasyon gorunumu
- ana dashboard'a kontrollu veri tasima

## Test Yaklasimi

Test katmanlari:
- servis unit testleri
- liste filtreleme testleri
- eslestirme confidence testleri
- role/permission testleri
- UI smoke testleri

Kritik regression kurali:
- mevcut `/agents`, `/dashboard`, `/remote-support`, `/deployments` ekranlarinin davranisi degismemeli
