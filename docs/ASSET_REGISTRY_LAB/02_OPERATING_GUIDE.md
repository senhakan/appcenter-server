# 02 - Operating Guide

Bu belge, yeni mod olgunlastiginda kullanicinin hangi ekrandan ne yapacagini tanimlar.

## Hedef Kullanici Rolleri

### 1. Platform Admin

Yetkileri:
- organizasyon hiyerarsisini olusturur
- lokasyon hiyerarsisini olusturur
- alan sozluklerini tanimlar
- import ve eslestirme kurallarini yonetir

### 2. Asset Operator

Yetkileri:
- asset kaydi acar / gunceller
- agent-asset eslestirir
- sahiplik ve lokasyon alanlarini duzeltir
- eslesmeyen cihaz kuyrugunu temizler

### 3. Help Desk / Support

Yetkileri:
- cihazin sahiplik ve lokasyon baglamini gorur
- remote support oncesi cihazin baglamini kontrol eder
- ama kurumsal ana veriyi degistirmez

### 4. Reporting / Audit Viewer

Yetkileri:
- rapor ve dashboard gorur
- export alir
- degisiklik gecmisini inceler

## Ana Kullanici Akislari

### A. Kurum ve lokasyon yapisini kurma

Kullanici:
- `Asset Registry > Organizasyon`
ekranina girer.

Burada sunlari yapar:
- sirket / kurum dugumleri ekler
- bolge / direktorluk / departman / birim yapisini tanimlar
- kampus / tesis / bina / blok / kat yapisini tanimlar
- maliyet merkezlerini baglar

Cikti:
- asset ve raporlar icin kullanilacak kurumsal hiyerarsi hazir olur.

### B. Asset kaydi acma

Kullanici:
- `Asset Registry > Assetler > Yeni Asset`
ekranina girer.

Burada:
- asset tag
- seri no
- cihaz tipi
- uretici / model
- organizasyon / lokasyon
- sahiplik modeli
- birincil kullanici
- owner / sorumlu ekip
- maliyet merkezi
- yasam dongusu durumu
alanlarini doldurur.

Cikti:
- teknik agent olmasa bile asset kaydi acilabilir.

### C. Agent ile asset eslestirme

Kullanici:
- `Asset Registry > Eslestirme Kuyrugu`
ekranina girer.

Burada sistem sunlari listeler:
- agent var ama asset baglanmamis kayitlar
- asset var ama agent baglanmamis kayitlar
- birden fazla eslesme adayi olan kayitlar

Kullanici:
- onerilen eslesmeyi onaylar
- reddeder
- manuel yeni asset acar
- var olan asset'e baglar

Cikti:
- teknik agent ile kurumsal asset birbirine baglanir.

### D. Sahipsiz cihazlari duzeltme

Kullanici:
- `Asset Registry > Veri Kalitesi`
ekranina girer.

Burada gorur:
- primary user bos olanlar
- lokasyonu eksik olanlar
- maliyet merkezi bos olanlar
- ownership type belirsiz olanlar

Kullanici:
- toplu duzeltme
- tekil duzeltme
- import ile tamamlama
yapar.

### E. Help desk kullanimi

Kullanici:
- ajan detayina gitmeden once veya remote support baslatmadan once
- `Asset Registry > Asset Detay`
ekraninda cihazin baglamini gorur.

Gormesi gereken temel alanlar:
- organizasyon yolu
- lokasyon yolu
- primary user
- owner
- cihaz tipi
- kullanim tipi

Boylece teknik destek islemi baglamsiz kalmaz.

### F. Raporlama

Kullanici:
- `Asset Registry > Raporlar`
ekranina girer.

Burada asagidakileri alabilir:
- organizasyon bazli cihaz sayisi
- kampus bazli online/offline dagilimi
- maliyet merkezi bazli lisans riski
- lokasyon bazli remote support yogunlugu
- sahipsiz cihazlar listesi
- eslesmemis agent / asset listesi

## Dikey Senaryolar

### Senaryo 1: Cok-sirketli veya cok-lokasyonlu kurumsal yapi

Hiyerarsi ornegi:
- Kurum: `Akgun Grup`
- Alt kurum: `Merkez Ofis`, `Teknoloji Sirketi`, `Saha Operasyonlari`
- Kampus / Tesis: `Merkez Yerleske`, `Ankara Ofis`, `Gebze Tesis`
- Bina: `A Blok`, `Operasyon Binasi`
- Kat: `2. Kat`
- Birim: `Finans`, `Insan Kaynaklari`, `Satis Operasyonlari`, `Destek Masasi`

Kullanici bu yapi uzerinden:
- birime gore cihaz bulur
- bina bazli risk raporu alir
- organizasyon bazli sahiplik takibi yapar

### Senaryo 2: Ortak kullanim cihazlari

Ornek cihazlar:
- resepsiyon terminali
- vardiya terminali
- kiosk
- ortak egitim salonu cihazi

Bu cihazlarda:
- primary user zorunlu olmayabilir
- `usage_mode = shared`
- owner ekip bazli olabilir

### Senaryo 3: Calisana atamali cihaz

Laptop veya tablet:
- primary user = belirli personel
- owner = ilgili organizasyon veya sorumlu ekip
- location = son fiziksel atanmis yer
- cost center = bagli oldugu birim

### Senaryo 4: Saglik gibi dikeylerde uyarlama

Ayni model isterse saglik kuruluslarinda da kullanilabilir.
Bu durumda:
- organizasyon tarafi `kurum / bashekimlik / direktorluk / klinik / birim`
- lokasyon tarafi `kampus / bina / kat / alan / oda`
olarak uyarlanir.

Ancak cekirdek modelin varsayilani saglika ozel degil, genel kurumsal yapidir.

## Kullanim Kurallari

- Teknik agent kaydi tek basina kurumsal dogruluk anlamina gelmez.
- Asset verisi manuel onay veya guvenilir import ile dogrulanmalidir.
- Eslesme motoru yardimci olabilir ama son karar operator ekraninda verilir.
- Raporlar varsayilan olarak `asset baglami` uzerinden uretilmelidir.
