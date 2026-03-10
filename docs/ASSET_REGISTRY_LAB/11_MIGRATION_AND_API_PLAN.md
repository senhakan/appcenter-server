# 11 - Migration And API Plan

Bu belge, kodlama oncesi teknik implementasyon islerini siraya koyar.

Amac:
- migration sirasini belirlemek
- tablo omurgasini netlestirmek
- API ve UI entegrasyon noktasini sabitlemek

## 1. Uygulama Sinirlari

Ilk faz kurali:
- mevcut `web.py`, `agent.py`, `remote_support.py`, `inventory.py` akislari degistirilmez
- yeni mod ayri route ve service grubu ile gelir
- mevcut template klasorleri etkilenmez

Yeni eklenecek ana kod alanlari:
- `server/app/api/v1/asset_registry.py`
- `server/app/services/asset_registry_service.py`
- `server/app/services/organization_service.py`
- `server/app/services/location_service.py`
- `server/app/services/person_registry_service.py`
- `server/app/services/asset_matching_service.py`
- `server/app/services/asset_reporting_service.py`
- `server/app/templates/asset_registry/*`

## 2. Migration Sirasi

Migrationlar asagidaki sirayla acilmalidir:

### Faz 1: Referans ve agac tablolar

1. `organization_node_types`
2. `location_node_types`
3. `org_nodes`
4. `location_nodes`
5. `cost_centers`
6. `person_registry`

Sebep:
- asset kaydina gecmeden once referans agaclari ve kisi kaydi hazir olmalidir

### Faz 2: Ana asset katmani

7. `assets`
8. `asset_agent_links`

Sebep:
- is baglami ve teknik bag bu fazda kurulur

### Faz 3: Veri kalitesi ve audit

9. `asset_data_quality_issues`
10. `asset_change_log`

Sebep:
- ilk CRUD sonrasi veri kalite ve gecmis altyapisi gelir

## 3. Tablo Omurgasi

Bu bolum tam DDL degil, implementasyon omurgasidir.

### `organization_node_types`

Amac:
- semantik node kodlarini sistemde sabit tutmak
- UI display label'larini esnek yapmak

Asgari kolonlar:
- `id`
- `code`
- `display_name`
- `sort_order`
- `is_active`
- `created_at`
- `updated_at`

Seed degerler:
- `company`
- `legal_entity`
- `region`
- `directorate`
- `department`
- `team`
- `unit`

### `location_node_types`

Seed degerler:
- `campus`
- `building`
- `block`
- `floor`
- `area`
- `room`

### `org_nodes`

Asgari constraintler:
- `parent_id` self reference FK
- `node_type` referans veya enum benzeri dogrulama
- `name` not null
- `is_active` not null default true

Onerilen indexler:
- `idx_org_nodes_parent_id`
- `idx_org_nodes_node_type`
- `idx_org_nodes_name`

### `location_nodes`

Asgari constraintler:
- `parent_id` self reference FK
- `org_node_id` nullable FK
- `location_type` referans veya enum benzeri dogrulama
- `name` not null

Onerilen indexler:
- `idx_location_nodes_parent_id`
- `idx_location_nodes_location_type`
- `idx_location_nodes_org_node_id`

### `cost_centers`

Asgari constraintler:
- `org_node_id` FK
- `code` not null
- `name` not null

Onerilen indexler:
- `idx_cost_centers_org_node_id`
- unique (`org_node_id`, `code`)

### `person_registry`

Asgari constraintler:
- `full_name` not null
- `source_type` not null
- `org_node_id` nullable FK
- `cost_center_id` nullable FK

Onerilen indexler:
- `idx_person_registry_username`
- `idx_person_registry_email`
- `idx_person_registry_org_node_id`

### `assets`

Asgari constraintler:
- `asset_tag` not null
- `device_type` not null
- `usage_type` not null
- `ownership_type` not null
- `lifecycle_status` not null
- `org_node_id` not null FK
- `location_node_id` not null FK
- `primary_person_id` nullable FK
- `owner_person_id` nullable FK

Onerilen indexler:
- unique (`asset_tag`)
- `idx_assets_serial_number`
- `idx_assets_org_node_id`
- `idx_assets_location_node_id`
- `idx_assets_cost_center_id`
- `idx_assets_primary_person_id`
- `idx_assets_owner_person_id`
- `idx_assets_lifecycle_status`

### `asset_agent_links`

Asgari constraintler:
- `asset_id` not null FK
- `agent_uuid` not null
- `link_status` not null
- `is_primary` not null default false

Onerilen indexler:
- `idx_asset_agent_links_asset_id`
- `idx_asset_agent_links_agent_uuid`
- `idx_asset_agent_links_link_status`
- partial unique: aktif primary link icin `agent_uuid`

Kritik kural:
- ayni `agent_uuid` icin birden fazla aktif primary link olamaz

### `asset_data_quality_issues`

Onerilen indexler:
- `idx_asset_dq_asset_id`
- `idx_asset_dq_issue_type`
- `idx_asset_dq_status`

### `asset_change_log`

Onerilen indexler:
- `idx_asset_change_log_asset_id`
- `idx_asset_change_log_changed_at`

## 4. Seed Ve Baslangic Verisi

Kodlama sirasinda asagidakiler seed edilmelidir:

