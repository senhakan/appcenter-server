# 04 - Screen Catalog

Bu belge, her ekranin ne ise yaradigini ve kullanicinin hangi veriyi gorecegini tanimlar.

## 1. Genel Bakis

### Amac
- modun ana ozet sayfasi

### Gosterilecek Kartlar
- toplam asset
- eslesmis asset / agent sayisi
- eslesmemis agent sayisi
- eslesmemis asset sayisi
- sahipsiz cihaz sayisi
- lokasyonsuz cihaz sayisi
- owner'i tanimsiz cihaz sayisi
- organizasyon bazli dagilim
- lokasyon bazli dagilim

### Aksiyonlar
- rapora git
- eslestirme kuyruguna git
- veri kalitesine git
- asset listesine git

### Ek Ozetler
- matching kapsama orani
- owner kapsama orani
- lokasyon eksik sayisi
- eslesmemis asset sayisi
- issue type breakdown
- son 7 gun trend panelleri
  - yeni asset
  - yeni eslesme
  - yeni issue
- action required watchlist
- risk yogunlugu listeleri
  - organizasyon bazli acik issue
  - lokasyon bazli acik issue

## 2. Asset Listesi

### Amac
- tum asset kayitlarini filtreleyip yonetmek

### Filtreler
- organizasyon
- legal entity
- region
- kampus
- bina
- kat
- birim
- maliyet merkezi
- cihaz tipi
- sahiplik tipi
- kullanim tipi
- yasam dongusu durumu
- primary user var / yok
- agent bagli / bagli degil
- serbest metin arama
- issue var / yok

### Kolonlar
- asset tag
- seri no
- cihaz tipi
- organizasyon
- lokasyon
- primary user
- owner
- support team
- maliyet merkezi
- agent baglanti durumu
- yasam dongusu durumu

### Satir Aksiyonlari
- detay
- duzenle
- agent bagla
- asset gecmisini gor
- history

## 3. Asset Detay

### Amac
- bir asset'in tum is ve teknik baglamini tek yerde toplamak

### Hero Kartlari
- asset tag / cihaz tipi / kullanim tipi
- lifecycle status
- data quality score
- issue sayisi

### Operasyon Ozeti
- kimlik ve yasam dongusu
- baglam ve sorumluluk
- teknik baglanti
- veri kalitesi

### Sag Panel
- duzenleme formu
- agent baglama formu
- aktif bag varsa agent baglantisini kes aksiyonu
- acik issue listesi

### Alt Alan
- degisiklik gecmisi

### UI Davranisi
- detail ekranindaki secici doldurma, sayisal null donusumu ve ortak HTML escape davranislari ortak JS yardimci katmanindan gelir
- cost center secimi ayni detail formu icinde yapilir
- teknik baglanti paneli agent IP, son gorulme, match source, confidence ve linked time gibi alanlari gosterir

## 4. Kisi Listesi

### Amac
- primary user ve owner olarak kullanilacak kurumsal kisi havuzunu yonetmek

### Filtreler
- organizasyon
- maliyet merkezi
- kaynak tipi
- aktif / pasif
- serbest metin arama
- asset baglanti var / yok

### Kolonlar
- ad soyad
- kullanici adi
- e-posta
- organizasyon
- maliyet merkezi
- kaynak tipi
- aktiflik

### Satir Aksiyonlari
- detay
- duzenle
- bagli assetleri gor

## 4A. Kisi Detay

### Amac
- bir kisinin asset sahipligi ve kullanim baglamini tek yerde gostermek

### Hero Kartlari
- kisi
- bagli asset sayisi
- aktif / pasif durumu

### Bilgi Alani
- kullanici adi
- e-posta
- telefon
- unvan
- organizasyon
- maliyet merkezi
- kaynak tipi

### Alt Liste
- bagli assetler

### Yan Panel
- kisi duzenleme formu
- aktif / pasif durum guncelleme

### UI Davranisi
- detail ekranindaki tekrar eden form doldurma ve secici yukleme mantigi ortak JS yardimci katmanini kullanir

## 5. Organizasyon Listesi

### Amac
- organizasyon hiyerarsisini yonetmek

### Kolonlar
- ad
- tip
- parent
- bagli asset sayisi
- bagli agent sayisi

### Aksiyonlar
- alt dugum ekle
- duzenle
- pasife al
- detay
- cost center duzenle
- cost center pasife al

