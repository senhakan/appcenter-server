# Inventory Normalization

Bu dokuman inventory (installed software) verisindeki farkli yazim/format varyasyonlarini normalize etmek icin pratik oneriler icerir.

## 1. Problem Tipleri (Sahada Gorulen)

Bu hosttaki mevcut veride gorulen ornekler:

- Sonda/basta bosluk: `Cisco Secure Client - AnyConnect VPN ` (sonda space)
- Unicode bosluk: NBSP (`\\u00A0`) iceren adlar (ornegin `akweb14\\u00A0`)
- Ayni urunun adinda mimari/versiyon ekleri:
  - `7-Zip 26.00 (x64 edition)`
  - `Notepad++ (64-bit x64)`
  - `Microsoft Windows Desktop Runtime - 8.0.5 (x64)`
- Komponent/pack entries:
  - `Office 16 Click-to-Run ...`
  - `CCC Help <Language>`

## 2. Baseline Temizlik (Onerilen Davranis)

Kural yazmadan once her kayit icin su temizliklerin uygulanmasi, hem diff hem de UI'da ciddi kalite artisi saglar:

- `NFKC` unicode normalize
- NBSP (`\\u00A0`) -> ASCII space
- tum whitespace runlarini tek space'e indirgeme + trim
- karsilastirmalarda `casefold()` ile case-insensitive anahtar

Not: Bu temizlik yalnizca goruntu/diff icin degil, `change_history` (installed/removed/updated) hesaplamasinda da kullanilmalidir. Aksi halde sadece sonda bosluk farki bile "kaldirildi/eklendi" gibi yalanci degisim uretir.

## 3. Normalization Rules (Mevcut Rule Engine ile)

Mevcut rule engine `match_type`: `exact | contains | starts_with` destekler ve ilk eslesen (id sirasi) kural uygulanir.

Onerilen baslangic seti (ornek):

1. .NET Desktop Runtime'lari tek isimde topla
- `match_type`: `starts_with`
- `pattern`: `Microsoft Windows Desktop Runtime -`
- `normalized_name`: `Microsoft .NET Desktop Runtime`

2. Office Click-to-Run komponentlerini tek isimde topla
- `match_type`: `starts_with`
- `pattern`: `Office 16 Click-to-Run`
- `normalized_name`: `Microsoft Office 2016 (Click-to-Run Components)`

3. Notepad++ mimari eklerini topla
- `match_type`: `starts_with`
- `pattern`: `Notepad++`
- `normalized_name`: `Notepad++`

4. 7-Zip versiyonlu adlari topla
- `match_type`: `contains`
- `pattern`: `7-Zip`
- `normalized_name`: `7-Zip`

5. AMD CCC Help (dil paketleri) topla
- `match_type`: `starts_with`
- `pattern`: `CCC Help`
- `normalized_name`: `AMD Catalyst Control Center`

Bu kurallar UI'dan veya API ile eklenebilir:

```bash
curl -sS -X POST http://127.0.0.1:8000/api/v1/inventory/normalization \\
  -H \"Authorization: Bearer <token>\" \\
  -H \"Content-Type: application/json\" \\
  -d '{\"pattern\":\"Microsoft Windows Desktop Runtime -\",\"normalized_name\":\"Microsoft .NET Desktop Runtime\",\"match_type\":\"starts_with\"}'
```

## 4. Publisher Normalizasyon (Oneri)

Su anki model sadece isim normalizasyonu yapiyor. Publisher tarafinda pratikte su varyasyonlar gorulebilir:

- `Microsoft` vs `Microsoft Corporation`
- `Advanced Micro Devices, Inc.` vs `AMD`
- buyuk/kucuk harf / Turkce karakter farklari

Eger lisans/uyumluluk tarafinda publisher kritik olacaksa, ek bir alan/tabla ile `normalized_publisher` mantigi eklemek faydali olur.

## 5. Uygulanan Kural Seti (2026-03-05)

Canli PostgreSQL uzerinde versiyon sonekli yazilim adlari ve belirgin alias'lar icin kural seti uygulandi ve tum inventory yeniden normalize edildi.

Eklenen ana gruplar:

- Microsoft Visual C++ redistributable aileleri (2008 x64/x86, 2012 x64/x86, 2013 x64/x86, 2015-2022 x64/x86) icin `starts_with` kurallari
- `7-Zip`, `Greenshot`, `TAP-Windows`, `WinAppRuntime`, `Mirth Connect Administrator Launcher`, `Microsoft Network Monitor` aileleri icin versiyon soneki temizleme kurallari
- `Advanced IP Scanner` icin versiyon soneki temizleme kurali (`2.5`, `2.5.1` -> tek ad)
- Alias birlestirme:
  - `MicrosoftEdge` -> `Microsoft Edge`
  - `MicrosoftTeams` ve `MSTeams` -> `Microsoft Teams`
  - `NotepadPlusPlus` ve `Notepad++ (...)` -> `Notepad++`
  - `7zip` -> `7-Zip`

Ek guvenlik iyilestirmesi:

- Eski genis kural `starts_with: 7` daraltilarak `starts_with: 7-Zip` yapildi.

Olculen etki:

- `unique_raw` (ham ad): `3026` (degismedi)
- `unique_normalized`: `3011 -> 2973` (38 adet daha az parcalanmis yazilim ismi)
- Toplam aktif normalizasyon kurali (guncel): `8`

Ornek birlesmeler:

- `Microsoft Visual C++ 2015-2022 Redistributable (x64)` altinda 4 farkli ham isim tek gorunume toplandi
- `7-Zip` altinda 7 farkli ham isim tek gorunume toplandi
- `Microsoft Teams` altinda `MicrosoftTeams` + `MSTeams` tek gorunume toplandi
- `Notepad++` altinda `NotepadPlusPlus` + `Notepad++ (64-bit x64)` tek gorunume toplandi

## 6. Genel Versiyon-Soneki Fallback (Kod Seviyesinde)

Tek tek urun kurali yazmadan, kural motoru eslesmezse su fallback devreye alindi:

- Format: `UrunAdi 2.5`, `UrunAdi 2.5.1`, `UrunAdi v1.2.3`
- Son ek versiyon tokeni temizlenir, taban ad normalize isim olarak kullanilir.
- Yil/edition gibi `tek sayi` son ekler (ornegin `Office 2021`) etkilenmez; en az bir `.` zorunludur.
- Versiyon kaldirilinca sonda kalan ayiraclar (`-`, `_`, `:` vb.) da temizlenir.

Ornek:

- `Advanced IP Scanner 2.5` + `Advanced IP Scanner 2.5.1` -> `Advanced IP Scanner`
- `Microsoft Visual C++ 2010 x64 Redistributable - 10.0.40219` -> `Microsoft Visual C++ 2010 x64 Redistributable`

Not:

- Genel fallback devreye alindiktan sonra ayni isi yapan urun-ozel `starts_with` kurallari temizlendi.
- Boylece kural tablosu daha sade kalirken normalize sonucu korunur.
