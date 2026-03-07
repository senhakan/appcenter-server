# Timeline V2 Alternatifleri (Arastirma + Uygulama)

Tarih: 2026-03-07

## Problem

Timeline alaninda ayni dakikada cok sayida benzer olay olustugunda okunabilirlik dusuyor.
Hedef:

- Operasyonel bakista "ne oldu?" sorusuna hizli cevap
- Inceleme bakisinda ham olaya inebilme
- Coklu host/status degisiminde bilgi kaybi olmadan ozetleme

## Arastirma Notlari (Kisa)

- Activity stream urunleri olaylari zaman bazli gruplama ve filtreleme ile sunuyor.
  - Atlassian Activity Stream dokumani tarih bazli gruplamayi vurgular.
  - Kaynak: https://confluence.atlassian.com/display/DOCM/Activity%2BStream%2BGadget
- Security timeline urunleri (Elastic) ham olay + renderer + filtre kombinasyonunu onerir.
  - Kaynak: https://www.elastic.co/guide/en/security/current/timelines-ui.html
- Yogun veri listelerinde tablo/ozet formatinda taranabilirlik (scanability) onemlidir.
  - Kaynak: https://m1.material.io/components/data-tables.html

Not: Ustteki kaynaklardan cikarimla "tek gorunum" yerine "is amacina gore degistirilebilir gorunum" en pratik yaklasimdir.

## V2'de Uygulanan Alternatifler

`/dashboard-v2` icindeki "Timeline Lab (V2)" kartina gorunum secici eklendi:

1. A: Host + Status (Onerilen)
   - Ayni dakika + ayni tip olaylari birlestirir
   - Status olaylarinda host bazli `Up/Down` badge'leri gosterir
   - `Up/Down` uzerine gelince tam saatler tooltip'te gorunur
2. B: Dakika Ozeti
   - Dakika bazinda event type ozet tablosu
   - Host kapsami + olay adedi + status up/down sayisi
3. C: Ham Olay Akisi
   - Dakika gruplu ama event satirlari tek tek korunur
   - Inceleme/sorun ayiklama icin detay gorunumu

## Degerlendirme Kriterleri

- Okunabilirlik: 50+ olayda ilk bakista anlamlandirma suresi
- Dogruluk: Ozet satirinin ham olay sayisiyla tutarliligi
- Drill-down: Ham olaya inis maliyeti
- Operasyon hizi: "hangi hostlar etkilendi?" sorusuna yanit suresi

## Onerilen Varsayilan

- Varsayilan gorunum: `A: Host + Status (Onerilen)`
- Neden:
  - Operasyonel karar icin en az bilişsel yuk
  - Status degisimlerinde host + durum birlikte gorunur
  - Saat detaylari tooltip ile kaybolmaz