### Liste Davranisi
- tip, durum ve serbest metin filtresi
- satirdan hizli duzenle
- satirdan pasife al

## 6. Lokasyon Agaci

### Amac
- fiziksel lokasyon hiyerarsisini gostermek

### Tipler
- kampus
- bina
- blok
- kat
- alan
- oda

### Gosterimler
- agac gorunumu
- tablo gorunumu
- lokasyon doluluk ozetleri
- tip filtresi
- organizasyon filtresi
- serbest metin arama

### Satir Aksiyonlari
- duzenle
- pasife al

## 7. Eslestirme Kuyrugu

### Amac
- eslesmemis veya supheli eslesmeli kayitlari cozmek

### Sekmeler
- agent var / asset yok
- asset var / agent yok
- eslesme onerileri
- conflict kayitlari

### Kolonlar
- agent hostname
- serial / model ipucu
- aday asset
- confidence
- mevcut org/lokasyon ipucu
- son gorulme
- aksiyon

### Aksiyonlar
- oneriyi onayla
- reddet
- manuel sec
- yeni asset olustur
- sinyal rozetlerini incele

### Yeni Asset Ac Ve Bagla
- `agent_without_asset` adayi icin hizli form acilir
- formdan yeni asset olusturulur
- ayni akista ilgili agent ile primary link kurulur
- islem sonunda aday kuyruktan kaybolur

## 8. Veri Kalitesi

### Amac
- operasyonel veri borcunu azaltmak

### Kartlar
- primary user eksik
- owner eksik
- lokasyon eksik
- organizasyon eksik
- maliyet merkezi eksik
- duplicate serial
- catisan eslesme

### Aksiyonlar
- toplu atama
- tekil duzeltme
- disa aktar
- secili kayitlari yeniden hesapla

### Toolbar
- issue arama
- severity filtresi
- secili asset KPI'lari

## 9. Ayarlar

### Amac
- modun referans sozluklerini ve node label gorunumlerini kurum diline uyarlamak

### Alanlar
- device type sozlugu
- usage type sozlugu
- ownership type sozlugu
- lifecycle status sozlugu
- organization node labels
- location node labels

### Kurallar
- organization ve location node label degisikligi semantik kodu degistirmez
- mevcut agac ve raporlar ayni kodlarla calismaya devam eder
- sadece form, liste ve detay ekranlarinda gorunen adlar guncellenir

## 10. Yardim Merkezi

### Amac
- son kullaniciya modulun uçtan uca nasil kullanilacagini gostermek

### Icerik
- temel is akisi
- ekran bazli ne gorurum / ne yaparim tablosu
- hizli baslangic baglantilari
- yayin kurallari

### Erisim
- subnav uzerinden `Yardim`
- overview ekranindaki hizli gecis karti
## 11. Cekirdek Ekran Baglami

### Ajan Detay
- mevcut `Ajan Detay` sayfasinda read-only `Asset Registry Baglami` karti gosterilir
- bu kart yalnizca aktif primary asset-agent link varsa gorunur
- kart uzerinden asset detay ekranina gecis verilir

### Gosterilecek Alanlar
- asset tag
- cihaz tipi
- yasam dongusu
- organizasyon
- lokasyon
- primary user
- owner
- support team
- data quality skoru
- issue sayisi

## 12. Raporlar

### Rapor Setleri
- organizasyon bazli cihaz dagilimi
- kampus / bina bazli cihaz dagilimi
- organizasyon birimi bazli remote support yogunlugu
- maliyet merkezi bazli lisans riski
- sahiplik tipine gore cihaz dagilimi
- ortak cihaz / bireysel cihaz dagilimi
- eslesme kalitesi raporu
- owner'siz cihaz raporu
- lokasyonsuz cihaz raporu
- organizasyon kalitesi raporu

### Cikti Tipleri
- ekranda ozet
- CSV
- Excel
- daha sonra PDF

## 10. Ayarlar

### Sozlukler
- cihaz tipleri
- kullanim tipleri
- ownership type
- lifecycle status
- support team
- organization node labels
- location node labels

### Kurallar
- otomatik eslestirme kurallari
- zorunlu alan politikasi
- veri kalite skoru kurallari
- varsayilan organizasyon seviyesi politikasi
- varsayilan lokasyon seviyesi politikasi
