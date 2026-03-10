# Asset Registry / CMDB Lab

Bu klasor, AppCenter icinde mevcut sistemi etkilemeden gelistirilecek yeni `Asset Registry / CMDB Lab` inisiyatifi icin ayrilmis dokuman setidir.

Amac:
- mevcut ekranlari, API'leri ve veri modelini bozmadan
- `Asset Management` ust menusu altinda konumlanan yeni bir bilgi mimarisi icinde
- cok-sirketli, cok-birimli ve cok-lokasyonlu kurumsal yapilari destekleyecek
- ileride cekirdege alinabilecek
ayri bir varlik ve baglam yonetim katmani tasarlamaktir.

Calisma sirasi su sekilde baslatilmistir:

1. Kilavuz
2. Bilgi mimarisi ve ekranlar
3. Teknik tasarim
4. Kodlama

Bugunku durum:
- dokuman seti tamamlandi
- lab modulu repo icinde islevsel hale getirildi
- mevcut cekirdek ekranlara sadece kontrollu ve read-only baglam panelleri ekleniyor
- entegrasyonlar halen izole kapsamda tutuluyor

## Kapsam Ve Izolasyon Kurali

- Bu klasor ve bu mod icin acilacak kod alanlari genel server gelistirme kapsamindan bilincli olarak ayridir.
- Asset Registry / CMDB isi acikca istenmedigi surece bu klasor ve ilgili kod yolları baska gorevlerde isleme alinmaz.
- Bu alan sadece asagidaki tip islerde aktif kabul edilir:
  - asset management
  - asset registry
  - CMDB
  - organization / location / ownership baglami
  - asset-agent eslestirme
- Bu isler disinda:
  - klasorde dokuman guncellemesi yapilmaz
  - bu mod icin yeni kod dosyasi acilmaz
  - mevcut baska gelistirmeler bu alanla karistirilmaz

Ilgili kod kapsami:
- `server/app/api/v1/asset_registry.py`
- `server/app/services/asset_registry_service.py`
- `server/app/services/organization_service.py`
- `server/app/services/location_service.py`
- `server/app/services/person_registry_service.py`
- `server/app/services/asset_matching_service.py`
- `server/app/services/asset_reporting_service.py`
- `server/app/templates/asset_registry/`

## Dosya Sirasi

1. `01_SCOPE_AND_PRINCIPLES.md`
   Inisiyatifin amaci, kapsam sinirlari, prensipler ve mevcut sisteme temas kurallari.

2. `02_OPERATING_GUIDE.md`
   Isletim kilavuzu: kullanici hangi ekranda ne yapar, hangi bilgiyi gorur, hangi karari verir.

3. `03_INFORMATION_ARCHITECTURE.md`
   Menu yapisi, moduller, alt moduller, ekranlar ve ekranlar arasi iliskiler.

4. `04_SCREEN_CATALOG.md`
   Tek tek ekran katalogu: her ekranin amaci, aksiyonlari, filtreleri, tabloları ve ciktilari.

5. `05_DATA_MODEL.md`
   Hafif ama gelisime acik asset registry veri modeli.

6. `06_TECHNICAL_DESIGN.md`
   Teknik mimari, entegrasyon sinirlari, servis kurallari, rollout yaklasimi.

7. `07_PHASED_ROADMAP.md`
   Fazlara bolunmus gecis ve olgunlastirma plani.

8. `08_CANONICAL_MODEL.md`
   Sonradan degistirilmesi zor olacak temel organizasyon, lokasyon, sahiplik ve iliski kararlarinin sabitlendigi belge.

9. `09_FORM_AND_WORKFLOW_SPEC.md`
   Ekran bazli form alanlari, zorunluluk kurallari, alan bagimliliklari ve kullanici aksiyon sonuculari.

10. `10_REPORTING_AND_FIELD_AUTHORITY.md`
    Hangi alanin hangi kaynaktan geldigi ve raporlamada tek dogruluk kaynagi kurallari.

11. `11_MIGRATION_AND_API_PLAN.md`
    Kodlama oncesi migration sirasi, tablo omurgasi, API endpoint sozlesmeleri ve entegrasyon plani.

12. `12_IMPLEMENTATION_BACKLOG.md`
    Fazlara, is paketlerine, bagimliliklara ve kabul kriterlerine ayrilmis uygulama backlog'u.

## Temel Yakinim

- Bu mod ulta mevcut `agents`, `inventory`, `groups`, `deployments`, `remote_support` yapilarina dogrudan mudahale edilmez.
- Ilk asamada `Asset Management` altinda `Hardware > Asset Registry` olarak ayri bir deneysel alan olusturulur.
- Yazilim envanteri ve SAM ekranlari ayni cati altinda `Software` grubunda konumlanir.
- Mevcut sistemin teknik kimligi `agent` olmaya devam eder.
- Yeni katmanin is kimligi `asset / organization / location / ownership` olur.
- Zaman icinde olgunlastikca cekirdek ekranlara kontrollu sekilde entegre edilir.
