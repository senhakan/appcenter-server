# Development Workflow

Bu dokuman ekip ici gelistirme akisini standartlastirir.

## 1. Hazirlik

```bash
python3.9 -m venv venv39
source venv39/bin/activate
pip install -r requirements.txt
```

## 2. Gelistirme Sirasi

- Faz bazli ilerle (1 -> 5).
- Faz 6 (UI yonetim iyilestirmeleri) aktif olarak faz 5 uzerine iteratif ilerletilir.
- Her faz sonunda:
  - API smoke test
  - `pytest -q`
  - Dokuman guncellemesi (`README.md`, gerekirse `CLAUDE.md`).

## 2.1 Sonraki Asama Plani

1. Faz 6.1:
- Edit formlarinda validation + daha net hata mesaji
- uygulama/dağıtım/grup duzenleme icin frontend form kontrolleri
2. Faz 6.2:
- Gruplar icin silme/pasife alma stratejisi
- deployment listesinde app/group/agent isimlerinin zengin gosterimi
3. Faz 6.3:
- Audit log (kim, neyi, ne zaman degistirdi)
- kritik degisikliklerde onay/ikinci adim

Detayli yol haritasi ve tema notlari:
- `docs/ROADMAP_AND_THEME.md`

## 3. Kod Standarti

- DB degisikliklerinde SQLite PRAGMA kurallari korunur.
- Tum timestamp'ler UTC tutulur.
- Agent auth: `X-Agent-UUID` + `X-Agent-Secret`
- Web auth: JWT Bearer

## 4. Commit Kurali

- Tek sorumluluklu commit tercih edilir.
- Mesaj formati:
  - `feat: ...`
  - `fix: ...`
  - `docs: ...`
  - `test: ...`

Ornek:

```bash
git add -A
git commit -m "feat: add deployment task assignment flow"
```

## 5. Merge Oncesi Kontrol

```bash
pytest -q
```

- CI yesil olmadan merge edilmez.
