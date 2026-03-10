# 07 - Phased Roadmap

## Faz 0 - Dokuman ve Onay

Teslimatlar:
- kapsam
- isletim kilavuzu
- ekran katalogu
- veri modeli
- teknik tasarim

Bu faz tamamlanmadan kod yazilmaz.

## Faz 1 - Iskelet Modul

Hedef:
- yeni menu
- overview
- organizasyon ve lokasyon temel tablolari
- asset CRUD

Teslimatlar:
- yeni route grubu
- yeni template klasoru
- yeni tablolarin migrasyonu

## Faz 2 - Eslestirme Katmani

Hedef:
- asset-agent link modeli
- eslesme kuyrugu
- confidence skorlari
- manuel baglama

Teslimatlar:
- matching queue ekranlari
- link / unlink endpointleri
- temel veri kalite kurallari

## Faz 3 - Veri Kalitesi ve Import

Hedef:
- eksik alanlari gorme
- toplu duzeltme
- import ile besleme

Teslimatlar:
- veri kalitesi paneli
- CSV import
- import validation raporu

## Faz 4 - Raporlama

Hedef:
- organizasyon bazli
- lokasyon bazli
- maliyet merkezi bazli
- sahiplik tipine gore
raporlama

Teslimatlar:
- rapor sayfalari
- exportlar
- dashboard widget adaylari

## Faz 5 - Kontrollu Cekirdek Entegrasyon

Hedef:
- ana sistemde yalnizca secilmis baglamsal gorunumleri gostermek

Ornekler:
- ajan detayda asset ozeti
- remote support listesinde organizasyon / lokasyon
- ana dashboard'ta organizasyon bazli ozetler

Bu faza gecis kriterleri:
- veri kalitesi kabul edilebilir seviyede olmali
- eslesme dogrulugu yuksek olmali
- kullanici ekibi ekranlari aktif kullanmaya baslamis olmali

## Onerilen Ilk Is Sirasi

1. Organizasyon modeli
2. Lokasyon modeli
3. Asset CRUD
4. Asset-agent bag modeli
5. Matching queue
6. Veri kalitesi paneli
7. Raporlama
8. Cekirdege secili entegrasyon

## Riskler

- veri modeli fazla buyuyebilir
- teknik agent ile kurumsal asset karistirilabilir
- otomatik eslestirme yanlis guven yaratabilir
- kurumsal yapilarda hiyerarsi varyasyonlari fazla olabilir

## Risk Azaltma

- ilk fazda hafif model
- manuel onayli eslestirme
- alan sozluklerini ayarlardan yonetme
- cekirdege gecmeden once pilot kullanim
