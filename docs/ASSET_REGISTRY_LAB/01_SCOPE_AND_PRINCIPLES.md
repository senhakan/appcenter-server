# 01 - Scope And Principles

## Problem Tanimi

AppCenter bugun teknik olarak sunlari yonetmektedir:
- agent
- envanter
- deployment
- remote support
- duyuru
- audit ve temel dashboardlar

Ancak kurumsal sorularin onemli bir bolumu halen cevapsizdir:
- Bu cihaz kime ait?
- Hangi kurum / tesis / bina / kat / birimdedir?
- Hangi maliyet merkezi altindadir?
- Bu cihaz bireysel kullanim cihazimi, ortak alan terminalimi, kiosk mu, saha cihazi mi?
- Bu cihaz hangi kurumsal organizasyon hiyerarsisine baglidir?

Bu inisiyatifin hedefi, AppCenter'a `teknik envanter` uzerine oturan bir `is baglami / asset registry` katmani eklemektir.

## Kapsam

Ilk asama kapsami:
- kurumsal organizasyon hiyerarsisi
- lokasyon hiyerarsisi
- asset kaydi
- asset ile agent iliskisi
- sahiplik ve kullanim modeli
- maliyet merkezi ve baglamsal alanlar
- manuel ve yari-otomatik eslestirme
- raporlama ve filtreleme

Bu asamada kapsam disi:
- tam ITSM / full CMDB federasyonu
- change management
- incident / request management
- muhasebe entegrasyonu
- patch orchestration
- policy enforcement
- HR / LDAP canli senkronizasyonunun tum detaylari

## Ana Prensipler

### 1. Mevcut sistemi etkilememe

- Var olan menuler, ekranlar, endpointler ve veri modeli ilk fazda degistirilmez.
- Yeni alanlar `yan mod` olarak yasayacaktir.
- Mevcut dashboard, ajan listesi, deployment akislari oldugu gibi calismaya devam etmelidir.

### 2. Ayrik gelisim

- Yeni mod icin ayri menu yapisi kurulur.
- Ayrik sayfalar, ayrik servisler, ayrik tablolar tercih edilir.
- Entegrasyon ilk fazda salt-okunur veya opsiyonel baglar uzerinden ilerler.

### 3. Genel kurumsal ve cok-kurumlu model

Model su yapilari desteklemelidir:
- birden fazla sirket / kurum / bagli ortaklik
- bir kurum altinda birden fazla kampus / tesis / saha
- bir kampus veya tesis altinda birden fazla bina / blok / kat / alan
- genel organizasyon hiyerarsisi: sirket / bolge / direktorluk / departman / takim / birim
- genel kullanim tipleri: bireysel cihaz / ortak terminal / kiosk / saha cihazi / vardiya terminali
- farkli dikeyleri kapsayacak esneklik: saglik, egitim, kamu, holding, uretim, perakende

### 4. Teknik kimlik ve is kimligi ayrimi

- `Agent`: teknik varlik, heartbeat, status, inventory, remote support
- `Asset`: kurumsal varlik, sahiplik, lokasyon, baglam, yasam dongusu

Bu iki nesne ayni sey degildir; ama iliskilidir.

### 5. Hafif ama genisleyebilir model

Ilk asama `hafif asset registry` ile baslar.
Gelecekte:
- CMDB iliskileri
- external import
- ownership history
- contract / warranty
- policy scoping
gibi alanlara acik olmalidir.

## Kurumsal Kullanici Senaryolari

Bu mod asagidaki roller icin deger uretir:

- IT operasyon
  cihaz hangi lokasyonda ve kime bagli biliyor olmak ister
- yardim masasi
  remote support baslatmadan once cihazin baglamini gormek ister
- bilgi guvenligi
  riskli cihazlarin hangi kurum / lokasyonda yogunlastigini gormek ister
- lisans yonetimi
  maliyet merkezi bazli lisans tuketimi ister
- ust yonetim
  kurum / kampus / bina bazli ozet ister

## Basari Kriterleri

Ilk olgunluk seviyesinde basari kriterleri:
- agent ile asset iliskisi ayri modulde yonetilebiliyor olmali
- organizasyon / kampus / bina / birim bazli filtreleme calismali
- sahipsiz ve eslesmemis cihazlar ayri gorunebilmeli
- ortak kullanim cihazlari ile bireysel kullanim cihazlari ayrisabilmeli
- dashboard ve raporlar bu baglamlarla uretilmeli
