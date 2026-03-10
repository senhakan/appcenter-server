# 08 - Canonical Model

Bu belge, Asset Registry / CMDB Lab icin sonradan degistirilmesi en zor olacak temel model kararlarini sabitler.

Amac:
- ekran tasarimlari degisse bile veri modelinin omurgasini korumak
- organizasyon ve lokasyon tarafini birbirine karistirmamak
- ilk faz hafif kalsa da ikinci fazlarda geri donusu zor kirilimlari dogru secmek

## 1. Cekirdek Kavramlar

Bu modulde dort ana kavram vardir:

- `Agent`
  Teknik runtime varligidir. Heartbeat, online durumu, inventory ve remote support bilgisini tasir.
- `Asset`
  Kurumsal varlik kaydidir. Cihazin is kimligi, sahipligi, lokasyonu ve yasam dongusunu tasir.
- `Organization`
  Cihazin hangi yonetsel yapida konumlandigini tanimlar.
- `Location`
  Cihazin fiziksel olarak nerede oldugunu tanimlar.

Bu kavramlar ayni tabloya veya ayni anlam katmanina indirilmez.

## 2. Organizasyon Ve Lokasyon Ayrimi

Temel kural:
- organizasyon = yonetsel bag
- lokasyon = fiziksel bag

Ornek:
- cihaz `Finans Direktorlugu > Muhasebe Takimi` altinda olabilir
- fiziksel olarak `Merkez Kampus > A Blok > 3. Kat > Acik Ofis` icinde olabilir

Bu iki eksen ayri tablolarda tutulur ve her ikisi de asset uzerinde bagimsiz alan olarak yer alir.

## 3. Varsayilan Organizasyon Hiyerarsisi

Varsayilan kurumsal organizasyon seviyeleri:

1. `company`
2. `legal_entity`
3. `region`
4. `directorate`
5. `department`
6. `team`
7. `unit`

Kurallar:
- her kurulum tum seviyeleri kullanmak zorunda degildir
- UI etiketleri degisebilir, semantik sira degismez
- yeni ihtiyaclar once mevcut seviyelerle cozulmeye calisilir
- yeni sektorlerde farkli etiketleme yapilabilir ama veri modeli bu semantik seviyeleri referans almaya devam eder

## 4. Varsayilan Lokasyon Hiyerarsisi

Varsayilan fiziksel lokasyon seviyeleri:

1. `campus`
2. `building`
3. `block`
4. `floor`
5. `area`
6. `room`

Kurallar:
- `campus` yerine `site` veya `facility` gorunebilir
- `area`, acik ofis, servis alani, depo alani, ortak alan, hat alani gibi ara fiziksel seviyeleri temsil eder
- `room`, en alt fiziksel kirilimdir

## 5. Sahiplik Ve Sorumluluk Rolleri

Her asset icin bu roller birbirinden ayridir:

- `primary_person`
  Cihazi asil kullanan kisi
- `owner_person`
  Cihazdan idari veya zimmetsel olarak sorumlu kisi
- `support_team`
  Cihazdan operasyonel olarak sorumlu ekip
- `cost_center`
  Cihazin maliyetinin baglandigi finansal kirilim

Kurallar:
- `primary_person` bos olabilir
- `owner_person` ileride kisi yerine organizasyon owner modeline evrilebilir
- `support_team` her zaman operasyonel raporlama icin ayrik kalir

## 6. Device Type Ve Usage Type Ayrimi

Iki sozluk ayrik tutulur:

- `device_type`
  Fiziksel veya mantiksal cihaz sinifidir
- `usage_type`
  Cihazin nasil kullanildigini tanimlar

Ornek:
- `device_type = laptop`, `usage_type = personal`
- `device_type = shared_terminal`, `usage_type = shared`
- `device_type = kiosk`, `usage_type = kiosk`

Bu iki anlam tek alanda birlestirilmez.

## 7. Iliski Kurallari

Ilk fazda ana iliski kurallari:

- bir `asset` zaman icinde birden fazla `agent` ile iliskilenebilir
- bir `agent` ayni anda yalnizca bir aktif `asset` bagina sahip olur
- aktif bag `asset_agent_links.is_primary = true` ile temsil edilir
- link gecmisi silinmez, durum degistirilir

## 8. Minimum Zorunlu Alan Seti

Ilk fazda tum alanlar zorunlu yapilmaz.
Ama kurumsal anlam uretmek icin minimum alan seti tanimlanir:

- `asset_tag` veya kurumun kabul ettigi benzersiz asset anahtari
- `device_type`
- `usage_type`
- `ownership_type`
- `lifecycle_status`
- `org_node_id`
- `location_node_id`

Kosullu guclu alanlar:
- bireysel cihazlarda `primary_person`
- ortak cihazlarda `support_team`
- finansal raporlama gerekiyorsa `cost_center`

## 9. Tarihce Ve Audit Yaklasimi

Bu modulde tarihce sonradan eklenen bir ozellik olmayacak, tasarimin parcasi olacaktir.

Asgari beklenti:
- asset ana alan degisiklikleri kaydedilir
- link / unlink islemleri kaydedilir
- organizasyon ve lokasyon degisiklikleri gecmise yazilir
- silme yerine pasife alma tercih edilir

## 10. Dikey Uyarlama Kurali

Saglik, egitim, kamu, holding, uretim gibi dikeylerde:
- ekran etiketleri
- sozluk degerleri
- rapor isimleri
uyarlanabilir.

Ama asagidaki omurga degismemelidir:
- agent / asset ayrimi
- organizasyon / lokasyon ayrimi
- primary user / owner / support team ayrimi
- device type / usage type ayrimi

## 11. Sabit Kararlar

Bu inisiyatif icin artik temel kabul edilmesi gereken kararlar:

- organizasyon ve lokasyon ayri tutulacak
- asset ile agent ayni nesne kabul edilmeyecek
- sozlukler tek alana yigilmeyecek
- link history korunacak
- yeni modul ilk fazda mevcut cekirdegi bozmayacak

Bu belge, sonraki ekran detaylari ve teknik tasarim icin referans kabul edilir.
