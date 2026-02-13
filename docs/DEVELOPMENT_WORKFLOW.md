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
- Her faz sonunda:
  - API smoke test
  - `pytest -q`
  - Dokuman guncellemesi (`README.md`, gerekirse `CLAUDE.md`).

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