- organization node types
- location node types
- varsayilan `device_type` sozlugu
- varsayilan `usage_type` sozlugu
- varsayilan `ownership_type` sozlugu
- varsayilan `lifecycle_status` sozlugu

Not:
- sozlukler sabit Python enum yerine DB tabanli seed + metadata modeliyle gitmelidir

## 5. API Katmani

Ilk fazda tek router:
- `server/app/api/v1/asset_registry.py`

Bu router hem UI sayfa endpointlerini besleyen JSON endpointleri, hem de CRUD aksiyonlarini saglar.

### 5.1 Overview

`GET /api/v1/asset-registry/overview`

Donmesi beklenen alanlar:
- `total_assets`
- `matched_assets`
- `unmatched_agents`
- `unmatched_assets`
- `owner_missing_count`
- `location_missing_count`
- `organization_distribution`
- `location_distribution`

### 5.2 Organization

`GET /api/v1/asset-registry/organization`
- tree veya liste doner

`POST /api/v1/asset-registry/organization`
- yeni dugum olusturur

`PUT /api/v1/asset-registry/organization/{id}`
- dugum gunceller

`POST /api/v1/asset-registry/organization/{id}/deactivate`
- pasife alir

### 5.3 Locations

`GET /api/v1/asset-registry/locations`
- tree veya liste doner

`POST /api/v1/asset-registry/locations`
- yeni lokasyon olusturur

`PUT /api/v1/asset-registry/locations/{id}`
- lokasyon gunceller

### 5.4 People

`GET /api/v1/asset-registry/people`
- filtreli kisi listesi

`POST /api/v1/asset-registry/people`
- yeni kisi kaydi

`PUT /api/v1/asset-registry/people/{id}`
- kisi guncelleme

`GET /api/v1/asset-registry/people/{id}`
- kisi detay + bagli asset ozetleri

### 5.5 Assets

`GET /api/v1/asset-registry/assets`
- filtreli asset listesi

`POST /api/v1/asset-registry/assets`
- yeni asset

`GET /api/v1/asset-registry/assets/{id}`
- detay veri

`PUT /api/v1/asset-registry/assets/{id}`
- asset guncelle

`POST /api/v1/asset-registry/assets/{id}/deactivate`
- pasife alma

### 5.6 Matching

`GET /api/v1/asset-registry/matching/candidates`
- eslesme adaylari

`POST /api/v1/asset-registry/matching/link`
- manuel veya onayli link kurar

`POST /api/v1/asset-registry/matching/unlink`
- aktif link kapatir

`POST /api/v1/asset-registry/matching/reject`
- oneriyi reddeder veya suppress eder

### 5.7 Data Quality

`GET /api/v1/asset-registry/data-quality`
- issue listesi

`POST /api/v1/asset-registry/data-quality/bulk-update`
- toplu duzeltme

### 5.8 Reports

`GET /api/v1/asset-registry/reports/assets-by-organization`
`GET /api/v1/asset-registry/reports/assets-by-location`
`GET /api/v1/asset-registry/reports/assets-without-owner`
`GET /api/v1/asset-registry/reports/assets-without-location`
`GET /api/v1/asset-registry/reports/matching-quality`

## 6. UI Entegrasyon Plani

Menu entegrasyonu:
- mevcut topbar/menu yapisina `Asset Management` ust menusu eklenecek
- `Asset Registry`, bu ust menu icinde `Hardware` grubu altinda konumlanacak
- mevcut yazilim envanteri ve SAM ekranlari ayni ust menu icinde `Software` grubu altina alinacak
- ilk fazda mevcut ekranlara badge, panel veya cross-link eklenmeyecek

Template kurallari:
- tum yeni sayfalar `app/templates/asset_registry/` altinda olacak
- mevcut sayfa template'leri degistirilmeyecek
- ortak stil ihtiyaci varsa page-scoped CSS tercih edilecek

## 7. Service Katmani Cagri Akisi

Beklenen akis:

1. router request alir
2. ilgili service validation ve query mantigini calistirir
3. audit / change log gerekiyorsa service icinde yazilir
4. response schema ile UI'a donulur

Kurallar:
- SQL veya ORM query karmasasi router icine konmaz
- data quality hesaplama template veya router katmanina dagitilmaz
- matching confidence hesaplama yalnizca `asset_matching_service` icinde olur

## 8. Validasyon Kurallari

Asgari validasyonlar:
- asset formunda zorunlu alanlar bos gecilemez
- aktif olmayan kisi yeni atamada secilemez
- pasif organization / location dugumu yeni kayitlarda secilemez
- `usage_type = personal` ise `primary_person_id` icin warning veya hard validation uygulanir
- ayni agent icin birden fazla aktif primary link engellenir

## 9. Rollout Sirasi

Kodlama backlog'u icin onerilen sira:

1. migrationlar
2. seed verileri
3. service iskeletleri
4. organization ve location CRUD
5. people CRUD
6. asset CRUD
7. matching
8. data quality
9. reports
10. menu entegrasyonu

## 10. Kodlama Oncesi Donusmeyecek Teknik Kararlar

- yeni modul icin tek router dosyasi ile baslanacak
- service katmani ayrik tutulacak
- yeni tablolar mevcut cekirdek tablolara dogrudan kolon eklemeden ilerleyecek
- sozlukler DB metadata modeli ile yonetilecek
- UI ilk fazda yalnizca yeni menu alani altinda calisacak
