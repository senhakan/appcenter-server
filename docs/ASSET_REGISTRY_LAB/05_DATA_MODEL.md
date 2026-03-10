# 05 - Data Model

Bu belge, ilk asama icin onerilen hafif ama genisleyebilir veri modelini tanimlar.

## Tasarim Ilkesi

Mevcut `agents` tablosu teknik runtime kaydidir.
Yeni model kurumsal baglam katmani icin ayri tablolar kullanir.

Ilk fazda:
- mevcut tabloyu bozma
- yeni tablolarla ilerle
- iliskiyi baglayici alanlarla kur

## Ana Varliklar

### 1. `org_nodes`

Kurumsal hiyerarsi.

Alanlar:
- `id`
- `parent_id`
- `node_type`
- `name`
- `code`
- `is_active`
- `sort_order`
- `notes`
- `created_at`
- `updated_at`

`node_type` ornekleri:
- `company`
- `legal_entity`
- `region`
- `directorate`
- `department`
- `team`
- `unit`

Model kurali:
- bu sira veri modelinin anlamsal referansidir
- UI farkli etiket gosterebilir
- raporlama ve veri kalite kurallari bu anlamsal seviyeler uzerinden kurulur

Onerilen varsayilan kurumsal akıs:
- `company`
- `legal_entity`
- `region`
- `directorate`
- `department`
- `team`
- `unit`

### 2. `location_nodes`

Fiziksel hiyerarsi.

Alanlar:
- `id`
- `parent_id`
- `location_type`
- `org_node_id`
- `name`
- `code`
- `address_text`
- `is_active`
- `notes`
- `created_at`
- `updated_at`

`location_type` ornekleri:
- `campus`
- `building`
- `block`
- `floor`
- `area`
- `room`

### 3. `cost_centers`

Alanlar:
- `id`
- `parent_id`
- `code`
- `name`
- `org_node_id`
- `is_active`
- `created_at`
- `updated_at`

### 4. `person_registry`

Kurumsal kisi kaydi.

Alanlar:
- `id`
- `person_code`
- `username`
- `full_name`
- `email`
- `phone`
- `title`
- `org_node_id`
- `cost_center_id`
- `source_type`
- `is_active`
- `created_at`
- `updated_at`

`source_type`:
- `manual`
- `import`
- `ldap`
- `entra`

Ek alan adaylari:
- `manager_person_id`
- `employee_status`
- `external_ref`

### 5. `assets`

Kurumsal cihaz kaydi.

Alanlar:
- `id`
- `asset_tag`
- `serial_number`
- `inventory_number`
- `device_type`
- `usage_type`
- `ownership_type`
- `lifecycle_status`
- `criticality`
- `manufacturer`
- `model`
- `purchase_date`
- `warranty_end_date`
- `org_node_id`
- `location_node_id`
- `cost_center_id`
- `primary_person_id`
- `owner_person_id`
- `support_team`
- `notes`
- `last_verified_at`
- `last_verified_by`
- `created_at`
- `updated_at`

### 6. `asset_agent_links`

Asset ile teknik agent arasindaki bag.

Alanlar:
- `id`
- `asset_id`
- `agent_uuid`
- `link_status`
- `match_source`
- `confidence_score`
- `is_primary`
- `linked_at`
- `linked_by`
- `unlinked_at`
- `unlink_reason`

`match_source`:
- `manual`
- `rule`
- `import`
- `hostname_guess`
- `serial_match`

`confidence_score` sinyal kaynaklari:
- `hostname = asset_tag`
- `hostname = inventory_number`
- `hostname = serial_number`
- `login_user = primary_person`
- `login_user = owner_person`

### 7. `asset_data_quality_issues`

Veri kalitesi izleme kayitlari.

Alanlar:
- `id`
- `asset_id`
- `issue_type`
- `severity`
- `status`
- `summary`
- `details_json`
- `detected_at`
- `resolved_at`
- `resolved_by`

### 8. `asset_change_log`

Kritik alan degisikliklerini tutar.

Alanlar:
- `id`
- `asset_id`
- `change_type`
- `field_name`
- `old_value`
- `new_value`
- `changed_by`
- `changed_at`

### 9. `organization_node_types`

Kuruma ozel etiketleme veya gorunum amacli node tipi metadata tablosu.

Alanlar:
- `id`
- `code`
- `display_name`
- `sort_order`
- `is_active`

### 10. `location_node_types`

Kuruma ozel lokasyon etiketleme metadata tablosu.

Alanlar:
- `id`
- `code`
- `display_name`
- `sort_order`
- `is_active`

## Onerilen Sozlukler

### `device_type`
- `desktop`
- `laptop`
- `tablet`
- `thin_client`
- `workstation`
- `kiosk`
- `shared_terminal`
- `meeting_room_terminal`
- `field_device`

### `usage_type`
- `personal`
- `shared`
- `kiosk`
- `field`
- `meeting_room`
- `admin`

### `ownership_type`
- `company`
- `leased`
- `partner`
- `personal`

### `lifecycle_status`
- `planned`
- `active`
- `in_stock`
- `in_repair`
- `retired`
- `lost`
- `awaiting_match`

## Dikey Uyarlama Notlari

Bu veri modeli varsayilan olarak genel kurumsal kullanim icin tasarlanmistir.
Ancak farkli dikeylere uyarlanabilir.

Ornekler:
- saglikta `org_nodes` klinik ve idari yapilari temsil edebilir
- uretimde `location_nodes` tesis / hat / alan yapisina acilabilir
- egitimde `org_nodes` fakulte / bolum / idari birim seklinde kullanilabilir

Bu nedenle ilk faz icin kritik alanlar:
- `usage_type`
- `org_node_id`
- `location_node_id`
- `ownership_type`

## Model Kurallari

- `org_nodes` ve `location_nodes` birlestirilmez
- `assets` tablosu her zaman kurumsal ana kayittir
- `asset_agent_links` history tutan iliski tablosudur
- `person_registry` ilk fazda hafif tutulur ama ileride identity senkronizasyonuna acik olmalidir
- sozluk tablolari UI etiketlerini esnek tutmak icin ayrik tutulur

## Entegrasyon Yaklasimi

Ilk asama:
- `agents` kaydi oldugu gibi kalir
- asset baglamina sadece `asset_agent_links` uzerinden baglanir

Boylece:
- mevcut ekranlar bozulmaz
- yeni mod kendi veri modelinde gelisir
- sonra istenirse `agents.asset_id` gibi daha sik baglar degerlendirilebilir
