# Agent Service Monitoring Plan (Windows + Linux)

## Hedef

Windows ve Linux ajanlardan servis listesi + durum bilgisi ortak bir veri modeliyle toplanacak, en az trafikle server'a aktarilacak, Agent Detay sayfasinda goruntulenecek ve degisen/silinen servisler tarihce olarak izlenecek.

## Temel kurallar

1. Tarama periyodu yeni bir ayar acmayacak, dogrudan `inventory_scan_interval_min` kullanacak.
2. Global ac/kapat ayari olacak: `service_monitoring_enabled`.
3. Agent bazli override olacak: `agents.service_monitoring_enabled` (null: globale bagli, true/false: override).
4. Veri trafigi minimum tutulacak:
   - Her heartbeat'te sadece `services_hash` gonder.
   - `services` listesi sadece hash degistiginde veya server `services_sync_required=true` dediginde gonder.
5. Server full snapshot uzerinden fark hesaplayacak:
   - eklenen servis
   - silinen servis
   - status degisimi
   - startup type degisimi

## Ortak veri modeli

Servis kaydi (ajanlar arasi ortak):

- `name` (zorunlu)
- `display_name`
- `status` (`running|stopped|paused|failed|unknown`)
- `startup_type` (`auto|manual|disabled|delayed|unknown`)
- `pid`
- `run_as`
- `description`

Heartbeat ek alanlari:

- `services_hash` (opsiyonel)
- `services` (opsiyonel, yukaridaki model listesi)

Heartbeat config ek alanlari:

- `service_monitoring_enabled` (effective sonuc)
- `services_sync_required` (server hash uyusmazsa true)

## Server degisiklik plani

1. DB/model:
   - `agents.services_hash`
   - `agents.services_json`
   - `agents.services_updated_at`
   - `agents.service_monitoring_enabled` (nullable bool override)
   - `agent_service_history` tablosu
2. Migration:
   - PostgreSQL icin idempotent startup migration.
3. Heartbeat isleme:
   - `services_hash` saklama.
   - `services` geldiyse normalize + snapshot update + diff history yazimi.
   - `services_sync_required` hesaplama.
4. API/UI:
   - Agent detail response'a servis izleme override alaninin eklenmesi.
   - `PUT /api/v1/web/agents/{uuid}/service-monitoring` endpointi (override).
   - `GET /api/v1/agents/{uuid}/services` ve `/services/history` endpointleri.
   - Agent Detay sayfasinda:
     - effective durum gostergesi
     - override ac/kapat kontrolu
     - servis tablosu + history tablosu
5. Settings:
   - `service_monitoring_enabled` ayari Settings sayfasina eklenir.

## Agent degisiklik plani

1. Windows agent:
   - `Win32_Service` uzerinden servis toplama.
   - normalize + hash.
   - interval dolunca veya force sync'te `services` listesini heartbeat'e ekle.
2. Linux agent:
   - `systemctl list-units --type=service --all` + `systemctl show`.
   - normalize + hash.
   - interval dolunca veya force sync'te `services` listesini heartbeat'e ekle.
3. Ortak optimizasyon:
   - Timeout'lu collect.
   - Hata olursa heartbeat bozulmaz, sadece loglanir.

## Test plani

1. Unit:
   - status/startup normalize testleri.
   - hash deterministic test.
   - diff hesaplama testleri (added/removed/status/startup).
2. Entegrasyon:
   - Heartbeat ile snapshot kaydi.
   - `services_sync_required` davranisi.
   - override endpoint davranisi.
3. Canli:
   - 1 Windows + 1 Linux test ajaninda servis start/stop + disable/enable degisiklikleri.
   - Agent Detay'da anlik yansima.
   - History'de degisim tiplerinin dogrulanmasi.

## Notlar

- Bu akista envanter tarama araligi servis tarama icin tek kaynak olur.
- Varsayilan global deger: `false` (trafik kontrollu rollout).
- Agent detayindan acilan override ile secili clientta ozel takip aktif edilebilir.
